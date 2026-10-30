"""Historical irrigation and water-sensor analysis for AgriSenseAI."""

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean

from tools import Tool
from tools.data_query import get_data_dir


class IrrigationAnalysis(Tool):
    name = "irrigation_analysis"
    description = (
        "Analyze historical tomato irrigation and water-sensor records. "
        "Summarize soil-moisture percentage, temperature, humidity, "
        "evapotranspiration fields, recorded irrigation-needed values, "
        "motor status, water volume and daily readings for a requested "
        "number of calendar days. This is historical dataset analysis, "
        "not a live weather forecast or an automatic irrigation prescription."
    )
    args_doc = '{"filename": "tomato_water_sensor_data.json", "days": 7}'

    @staticmethod
    def _number(row, field):
        """Return a finite numeric value, or None if unavailable/invalid."""
        try:
            value = float(row.get(field))
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    @classmethod
    def _summary(cls, rows, field, unit):
        values = [
            value for row in rows
            if (value := cls._number(row, field)) is not None
        ]
        if not values:
            return {"average": None, "minimum": None, "maximum": None, "unit": unit}
        return {
            "average": round(mean(values), 2),
            "minimum": round(min(values), 2),
            "maximum": round(max(values), 2),
            "unit": unit,
        }

    def execute(self, filename="tomato_water_sensor_data.json", days=7, **kwargs):
        try:
            days = int(days)
        except (TypeError, ValueError):
            return "ERROR: days must be a whole number between 1 and 365."

        if not 1 <= days <= 365:
            return "ERROR: days must be between 1 and 365."

        data_dir = get_data_dir().resolve()
        path = (data_dir / filename).resolve()

        if not path.is_relative_to(data_dir):
            return "ERROR: Dataset must be inside the configured data directory."
        if not path.is_file():
            return f"ERROR: Dataset not found: {filename}"

        try:
            records = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return f"ERROR: Could not read irrigation dataset: {exc}"

        if not isinstance(records, list) or not records:
            return "ERROR: Expected a non-empty JSON list of sensor records."

        parsed = []
        skipped_records = 0
        for row in records:
            if not isinstance(row, dict):
                skipped_records += 1
                continue
            try:
                timestamp = datetime.fromisoformat(str(row.get("dateTimeAdded", "")))
            except ValueError:
                skipped_records += 1
                continue
            parsed.append((timestamp, row))

        if not parsed:
            return "ERROR: No records with a valid dateTimeAdded timestamp were found."

        latest_timestamp = max(timestamp for timestamp, _ in parsed)
        end_date = latest_timestamp.date()
        start_date = end_date - timedelta(days=days - 1)
        selected = [
            row for timestamp, row in parsed
            if start_date <= timestamp.date() <= end_date
        ]
        if not selected:
            return "ERROR: No sensor records were found in the requested date range."

        metric_fields = {
            "temperature_c": ("temperature", "°C"),
            "relative_humidity": ("humidity", "%"),
            "soil_moisture_percentage": ("moisturePercentage", "% as recorded in dataset"),
            "evapotranspiration_value": ("evapotranspirationValue", "unit not specified in dataset"),
            "reference_eto": ("reference_eto", "unit not specified in dataset"),
            "irrigation_needed_value": ("irrigation_needed_value", "unit not specified in dataset"),
            "water_volume_per_record": ("waterVolume_liter", "litres per record"),
            "water_flow_rate": ("waterFlow_rate", "unit not specified in dataset"),
            "wind_speed": ("windSpeedVal", "unit not specified in dataset"),
            "solar_radiation_ghi": ("solarRadiation_ghi_val", "unit not specified in dataset"),
        }
        summaries = {
            name: self._summary(selected, field, unit)
            for name, (field, unit) in metric_fields.items()
        }

        by_day = defaultdict(list)
        for row in selected:
            try:
                day = datetime.fromisoformat(str(row.get("dateTimeAdded", ""))).date()
            except ValueError:
                continue
            by_day[day].append(row)

        daily_summary = []
        for day in sorted(by_day):
            day_rows = by_day[day]
            daily_summary.append({
                "date": day.isoformat(),
                "record_count": len(day_rows),
                "average_moisture_percentage": self._summary(
                    day_rows, "moisturePercentage", "%"
                )["average"],
                "average_water_volume_per_record_litres": self._summary(
                    day_rows, "waterVolume_liter", "L"
                )["average"],
                "records_with_positive_irrigation_needed_value": sum(
                    (self._number(row, "irrigation_needed_value") or 0) > 0
                    for row in day_rows
                ),
                "records_with_motor_on": sum(
                    self._number(row, "motorValue") == 1 for row in day_rows
                ),
            })

        expected_days = [start_date + timedelta(days=offset) for offset in range(days)]
        missing_days = [day.isoformat() for day in expected_days if day not in by_day]
        latest_row = max(
            selected,
            key=lambda row: datetime.fromisoformat(str(row.get("dateTimeAdded", "")))
        )

        latest_moisture = self._number(latest_row, "moisturePercentage")
        min_moisture = self._number(latest_row, "minTomatoMoisture")
        max_moisture = self._number(latest_row, "maxTomatoMoisture")
        if latest_moisture is None or min_moisture is None or max_moisture is None:
            moisture_interpretation = "The latest record does not contain enough information to compare moisture with the dataset's stored bounds."
        elif latest_moisture < min_moisture:
            moisture_interpretation = (
                f"Latest moisture ({latest_moisture:.2f}%) is below the dataset's stored minimum "
                f"({min_moisture:.2f}%). Confirm sensor calibration and field conditions."
            )
        elif latest_moisture > max_moisture:
            moisture_interpretation = (
                f"Latest moisture ({latest_moisture:.2f}%) is above the dataset's stored maximum "
                f"({max_moisture:.2f}%). Confirm sensor calibration and field conditions."
            )
        else:
            moisture_interpretation = (
                f"Latest moisture ({latest_moisture:.2f}%) is within the dataset's stored bounds "
                f"({min_moisture:.2f}% to {max_moisture:.2f}%). These stored bounds are not an independently verified agronomic recommendation."
            )

        latest_irrigation_value = self._number(latest_row, "irrigation_needed_value")
        latest_motor = self._number(latest_row, "motorValue")
        if latest_irrigation_value is not None and latest_irrigation_value > 0:
            irrigation_interpretation = (
                "The latest record has a positive irrigation_needed_value in the source dataset. "
                "Its unit is not specified, so do not interpret it as litres or millimetres."
            )
        elif latest_motor == 1:
            irrigation_interpretation = (
                "The latest record shows motorValue=1. The dataset does not specify a complete irrigation schedule."
            )
        else:
            irrigation_interpretation = (
                "The latest record shows irrigation_needed_value=0 and motorValue is not on; "
                "the latest record does not flag irrigation demand."
            )

        records_with_irrigation_flag = sum(
            (self._number(row, "irrigation_needed_value") or 0) > 0
            for row in selected
        )
        records_with_motor_on = sum(
            self._number(row, "motorValue") == 1 for row in selected
        )

        result = {
            "analysis": "Tomato Irrigation and Water-Sensor Analysis",
            "dataset": filename,
            "date_range": {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "calendar_days_requested": days,
                "days_with_records": len(by_day),
                "days_without_records": missing_days,
            },
            "records_analyzed": len(selected),
            "invalid_or_skipped_records_in_file": skipped_records,
            "measurements": summaries,
            "irrigation_indicators": {
                "records_with_positive_irrigation_needed_value": records_with_irrigation_flag,
                "records_with_motor_on": records_with_motor_on,
                "latest_record_interpretation": irrigation_interpretation,
                "latest_moisture_interpretation": moisture_interpretation,
            },
            "latest_record": {
                "dateTimeAdded": latest_row.get("dateTimeAdded"),
                "temperature_c": latest_row.get("temperature"),
                "humidity_percent": latest_row.get("humidity"),
                "moisturePercentage": latest_row.get("moisturePercentage"),
                "dataset_minTomatoMoisture": latest_row.get("minTomatoMoisture"),
                "dataset_maxTomatoMoisture": latest_row.get("maxTomatoMoisture"),
                "irrigation_needed_value": latest_row.get("irrigation_needed_value"),
                "motorValue": latest_row.get("motorValue"),
                "waterVolume_liter": latest_row.get("waterVolume_liter"),
                "waterFlow_rate": latest_row.get("waterFlow_rate"),
            },
            "daily_summary": daily_summary,
            "limitations": [
                "This tool summarizes historical records; it does not provide live readings or weather forecasts.",
                "The dataset does not specify units for irrigation_needed_value, evapotranspirationValue, reference_eto or waterFlow_rate.",
                "waterVolume_liter is reported as recorded per row; it is not summed into a daily total because rows may repeat timestamps or sensor states.",
                "Record counts are counts of dataset rows, not verified unique irrigation events.",
                "The dataset's stored moisture bounds should be checked against the actual sensor calibration and local crop guidance.",
            ],
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

import csv
import json

from tools import Tool
from tools.data_query import get_data_dir


class SoilAnalysis(Tool):

    name = "soil_analysis"

    description = (
        "Analyze tomato soil and NPK dataset readings. "
        "Provides nitrogen, phosphorus, potassium, "
        "soil moisture, pH, temperature and humidity "
        "statistics for the latest number of planted days."
    )

    args_doc = (
        '{"filename": "tomato_irrigation_dataset.csv", "days": 7}'
    )

    def execute(
        self,
        filename="tomato_irrigation_dataset.csv",
        days=7,
        **kwargs
    ):

        try:
            days = int(days)

            if days < 1 or days > 365:
                return "ERROR: Days must be between 1 and 365."

            data_dir = get_data_dir()
            path = (data_dir / filename).resolve()

            if not path.is_relative_to(data_dir):
                return "ERROR: Dataset must be inside data folder."

            if not path.is_file():
                return f"ERROR: Dataset not found: {filename}"

            with path.open(
                "r",
                encoding="utf-8-sig",
                newline=""
            ) as file:

                reader = csv.DictReader(file)

                if not reader.fieldnames:
                    return "ERROR: Dataset has no column headers."

                headers = {
                    header.strip(): header
                    for header in reader.fieldnames
                }

                required = [
                    "Days of planted",
                    "Nitrogen [mg/kg]",
                    "Phosphorus [mg/kg]",
                    "Potassium",
                    "Soil moisture",
                    "pH",
                    "Temperature [_ C]",
                    "Humidity [%]",
                    "Crop Coefficient stage"
                ]

                missing = [
                    column for column in required
                    if column not in headers
                ]

                if missing:
                    return (
                        "ERROR: Missing dataset columns: "
                        + ", ".join(missing)
                    )

                rows = list(reader)

            if not rows:
                return "ERROR: No dataset records found."

            def get_number(row, column):
                return float(row[headers[column]])

            valid_rows = []

            for row in rows:
                try:
                    valid_rows.append({
                        "day": get_number(row, "Days of planted"),
                        "nitrogen": get_number(
                            row, "Nitrogen [mg/kg]"
                        ),
                        "phosphorus": get_number(
                            row, "Phosphorus [mg/kg]"
                        ),
                        "potassium": get_number(
                            row, "Potassium"
                        ),
                        "moisture": get_number(
                            row, "Soil moisture"
                        ),
                        "ph": get_number(row, "pH"),
                        "temperature": get_number(
                            row, "Temperature [_ C]"
                        ),
                        "humidity": get_number(
                            row, "Humidity [%]"
                        ),
                        "stage": row[
                            headers["Crop Coefficient stage"]
                        ]
                    })

                except (ValueError, TypeError, KeyError):
                    continue

            if not valid_rows:
                return "ERROR: No valid numeric records found."

            latest_day = max(
                row["day"] for row in valid_rows
            )

            selected = [
                row for row in valid_rows
                if row["day"] >= latest_day - days + 1
            ]

            if not selected:
                return "ERROR: No records available for this period."

            def summary(key):
                values = [row[key] for row in selected]

                return {
                    "average": round(
                        sum(values) / len(values), 2
                    ),
                    "minimum": round(min(values), 2),
                    "maximum": round(max(values), 2)
                }

            stages = {}

            for row in selected:
                stage = row["stage"]
                stages[stage] = stages.get(stage, 0) + 1

            result = {
                "analysis": "Tomato Soil and NPK Analysis",

                "dataset": filename,

                "planted_day_range": {
                    "from": latest_day - days + 1,
                    "to": latest_day
                },

                "records_analyzed": len(selected),

                "NPK": {
                    "nitrogen_mg_per_kg": summary("nitrogen"),
                    "phosphorus_mg_per_kg": summary("phosphorus"),
                    "potassium_dataset_value": summary("potassium")
                },

                "soil": {
                    "moisture_sensor_value": summary("moisture"),
                    "pH": summary("ph")
                },

                "environment": {
                    "temperature_c": summary("temperature"),
                    "humidity_percent": summary("humidity")
                },

                "growth_stages": stages,

                "limitations": [
                    "This is a dataset statistical summary, not a soil diagnosis.",
                    "Soil moisture is reported as the dataset's sensor value, not a percentage.",
                    "Compare NPK and pH values with locally calibrated soil-test recommendations before prescribing fertilizer."
                ]
            }

            return json.dumps(result, indent=2)

        except (OSError, csv.Error, ValueError) as error:
            return f"ERROR: Soil analysis failed: {error}"
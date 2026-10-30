"""Tomato nutrient-data summary and TNAU reference schedule for AgriSenseAI.

This tool deliberately does not convert dataset NPK concentrations (mg/kg)
into fertilizer application rates (kg/ha). That conversion requires a
locally calibrated soil-test interpretation and field-specific details.
"""

import csv
import json
import math
from pathlib import Path
from statistics import mean

from tools import Tool
from tools.data_query import get_data_dir


class FertilizerAdvisor(Tool):
    name = "fertilizer_advisor"
    description = (
        "Summarize recent tomato soil NPK and pH readings and provide clearly "
        "labelled Tamil Nadu Agricultural University (TNAU) reference nutrient "
        "schedules for standard tomato varieties or COTH1/COTH2 hybrids. "
        "Requires tomato_type='variety', 'hybrid', or 'unknown'. Does not "
        "diagnose nutrient deficiency or calculate a farm-specific fertilizer dose."
    )
    args_doc = (
        '{"filename": "tomato_irrigation_dataset.csv", '
        '"days": 7, "tomato_type": "unknown"}'
    )

    # Source: TNAU ICT-AAS tomato crop advisory.
    SOURCE_URL = (
        "https://agritech.tnau.ac.in/govt_schemes_services/aas/tomato.html"
    )

    TNAU_SCHEDULES = {
        "variety": {
            "profile": "TNAU tomato recommendation for listed varieties",
            "basal_before_or_at_planting": {
                "FYM_t_per_ha": 25,
                "nitrogen_kg_per_ha": 75,
                "phosphorus_kg_per_ha": 100,
                "potassium_kg_per_ha": 50,
                "borax_kg_per_ha": 10,
                "zinc_sulphate_kg_per_ha": 50,
            },
            "top_dressing": [
                {
                    "timing": "30 days after planting, during earthing up",
                    "nitrogen_kg_per_ha": 75,
                }
            ],
        },
        "hybrid": {
            "profile": "TNAU recommendation for COTH1/COTH2 hybrid tomato",
            "basal_before_or_at_planting": {
                "FYM_t_per_ha": 25,
                "NPK_kg_per_ha": {"N": 50, "P": 300, "K": 50},
            },
            "top_dressing": [
                {
                    "timing": "30 days after planting",
                    "nitrogen_kg_per_ha": 50,
                    "potassium_kg_per_ha": 50,
                },
                {
                    "timing": "45 days after planting",
                    "nitrogen_kg_per_ha": 50,
                    "potassium_kg_per_ha": 50,
                },
                {
                    "timing": "60 days after planting",
                    "nitrogen_kg_per_ha": 50,
                    "potassium_kg_per_ha": 50,
                },
            ],
        },
    }

    @staticmethod
    def _finite_number(row, column):
        try:
            value = float(row[column])
        except (KeyError, TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    @classmethod
    def _metric_summary(cls, rows, column, unit):
        values = [
            value for row in rows
            if (value := cls._finite_number(row, column)) is not None
        ]
        if not values:
            return {
                "average": None,
                "minimum": None,
                "maximum": None,
                "unit": unit,
                "valid_records": 0,
            }
        return {
            "average": round(mean(values), 2),
            "minimum": round(min(values), 2),
            "maximum": round(max(values), 2),
            "unit": unit,
            "valid_records": len(values),
        }

    def execute(
        self,
        filename="tomato_irrigation_dataset.csv",
        days=7,
        tomato_type="unknown",
        **kwargs,
    ):
        try:
            days = int(days)
        except (TypeError, ValueError):
            return "ERROR: days must be a whole number from 1 to 365."
        if not 1 <= days <= 365:
            return "ERROR: days must be between 1 and 365."

        tomato_type = str(tomato_type or "unknown").strip().lower()
        aliases = {
            "standard": "variety",
            "open_field_variety": "variety",
            "coth1": "hybrid",
            "coth2": "hybrid",
        }
        tomato_type = aliases.get(tomato_type, tomato_type)
        if tomato_type not in {"variety", "hybrid", "unknown"}:
            return (
                "ERROR: tomato_type must be 'variety', 'hybrid', or 'unknown'."
            )

        data_dir = Path(get_data_dir()).resolve()
        path = (data_dir / filename).resolve()
        if not path.is_relative_to(data_dir):
            return "ERROR: Dataset must be inside the configured data directory."
        if not path.is_file():
            return f"ERROR: Dataset not found: {filename}"

        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    return "ERROR: CSV dataset has no column headers."
                original_headers = reader.fieldnames
                normalized_headers = {
                    header.strip(): header for header in original_headers
                }
                required = [
                    "Days of planted",
                    "Nitrogen [mg/kg]",
                    "Phosphorus [mg/kg]",
                    "Potassium",
                    "pH",
                    "Crop Coefficient stage",
                ]
                missing = [
                    name for name in required
                    if name not in normalized_headers
                ]
                if missing:
                    return "ERROR: Missing CSV columns: " + ", ".join(missing)
                rows = list(reader)
        except (OSError, UnicodeError, csv.Error) as exc:
            return f"ERROR: Could not read soil dataset: {exc}"

        if not rows:
            return "ERROR: Soil dataset contains no records."

        def number(row, normalized_name):
            original_name = normalized_headers[normalized_name]
            return self._finite_number(row, original_name)

        valid_rows = [
            row for row in rows
            if number(row, "Days of planted") is not None
        ]
        if not valid_rows:
            return "ERROR: No valid planted-day values were found."

        latest_day = max(number(row, "Days of planted") for row in valid_rows)
        first_day = latest_day - days + 1
        selected = [
            row for row in valid_rows
            if first_day <= number(row, "Days of planted") <= latest_day
        ]
        if not selected:
            return "ERROR: No records found in the selected planted-day range."

        def summarize(normalized_name, unit):
            original_name = normalized_headers[normalized_name]
            return self._metric_summary(selected, original_name, unit)

        nutrient_data = {
            "nitrogen": summarize("Nitrogen [mg/kg]", "mg/kg as labelled in CSV"),
            "phosphorus": summarize("Phosphorus [mg/kg]", "mg/kg as labelled in CSV"),
            "potassium": summarize(
                "Potassium", "unit not specified in CSV header"
            ),
            "pH": summarize("pH", "pH units"),
        }

        stages = {}
        stage_column = normalized_headers["Crop Coefficient stage"]
        for row in selected:
            stage = str(row.get(stage_column, "Unknown")).strip() or "Unknown"
            stages[stage] = stages.get(stage, 0) + 1

        if tomato_type == "unknown":
            selected_schedule = None
            next_step = (
                "Identify whether the crop is a standard variety or a COTH1/COTH2 "
                "hybrid before selecting a schedule. The two TNAU profiles differ."
            )
            schedules_to_show = self.TNAU_SCHEDULES
        else:
            selected_schedule = self.TNAU_SCHEDULES[tomato_type]
            schedules_to_show = {tomato_type: selected_schedule}
            next_step = (
                "Confirm that this TNAU schedule matches the farm's location, "
                "cultivar, open-field system, soil-test report and current local "
                "extension advice before application."
            )

        result = {
            "analysis": "Tomato nutrient data summary and fertilizer reference",
            "dataset": filename,
            "planted_day_range": {
                "from": first_day,
                "to": latest_day,
            },
            "records_analyzed": len(selected),
            "observed_crop_stages": stages,
            "measured_soil_data": nutrient_data,
            "tomato_type_selected": tomato_type,
            "TNAU_reference_schedules": schedules_to_show,
            "interpretation": [
                "The dataset values are descriptive measurements, not calibrated fertilizer sufficiency classes.",
                "Nitrogen and phosphorus are labelled mg/kg in the CSV; the potassium unit is not specified.",
                "Soil-test concentrations in mg/kg cannot be directly converted into fertilizer application rates in kg/ha from this dataset alone.",
                "The TNAU schedules are crop-management references for specified tomato types; they are not personalized doses derived from these CSV averages.",
                "TNAU advises soil testing at the beginning of the crop season. Confirm pH and nutrients with a local soil-testing laboratory.",
            ],
            "next_step": next_step,
            "reference": {
                "organization": "Tamil Nadu Agricultural University (TNAU)",
                "title": "ICT-AAS Tomato crop advisory",
                "url": self.SOURCE_URL,
            },
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

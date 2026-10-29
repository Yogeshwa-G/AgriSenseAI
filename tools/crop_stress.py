"""Rule-based crop stress screening from basic sensor readings."""

import json

from tools import Tool


class CropStress(Tool):
    name = "crop_stress"
    description = (
        "Screen crop conditions for possible heat and water stress. "
        "Provide crop, temperature_c, soil_moisture_pct, and humidity_pct."
    )
    args_doc = (
        '{"crop": "tomato", "temperature_c": 38, '
        '"soil_moisture_pct": 18, "humidity_pct": 35}'
    )

    def execute(
        self,
        crop,
        temperature_c,
        soil_moisture_pct,
        humidity_pct,
    ):
        try:
            temperature = float(temperature_c)
            moisture = float(soil_moisture_pct)
            humidity = float(humidity_pct)
        except (TypeError, ValueError):
            return "ERROR: Sensor readings must be numeric."

        if not 0 <= moisture <= 100:
            return "ERROR: Soil moisture percentage must be between 0 and 100."

        if not 0 <= humidity <= 100:
            return "ERROR: Humidity percentage must be between 0 and 100."

        findings = []

        if temperature >= 35:
            findings.append(
                "High air temperature: assess heat stress, especially "
                "during flowering and fruit development."
            )
        elif temperature >= 30:
            findings.append(
                "Warm conditions: monitor the crop for heat-related symptoms."
            )

        if moisture <= 20:
            findings.append(
                "Low reported soil-moisture percentage: check sensor "
                "calibration, soil type, and moisture near the root zone."
            )

        if humidity <= 35:
            findings.append(
                "Low relative humidity: evaporative water loss may be elevated."
            )

        if not findings:
            findings.append(
                "These readings did not trigger the screening rules. "
                "This does not rule out crop stress."
            )

        result = {
            "crop": str(crop),
            "readings": {
                "temperature_c": temperature,
                "soil_moisture_pct": moisture,
                "humidity_pct": humidity,
            },
            "screening": "Potential stress indicators detected"
            if len(findings) > 1 or temperature >= 35 or moisture <= 20
            else "No configured warning threshold triggered",
            "findings": findings,
            "limitations": (
                "Preliminary screening only. Thresholds are generic, not "
                "crop-specific diagnoses. Soil-moisture percentages depend "
                "on the sensor and soil. Confirm readings and consider "
                "crop variety, growth stage, and local conditions."
            ),
        }

        return json.dumps(result, indent=2)
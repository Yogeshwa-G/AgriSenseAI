"""Current conditions and short-term weather forecast for AgriSenseAI.

Uses the Open-Meteo Geocoding and Forecast APIs. No API key is required
for ordinary non-commercial use; retain the Open-Meteo attribution.
"""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tools import Tool


class WeatherForecast(Tool):
    name = "weather_forecast"
    description = (
        "Get current weather and a daily forecast for a named location. "
        "Use this for weather, rainfall, rain probability, temperature, "
        "humidity, wind and reference evapotranspiration forecast questions. "
        "Provide location and optionally days (1-7). This is forecast data, "
        "not a farm sensor reading or a guarantee of rainfall."
    )
    args_doc = '{"location": "Tiruchirappalli, Tamil Nadu, India", "days": 7}'

    @staticmethod
    def _get_json(url, params):
        query = urlencode(params, doseq=True)
        request = Request(
            f"{url}?{query}",
            headers={"User-Agent": "AgriSenseAI/1.0 (weather forecast tool)"},
        )
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _weather_description(code):
        descriptions = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            56: "Light freezing drizzle",
            57: "Dense freezing drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            66: "Light freezing rain",
            67: "Heavy freezing rain",
            71: "Slight snow fall",
            73: "Moderate snow fall",
            75: "Heavy snow fall",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail",
        }
        try:
            return descriptions.get(int(code), "Unknown weather condition")
        except (TypeError, ValueError):
            return "Unknown weather condition"

    def execute(self, location, days=7, **kwargs):
        location = str(location).strip()
        if not location:
            return "ERROR: Provide a town, city or location name."

        try:
            days = int(days)
        except (TypeError, ValueError):
            return "ERROR: days must be a whole number from 1 to 7."
        if not 1 <= days <= 7:
            return "ERROR: days must be between 1 and 7."

        try:
            # Resolve the place name to coordinates.
            geocoding = self._get_json(
                "https://geocoding-api.open-meteo.com/v1/search",
                {"name": location, "count": 5, "language": "en", "format": "json"},
            )
            matches = geocoding.get("results") or []
            if not matches:
                return (
                    f"ERROR: No matching location found for '{location}'. "
                    "Try a town/city followed by its state and country."
                )

            # Use the top geocoding match and return its full identity so the
            # caller can see which same-named place was selected.
            place = matches[0]
            latitude = float(place["latitude"])
            longitude = float(place["longitude"])

            forecast = self._get_json(
                "https://api.open-meteo.com/v1/forecast",
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "apparent_temperature",
                        "precipitation",
                        "rain",
                        "weather_code",
                        "wind_speed_10m",
                    ],
                    "daily": [
                        "weather_code",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_sum",
                        "precipitation_probability_max",
                        "wind_speed_10m_max",
                        "et0_fao_evapotranspiration",
                    ],
                    "forecast_days": days,
                    "timezone": "auto",
                    "temperature_unit": "celsius",
                    "wind_speed_unit": "kmh",
                    "precipitation_unit": "mm",
                },
            )

            current = forecast.get("current", {})
            current_units = forecast.get("current_units", {})
            daily = forecast.get("daily", {})
            daily_units = forecast.get("daily_units", {})

            daily_forecast = []
            date_values = daily.get("time", [])
            for index, forecast_date in enumerate(date_values):
                code_values = daily.get("weather_code", [])
                code = code_values[index] if index < len(code_values) else None
                item = {
                    "date": forecast_date,
                    "weather_code": code,
                    "condition": self._weather_description(code),
                }
                for key in (
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                    "et0_fao_evapotranspiration",
                ):
                    values = daily.get(key, [])
                    item[key] = values[index] if index < len(values) else None
                daily_forecast.append(item)

            result = {
                "analysis": "Current Weather and Short-Term Forecast",
                "location": {
                    "requested": location,
                    "matched_name": place.get("name"),
                    "admin1": place.get("admin1"),
                    "country": place.get("country"),
                    "latitude": latitude,
                    "longitude": longitude,
                    "timezone": forecast.get("timezone"),
                },
                "current_conditions": {
                    "time": current.get("time"),
                    "temperature": current.get("temperature_2m"),
                    "temperature_unit": current_units.get("temperature_2m", "°C"),
                    "relative_humidity": current.get("relative_humidity_2m"),
                    "humidity_unit": current_units.get("relative_humidity_2m", "%"),
                    "apparent_temperature": current.get("apparent_temperature"),
                    "precipitation": current.get("precipitation"),
                    "rain": current.get("rain"),
                    "wind_speed": current.get("wind_speed_10m"),
                    "wind_speed_unit": current_units.get("wind_speed_10m", "km/h"),
                    "weather_code": current.get("weather_code"),
                    "condition": self._weather_description(current.get("weather_code")),
                },
                "daily_forecast": daily_forecast,
                "daily_units": daily_units,
                "data_source": "Open-Meteo (weather forecast and geocoding APIs)",
                "limitations": [
                    "Forecasts are model estimates and can change; they are not guaranteed observations.",
                    "Rainfall amounts are forecast precipitation totals in millimetres.",
                    "Use the forecast alongside on-farm sensor readings; do not treat it as a direct irrigation command.",
                    "The first geocoding match is selected automatically; check the returned matched location.",
                ],
            }
            return json.dumps(result, indent=2, ensure_ascii=False)

        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            return f"ERROR: Weather service returned HTTP {exc.code}: {detail}"
        except (URLError, TimeoutError) as exc:
            return f"ERROR: Could not connect to the weather service: {exc}"
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return f"ERROR: Could not process weather response: {exc}"
        except OSError as exc:
            return f"ERROR: Weather request failed: {exc}"

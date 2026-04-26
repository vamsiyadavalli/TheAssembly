from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import requests

_WMO_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Moderate showers",
    82: "Heavy showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ hail",
    99: "Thunderstorm w/ heavy hail",
}


def _wmo_description(code: int) -> str:
    return _WMO_CODES.get(code, "Unknown")


@dataclass(frozen=True)
class HourlyWeather:
    hour: int
    temperature: float
    feels_like: float
    precip_probability: int
    wind_speed: float
    weather_code: int

    @property
    def condition(self) -> str:
        return _wmo_description(self.weather_code)


@dataclass(frozen=True)
class WorkoutWeather:
    hours: tuple[HourlyWeather, ...]
    clothing_recommendation: str
    condition_summary: str


def get_clothing_recommendation(hours: list[HourlyWeather]) -> str:
    # Key off the 6am hour — closest to the 6:15am class start.
    reference = next((h for h in hours if h.hour == 6), None)
    if reference is None:
        reference = hours[0] if hours else None
    if reference is None:
        return "Weather data unavailable."

    feels = reference.feels_like

    if feels < 25:
        base = "Heavy coat, thermal base layer, hat, gloves, neck gaiter"
    elif feels < 35:
        base = "Insulated jacket, base layer, beanie, gloves"
    elif feels < 45:
        base = "Fleece or softshell jacket, long sleeves, gloves recommended"
    elif feels < 55:
        base = "Light jacket or hoodie, long sleeves, consider gloves"
    elif feels < 65:
        base = "T-shirt + light hoodie, leggings or shorts"
    elif feels < 75:
        base = "T-shirt + shorts"
    else:
        base = "Light and breathable clothing"

    modifiers: list[str] = []
    if reference.precip_probability > 50:
        modifiers.append("Waterproof layer recommended")
    if reference.wind_speed > 15:
        modifiers.append("Wind-resistant outer layer helps")

    if modifiers:
        return f"{base}. {' · '.join(modifiers)}."
    return f"{base}."


def fetch_workout_weather(
    lat: float,
    lon: float,
    target_date: date,
    timezone_name: str,
) -> WorkoutWeather | None:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,apparent_temperature,precipitation_probability,wind_speed_10m,weather_code",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": timezone_name,
        "forecast_days": 3,
    }

    try:
        response = requests.get(url, params=params, timeout=8)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    try:
        times: list[str] = data["hourly"]["time"]
        temps: list[float] = data["hourly"]["temperature_2m"]
        feels: list[float] = data["hourly"]["apparent_temperature"]
        precip_probs: list[int | None] = data["hourly"]["precipitation_probability"]
        winds: list[float] = data["hourly"]["wind_speed_10m"]
        codes: list[int] = data["hourly"]["weather_code"]
    except (KeyError, TypeError):
        return None

    target_str = target_date.isoformat()
    workout_hours: list[HourlyWeather] = []

    for i, time_str in enumerate(times):
        if not time_str.startswith(target_str):
            continue
        try:
            hour = int(time_str[11:13])
        except (ValueError, IndexError):
            continue
        if hour not in (5, 6, 7, 8):
            continue
        workout_hours.append(
            HourlyWeather(
                hour=hour,
                temperature=round(float(temps[i]), 1),
                feels_like=round(float(feels[i]), 1),
                precip_probability=int(precip_probs[i]) if precip_probs[i] is not None else 0,
                wind_speed=round(float(winds[i]), 1),
                weather_code=int(codes[i]),
            )
        )

    if not workout_hours:
        return None

    clothing = get_clothing_recommendation(workout_hours)

    # Use the 6am condition as the headline summary, fall back to the first hour.
    six_am = next((h for h in workout_hours if h.hour == 6), workout_hours[0])
    condition_summary = six_am.condition

    return WorkoutWeather(
        hours=tuple(workout_hours),
        clothing_recommendation=clothing,
        condition_summary=condition_summary,
    )

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from theassembly.weather import (
    HourlyWeather,
    WorkoutWeather,
    _wmo_description,
    fetch_workout_weather,
    get_clothing_recommendation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hour(h: int, temp: float, feels: float, precip: int = 0, wind: float = 5.0, code: int = 0) -> HourlyWeather:
    return HourlyWeather(hour=h, temperature=temp, feels_like=feels, precip_probability=precip, wind_speed=wind, weather_code=code)


def _hours_at_6(feels: float, precip: int = 0, wind: float = 5.0) -> list[HourlyWeather]:
    """Return a minimal list with only a 6am entry."""
    return [_hour(6, feels + 2, feels, precip=precip, wind=wind)]


# ---------------------------------------------------------------------------
# _wmo_description
# ---------------------------------------------------------------------------

class TestWmoDescription:
    def test_clear_sky(self):
        assert _wmo_description(0) == "Clear sky"

    def test_partly_cloudy(self):
        assert _wmo_description(2) == "Partly cloudy"

    def test_moderate_rain(self):
        assert _wmo_description(63) == "Moderate rain"

    def test_heavy_snow(self):
        assert _wmo_description(75) == "Heavy snow"

    def test_thunderstorm(self):
        assert _wmo_description(95) == "Thunderstorm"

    def test_unknown_code_returns_unknown(self):
        assert _wmo_description(999) == "Unknown"


# ---------------------------------------------------------------------------
# get_clothing_recommendation — temperature bands
# ---------------------------------------------------------------------------

class TestClothingRecommendation:
    def test_extreme_cold_below_25(self):
        rec = get_clothing_recommendation(_hours_at_6(20.0))
        assert "Heavy coat" in rec
        assert "thermal base layer" in rec
        assert "neck gaiter" in rec

    def test_cold_25_to_35(self):
        rec = get_clothing_recommendation(_hours_at_6(30.0))
        assert "Insulated jacket" in rec
        assert "beanie" in rec
        assert "gloves" in rec

    def test_cool_35_to_45(self):
        rec = get_clothing_recommendation(_hours_at_6(40.0))
        assert "Fleece" in rec
        assert "long sleeves" in rec

    def test_mild_45_to_55(self):
        rec = get_clothing_recommendation(_hours_at_6(50.0))
        assert "Light jacket" in rec or "hoodie" in rec
        assert "long sleeves" in rec

    def test_comfortable_55_to_65(self):
        rec = get_clothing_recommendation(_hours_at_6(60.0))
        assert "T-shirt" in rec
        assert "hoodie" in rec

    def test_warm_65_to_75(self):
        rec = get_clothing_recommendation(_hours_at_6(70.0))
        assert "T-shirt" in rec
        assert "shorts" in rec

    def test_hot_above_75(self):
        rec = get_clothing_recommendation(_hours_at_6(80.0))
        assert "breathable" in rec.lower()

    def test_rain_modifier_above_50pct(self):
        rec = get_clothing_recommendation(_hours_at_6(60.0, precip=55))
        assert "Waterproof" in rec

    def test_no_rain_modifier_at_50pct(self):
        rec = get_clothing_recommendation(_hours_at_6(60.0, precip=50))
        assert "Waterproof" not in rec

    def test_wind_modifier_above_15mph(self):
        rec = get_clothing_recommendation(_hours_at_6(60.0, wind=16.0))
        assert "Wind-resistant" in rec

    def test_no_wind_modifier_at_15mph(self):
        rec = get_clothing_recommendation(_hours_at_6(60.0, wind=15.0))
        assert "Wind-resistant" not in rec

    def test_both_modifiers_combined(self):
        rec = get_clothing_recommendation(_hours_at_6(60.0, precip=70, wind=20.0))
        assert "Waterproof" in rec
        assert "Wind-resistant" in rec

    def test_falls_back_to_first_hour_when_no_6am(self):
        hours = [_hour(5, 42.0, 38.0)]
        rec = get_clothing_recommendation(hours)
        assert "Fleece" in rec

    def test_empty_hours_returns_unavailable(self):
        rec = get_clothing_recommendation([])
        assert "unavailable" in rec.lower()


# ---------------------------------------------------------------------------
# fetch_workout_weather — mocked HTTP
# ---------------------------------------------------------------------------

def _make_open_meteo_response(target_date: str, extra_hours: list[int] | None = None) -> dict:
    """Build a minimal Open-Meteo JSON body."""
    target_hours = [5, 6, 7, 8]
    all_hours = target_hours + (extra_hours or [])

    times, temps, feels, precips, winds, codes = [], [], [], [], [], []
    for h in all_hours:
        times.append(f"{target_date}T{h:02d}:00")
        temps.append(55.0 + h)
        feels.append(50.0 + h)
        precips.append(10)
        winds.append(8.0)
        codes.append(1)

    # Add an entry for a different date to test filtering
    times.append("2099-01-01T06:00")
    temps.append(99.0)
    feels.append(99.0)
    precips.append(0)
    winds.append(0.0)
    codes.append(0)

    return {
        "hourly": {
            "time": times,
            "temperature_2m": temps,
            "apparent_temperature": feels,
            "precipitation_probability": precips,
            "wind_speed_10m": winds,
            "weather_code": codes,
        }
    }


class TestFetchWorkoutWeather:
    def _mock_get(self, payload: dict) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = payload
        return mock_resp

    def test_returns_four_hours_for_target_date(self):
        target = date(2026, 4, 26)
        payload = _make_open_meteo_response("2026-04-26")
        with patch("theassembly.weather.requests.get", return_value=self._mock_get(payload)):
            result = fetch_workout_weather(39.3448, -77.3241, target, "America/New_York")
        assert result is not None
        assert len(result.hours) == 4
        assert {h.hour for h in result.hours} == {5, 6, 7, 8}

    def test_excludes_non_target_hours(self):
        target = date(2026, 4, 26)
        # Add hours 0 and 12 to the payload — they must not appear in the result.
        payload = _make_open_meteo_response("2026-04-26", extra_hours=[0, 12])
        with patch("theassembly.weather.requests.get", return_value=self._mock_get(payload)):
            result = fetch_workout_weather(39.3448, -77.3241, target, "America/New_York")
        assert result is not None
        for h in result.hours:
            assert h.hour in (5, 6, 7, 8)

    def test_excludes_different_date_entries(self):
        target = date(2026, 4, 26)
        payload = _make_open_meteo_response("2026-04-26")
        with patch("theassembly.weather.requests.get", return_value=self._mock_get(payload)):
            result = fetch_workout_weather(39.3448, -77.3241, target, "America/New_York")
        assert result is not None
        # The 2099 entry in the mock payload must be excluded.
        for h in result.hours:
            assert h.hour in (5, 6, 7, 8)

    def test_returns_none_on_request_exception(self):
        target = date(2026, 4, 26)
        with patch("theassembly.weather.requests.get", side_effect=Exception("network error")):
            result = fetch_workout_weather(39.3448, -77.3241, target, "America/New_York")
        assert result is None

    def test_returns_none_on_http_error(self):
        target = date(2026, 4, 26)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("500 Server Error")
        with patch("theassembly.weather.requests.get", return_value=mock_resp):
            result = fetch_workout_weather(39.3448, -77.3241, target, "America/New_York")
        assert result is None

    def test_returns_none_when_no_matching_hours(self):
        target = date(2026, 4, 27)
        # Payload only has data for 2026-04-26, not 2026-04-27.
        payload = _make_open_meteo_response("2026-04-26")
        with patch("theassembly.weather.requests.get", return_value=self._mock_get(payload)):
            result = fetch_workout_weather(39.3448, -77.3241, target, "America/New_York")
        assert result is None

    def test_clothing_recommendation_included(self):
        target = date(2026, 4, 26)
        payload = _make_open_meteo_response("2026-04-26")
        with patch("theassembly.weather.requests.get", return_value=self._mock_get(payload)):
            result = fetch_workout_weather(39.3448, -77.3241, target, "America/New_York")
        assert result is not None
        assert result.clothing_recommendation
        assert len(result.clothing_recommendation) > 5

    def test_condition_summary_from_6am(self):
        target = date(2026, 4, 26)
        payload = _make_open_meteo_response("2026-04-26")
        with patch("theassembly.weather.requests.get", return_value=self._mock_get(payload)):
            result = fetch_workout_weather(39.3448, -77.3241, target, "America/New_York")
        assert result is not None
        assert result.condition_summary == "Mainly clear"  # code=1

    def test_precip_probability_none_treated_as_zero(self):
        target = date(2026, 4, 26)
        payload = _make_open_meteo_response("2026-04-26")
        # Set all precip values to None to simulate missing data.
        payload["hourly"]["precipitation_probability"] = [None] * len(payload["hourly"]["time"])
        with patch("theassembly.weather.requests.get", return_value=self._mock_get(payload)):
            result = fetch_workout_weather(39.3448, -77.3241, target, "America/New_York")
        assert result is not None
        for h in result.hours:
            assert h.precip_probability == 0

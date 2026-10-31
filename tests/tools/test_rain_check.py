"""Tests for the rain_check tool."""

from typing import Any
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import httpx
import pytest

from morning_briefing.tools import rain_check
from morning_briefing.tools.rain_check import RainCheck, home_coordinates, summarize_forecast


NOW = datetime(2026, 10, 31, 6, 0, tzinfo=timezone.utc)  # 07:00 in Oslo (CET)


def _hour(offset_hours: int, temperature: float, rain_mm: float, symbol: str, wind: float = 3.0) -> dict[str, Any]:
    return {
        "time": (NOW + timedelta(hours=offset_hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": {
            "instant": {"details": {"air_temperature": temperature, "wind_speed": wind}},
            "next_1_hours": {"summary": {"symbol_code": symbol}, "details": {"precipitation_amount": rain_mm}},
        },
    }


def _payload(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"properties": {"timeseries": list(entries)}}


def test_dry_morning_needs_no_umbrella() -> None:
    """Trace amounts below both thresholds do not trigger the umbrella."""
    result = summarize_forecast(_payload(_hour(0, 8.0, 0.0, "cloudy"), _hour(1, 9.5, 0.1, "cloudy")), NOW, hours=3)

    assert result["umbrella_needed"] is False
    assert result["first_rain_at"] is None
    assert result["total_precipitation_mm"] == 0.1
    assert (result["temperature_now_c"], result["temperature_min_c"], result["temperature_max_c"]) == (8.0, 8.0, 9.5)
    assert result["conditions"] == ["cloudy"]


def test_rain_later_sets_umbrella_and_local_start_time() -> None:
    """The first wet hour is reported in Oslo time and the totals are summed."""
    result = summarize_forecast(
        _payload(_hour(0, 8.0, 0.0, "cloudy"), _hour(2, 8.0, 0.6, "lightrain"), _hour(3, 7.0, 1.4, "rain", wind=9.2)),
        NOW,
        hours=6,
    )

    assert result["umbrella_needed"] is True
    assert result["first_rain_at"] == "09:00"
    assert result["total_precipitation_mm"] == 2.0
    assert result["max_hourly_precipitation_mm"] == 1.4
    assert result["max_wind_speed_ms"] == 9.2
    assert result["conditions"] == ["cloudy", "lightrain", "rain"]


def test_window_excludes_hours_beyond_request() -> None:
    """Rain after the requested window does not count."""
    result = summarize_forecast(
        _payload(_hour(0, 8.0, 0.0, "fair_day"), _hour(5, 8.0, 5.0, "heavyrain")), NOW, hours=4
    )

    assert result["umbrella_needed"] is False
    assert result["conditions"] == ["fair_day"]


def test_empty_or_stale_forecast_is_an_error() -> None:
    """Missing timeseries or one entirely outside the window is reported as an error."""
    assert "error" in summarize_forecast({"properties": {}}, NOW)
    assert "error" in summarize_forecast(_payload(_hour(-6, 8.0, 0.0, "cloudy")), NOW, hours=2)


def test_home_coordinates_env_override_rounds_to_met_precision(monkeypatch: pytest.MonkeyPatch) -> None:
    """Coordinates come from the environment and are rounded to four decimals."""
    monkeypatch.setenv("MORNING_BRIEFING_LATITUDE", "60.123456")
    monkeypatch.setenv("MORNING_BRIEFING_LONGITUDE", "5.0")
    assert home_coordinates() == (60.1235, 5.0)
    monkeypatch.delenv("MORNING_BRIEFING_LATITUDE")
    monkeypatch.delenv("MORNING_BRIEFING_LONGITUDE")
    assert home_coordinates() == (rain_check.DEFAULT_LATITUDE, rain_check.DEFAULT_LONGITUDE)


@pytest.mark.asyncio
async def test_tool_clamps_hours_and_summarizes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tool fetches the home point and clamps the requested horizon."""
    seen: list[tuple[float, float]] = []

    async def fake_fetch(latitude: float, longitude: float) -> dict[str, Any]:
        seen.append((latitude, longitude))
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        return _payload({**_hour(0, 5.0, 0.0, "clearsky_day"), "time": now.strftime("%Y-%m-%dT%H:%M:%SZ")})

    monkeypatch.setattr(rain_check, "fetch_forecast", fake_fetch)
    monkeypatch.delenv("MORNING_BRIEFING_LATITUDE", raising=False)
    monkeypatch.delenv("MORNING_BRIEFING_LONGITUDE", raising=False)

    result = await RainCheck()(MagicMock(), hours=500)

    assert seen == [(rain_check.DEFAULT_LATITUDE, rain_check.DEFAULT_LONGITUDE)]
    assert result["hours"] == rain_check.MAX_HOURS
    assert result["umbrella_needed"] is False


@pytest.mark.asyncio
async def test_tool_reports_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP errors become an error payload."""

    async def failing_fetch(latitude: float, longitude: float) -> dict[str, Any]:
        raise httpx.HTTPStatusError("429", request=MagicMock(), response=MagicMock())

    monkeypatch.setattr(rain_check, "fetch_forecast", failing_fetch)

    result = await RainCheck()(MagicMock())

    assert "error" in result
    assert "MET" in result["error"]

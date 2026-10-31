"""Rain and umbrella check from MET Norway's Locationforecast API."""

import os
import logging
from typing import Any
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import httpx

from morning_briefing.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

MET_FORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
# MET's terms require an identifying User-Agent with a way to contact the operator.
MET_USER_AGENT = "morning_briefing/0.1 https://github.com/alavesa"
LATITUDE_ENV = "MORNING_BRIEFING_LATITUDE"
LONGITUDE_ENV = "MORNING_BRIEFING_LONGITUDE"
DEFAULT_LATITUDE = 58.9664  # Lervigbrygga, Stavanger
DEFAULT_LONGITUDE = 5.7641
LOCAL_TIMEZONE = ZoneInfo("Europe/Oslo")
MAX_HOURS = 48
_DEFAULT_HOURS = 12
_REQUEST_TIMEOUT_S = 10.0
# Thresholds, mm: a wet hour you would notice, and a day total worth carrying an umbrella for.
UMBRELLA_HOURLY_MM = 0.3
UMBRELLA_TOTAL_MM = 1.0


def home_coordinates() -> tuple[float, float]:
    """Return the configured forecast coordinates, rounded as MET requires."""
    latitude = float(os.getenv(LATITUDE_ENV, "").strip() or DEFAULT_LATITUDE)
    longitude = float(os.getenv(LONGITUDE_ENV, "").strip() or DEFAULT_LONGITUDE)
    return round(latitude, 4), round(longitude, 4)


def summarize_forecast(payload: dict[str, Any], now: datetime, hours: int = _DEFAULT_HOURS) -> dict[str, Any]:
    """Reduce a Locationforecast compact response to the next hours' rain, temperature and wind."""
    timeseries = payload.get("properties", {}).get("timeseries")
    if not isinstance(timeseries, list) or not timeseries:
        return {"error": "forecast response had no timeseries"}

    window_end = now + timedelta(hours=hours)
    total_mm = 0.0
    max_hourly_mm = 0.0
    first_rain_at: str | None = None
    temperatures: list[float] = []
    max_wind = 0.0
    symbols: list[str] = []
    for entry in timeseries:
        at = datetime.fromisoformat(entry["time"])
        # Keep the hour that already started so "right now" is covered.
        if at < now - timedelta(hours=1) or at >= window_end:
            continue
        instant = entry.get("data", {}).get("instant", {}).get("details", {})
        if (temperature := instant.get("air_temperature")) is not None:
            temperatures.append(float(temperature))
        max_wind = max(max_wind, float(instant.get("wind_speed") or 0.0))

        next_hour = entry.get("data", {}).get("next_1_hours")
        if not next_hour:
            continue
        rain_mm = float(next_hour.get("details", {}).get("precipitation_amount") or 0.0)
        total_mm += rain_mm
        max_hourly_mm = max(max_hourly_mm, rain_mm)
        if rain_mm >= UMBRELLA_HOURLY_MM and first_rain_at is None:
            first_rain_at = at.astimezone(LOCAL_TIMEZONE).strftime("%H:%M")
        if symbol := next_hour.get("summary", {}).get("symbol_code"):
            symbols.append(symbol)

    if not temperatures and not symbols:
        return {"error": "forecast does not cover the requested hours"}

    return {
        "hours": hours,
        "umbrella_needed": max_hourly_mm >= UMBRELLA_HOURLY_MM or total_mm >= UMBRELLA_TOTAL_MM,
        "total_precipitation_mm": round(total_mm, 1),
        "max_hourly_precipitation_mm": round(max_hourly_mm, 1),
        "first_rain_at": first_rain_at,
        "temperature_now_c": temperatures[0] if temperatures else None,
        "temperature_min_c": min(temperatures) if temperatures else None,
        "temperature_max_c": max(temperatures) if temperatures else None,
        "max_wind_speed_ms": round(max_wind, 1),
        "conditions": sorted(set(symbols), key=symbols.index),
    }


async def fetch_forecast(latitude: float, longitude: float) -> dict[str, Any]:
    """Download the compact forecast for one point."""
    headers = {"User-Agent": MET_USER_AGENT}
    params = {"lat": f"{latitude:.4f}", "lon": f"{longitude:.4f}"}
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S, headers=headers) as client:
        response = await client.get(MET_FORECAST_URL, params=params)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    return payload


class RainCheck(Tool):
    """Tell whether the user should bring an umbrella."""

    name = "rain_check"
    description = (
        "Check the MET Norway forecast at home (Stavanger) for the coming hours: whether an umbrella is needed, "
        "when rain starts, expected precipitation, temperature range and wind."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "hours": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_HOURS,
                "description": f"How many hours ahead to look (default {_DEFAULT_HOURS}).",
            },
        },
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Fetch the forecast and summarize the rain outlook."""
        hours = min(MAX_HOURS, max(1, int(kwargs.get("hours") or _DEFAULT_HOURS)))
        latitude, longitude = home_coordinates()
        logger.info("Tool call: rain_check lat=%s lon=%s hours=%d", latitude, longitude, hours)
        try:
            payload = await fetch_forecast(latitude, longitude)
        except (httpx.HTTPError, ValueError) as e:
            logger.error("rain_check failed: %s", e)
            return {"error": f"could not reach MET Norway: {e}"}
        return summarize_forecast(payload, datetime.now(timezone.utc), hours)

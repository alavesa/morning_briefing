"""Next bus departures from the home stop, read from Entur's JourneyPlanner API."""

import os
import logging
from typing import Any
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from morning_briefing.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

ENTUR_GRAPHQL_URL = "https://api.entur.io/journey-planner/v3/graphql"
# Entur asks every client to identify itself; the value is free-form.
ENTUR_CLIENT_NAME = "alavesa-morning_briefing"
STOP_PLACE_ID_ENV = "MORNING_BRIEFING_STOP_PLACE_ID"
DEFAULT_STOP_PLACE_ID = "NSR:StopPlace:27111"  # Lervigsveien, Stavanger (line 12)
LOCAL_TIMEZONE = ZoneInfo("Europe/Oslo")
MAX_DEPARTURES = 10
_DEFAULT_DEPARTURES = 3
_LOOKAHEAD_S = 2 * 3600
_REQUEST_TIMEOUT_S = 10.0

_DEPARTURES_QUERY = """
query NextDepartures($stopPlaceId: String!, $count: Int!, $timeRange: Int!) {
  stopPlace(id: $stopPlaceId) {
    name
    estimatedCalls(numberOfDepartures: $count, timeRange: $timeRange) {
      expectedDepartureTime
      realtime
      cancellation
      destinationDisplay { frontText }
      serviceJourney { line { publicCode transportMode } }
      quay { publicCode }
    }
  }
}
"""


def home_stop_place_id() -> str:
    """Return the configured NSR stop place id, defaulting to Lervigsveien."""
    return os.getenv(STOP_PLACE_ID_ENV, "").strip() or DEFAULT_STOP_PLACE_ID


def summarize_departures(
    payload: dict[str, Any],
    now: datetime,
    destination: str | None = None,
    count: int = _DEFAULT_DEPARTURES,
) -> dict[str, Any]:
    """Turn an Entur stopPlace response into a short spoken-friendly departure list."""
    stop_place = payload.get("data", {}).get("stopPlace")
    if not isinstance(stop_place, dict):
        return {"error": "unknown stop place; check MORNING_BRIEFING_STOP_PLACE_ID"}

    wanted = destination.strip().lower() if destination else ""
    departures: list[dict[str, Any]] = []
    for call in stop_place.get("estimatedCalls", []):
        if call.get("cancellation"):
            continue
        front_text = (call.get("destinationDisplay") or {}).get("frontText") or ""
        if wanted and wanted not in front_text.lower():
            continue
        departs_at = datetime.fromisoformat(call["expectedDepartureTime"])
        in_minutes = max(0, int((departs_at - now).total_seconds() // 60))
        line = (call.get("serviceJourney") or {}).get("line") or {}
        departures.append(
            {
                "line": line.get("publicCode"),
                "mode": line.get("transportMode"),
                "destination": front_text,
                "quay": (call.get("quay") or {}).get("publicCode"),
                "departs_at": departs_at.astimezone(LOCAL_TIMEZONE).strftime("%H:%M"),
                "in_minutes": in_minutes,
                "realtime": bool(call.get("realtime")),
            }
        )
        if len(departures) >= count:
            break

    result: dict[str, Any] = {"stop": stop_place.get("name"), "departures": departures}
    if not departures:
        result["note"] = (
            f"no departures towards {destination!r} in the next two hours"
            if wanted
            else "no departures in the next two hours"
        )
    return result


async def fetch_departures(stop_place_id: str, count: int) -> dict[str, Any]:
    """Query Entur for the upcoming calls at one stop place."""
    headers = {"ET-Client-Name": ENTUR_CLIENT_NAME}
    body = {
        "query": _DEPARTURES_QUERY,
        "variables": {"stopPlaceId": stop_place_id, "count": count, "timeRange": _LOOKAHEAD_S},
    }
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S, headers=headers) as client:
        response = await client.post(ENTUR_GRAPHQL_URL, json=body)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    if payload.get("errors"):
        raise httpx.HTTPError(f"Entur GraphQL error: {payload['errors'][0].get('message', 'unknown')}")
    return payload


class NextBus(Tool):
    """Report the next bus departures from the user's home stop."""

    name = "next_bus"
    description = (
        "Get the next bus departures from the user's home stop (Lervigbrygga area, Stavanger) with live "
        "Entur times. Optionally filter by destination, e.g. 'Madlakrossen' for town or 'Rosenli'."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": "Optional destination text to filter on, matched against the bus front display.",
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_DEPARTURES,
                "description": f"How many departures to return (default {_DEFAULT_DEPARTURES}).",
            },
        },
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Fetch and summarize the upcoming departures."""
        destination = kwargs.get("destination") or None
        count = min(MAX_DEPARTURES, max(1, int(kwargs.get("count") or _DEFAULT_DEPARTURES)))
        stop_place_id = home_stop_place_id()
        logger.info("Tool call: next_bus stop=%s destination=%s count=%d", stop_place_id, destination, count)
        try:
            # Ask for the full lookahead so a destination filter still has candidates to pick from.
            payload = await fetch_departures(stop_place_id, MAX_DEPARTURES)
        except (httpx.HTTPError, ValueError) as e:
            logger.error("next_bus failed: %s", e)
            return {"error": f"could not reach Entur: {e}"}
        return summarize_departures(payload, datetime.now(timezone.utc), destination, count)

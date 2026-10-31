"""Tests for the next_bus tool."""

from typing import Any
from datetime import datetime, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from morning_briefing.tools import next_bus
from morning_briefing.tools.next_bus import NextBus, home_stop_place_id, summarize_departures


NOW = datetime(2026, 10, 31, 12, 50, tzinfo=timezone.utc)  # 13:50 in Oslo (CET)


def _call(departure: str, line: str, destination: str, quay: str, cancelled: bool = False) -> dict[str, Any]:
    return {
        "expectedDepartureTime": departure,
        "realtime": True,
        "cancellation": cancelled,
        "destinationDisplay": {"frontText": destination},
        "serviceJourney": {"line": {"publicCode": line, "transportMode": "bus"}},
        "quay": {"publicCode": quay},
    }


PAYLOAD = {
    "data": {
        "stopPlace": {
            "name": "Lervigsveien",
            "estimatedCalls": [
                _call("2026-10-31T13:55:00+01:00", "12", "Madlakrossen via Tjensvoll", "B"),
                _call("2026-10-31T13:56:00+01:00", "12", "Rosenli", "A", cancelled=True),
                _call("2026-10-31T14:11:00+01:00", "12", "Madlakrossen via Madlamark", "B"),
                _call("2026-10-31T14:12:00+01:00", "12", "Rosenli", "A"),
            ],
        }
    }
}


def test_summarize_departures_skips_cancelled_and_formats_local_time() -> None:
    """Cancelled calls are dropped and times are reported as Oslo clock time plus minutes to go."""
    result = summarize_departures(PAYLOAD, NOW, count=3)

    assert result["stop"] == "Lervigsveien"
    assert [d["departs_at"] for d in result["departures"]] == ["13:55", "14:11", "14:12"]
    assert [d["in_minutes"] for d in result["departures"]] == [5, 21, 22]
    assert result["departures"][0] == {
        "line": "12",
        "mode": "bus",
        "destination": "Madlakrossen via Tjensvoll",
        "quay": "B",
        "departs_at": "13:55",
        "in_minutes": 5,
        "realtime": True,
    }


def test_summarize_departures_filters_destination_case_insensitively() -> None:
    """A destination filter keeps only matching front texts and respects count."""
    result = summarize_departures(PAYLOAD, NOW, destination="madla", count=1)

    assert [d["departs_at"] for d in result["departures"]] == ["13:55"]
    assert "note" not in result


def test_summarize_departures_reports_empty_filter_match() -> None:
    """No matching departure yields an explanatory note instead of an empty answer."""
    result = summarize_departures(PAYLOAD, NOW, destination="Sandnes")

    assert result["departures"] == []
    assert "Sandnes" in result["note"]


def test_summarize_departures_unknown_stop() -> None:
    """A null stopPlace from Entur is reported as a configuration error."""
    assert "error" in summarize_departures({"data": {"stopPlace": None}}, NOW)


def test_home_stop_place_id_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stop place can be changed through the environment."""
    monkeypatch.setenv("MORNING_BRIEFING_STOP_PLACE_ID", " NSR:StopPlace:27710 ")
    assert home_stop_place_id() == "NSR:StopPlace:27710"
    monkeypatch.delenv("MORNING_BRIEFING_STOP_PLACE_ID")
    assert home_stop_place_id() == next_bus.DEFAULT_STOP_PLACE_ID


@pytest.mark.asyncio
async def test_tool_returns_departures(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tool fetches the full lookahead once and applies count afterwards."""
    requested: list[tuple[str, int]] = []

    async def fake_fetch(stop_place_id: str, count: int) -> dict[str, Any]:
        requested.append((stop_place_id, count))
        return PAYLOAD

    monkeypatch.setattr(next_bus, "fetch_departures", fake_fetch)
    monkeypatch.delenv("MORNING_BRIEFING_STOP_PLACE_ID", raising=False)

    result = await NextBus()(MagicMock(), count=2)

    assert requested == [(next_bus.DEFAULT_STOP_PLACE_ID, next_bus.MAX_DEPARTURES)]
    assert len(result["departures"]) == 2
    assert result["stop"] == "Lervigsveien"


@pytest.mark.asyncio
async def test_tool_reports_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Network problems surface as an error payload, not an exception."""

    async def failing_fetch(stop_place_id: str, count: int) -> dict[str, Any]:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(next_bus, "fetch_departures", failing_fetch)

    result = await NextBus()(MagicMock())

    assert "error" in result
    assert "Entur" in result["error"]


def test_spec_is_valid_function_schema() -> None:
    """The tool spec exposes an object schema with no required parameters."""
    spec = NextBus().spec()
    assert spec["name"] == "next_bus"
    assert spec["parameters"]["type"] == "object"
    assert spec["parameters"]["required"] == []

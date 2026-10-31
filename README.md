---
title: Morning Briefing
emoji: ☕
colorFrom: yellow
colorTo: blue
sdk: static
pinned: false
tags:
  - reachy_mini
  - reachy_mini_python_app
---

# Morning Briefing

A Reachy Mini conversation app that gets you out the door in Stavanger: say good morning and the robot tells you
whether to bring an umbrella, when the next bus leaves and what is in the news.

Forked from the [Reachy Mini conversation app](https://github.com/pollen-robotics/reachy_mini_conversation_app)
with the `reachy-mini-app-assistant` conversation template. The original README is kept as `README_OLD.md`.

## What it does

| Tool | Source | What the robot says |
|------|--------|---------------------|
| `rain_check` | [MET Norway Locationforecast 2.0](https://api.met.no/weatherapi/locationforecast/2.0/documentation) | Umbrella or not, when rain starts, precipitation total, temperature range, wind for the coming hours (default 12). |
| `next_bus` | [Entur JourneyPlanner v3](https://developer.entur.org/pages-journeyplanner-journeyplanner) | Next departures from the home stop with live times, optionally filtered by destination. |
| `nrk_headlines` | [NRK top stories RSS](https://www.nrk.no/toppsaker.rss) | The leading headlines with one-sentence summaries, translated into the conversation language. |

The assistant prompt and enabled tools live in `profiles/_morning_briefing_locked_profile/profile.md`.
The robot's usual conversation tools (emotions, head moves, memory, volume, sleep) stay enabled.

## Configuration

Everything has a default for Lervigbrygga, Stavanger. Override in `.env` (see `.env.example`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `MORNING_BRIEFING_STOP_PLACE_ID` | `NSR:StopPlace:27111` (Lervigsveien) | Entur NSR stop place for `next_bus`. Nearby: `NSR:StopPlace:27710` Søilands gate, `NSR:StopPlace:27113` Lervigtunet. |
| `MORNING_BRIEFING_LATITUDE` / `MORNING_BRIEFING_LONGITUDE` | `58.9664` / `5.7641` | Forecast point for `rain_check`. |
| `MORNING_BRIEFING_NEWS_FEED_URL` | NRK top stories | Any RSS 2.0 feed for `nrk_headlines`. |

Speech runs on the Hugging Face realtime backend and needs no API key. `HF_TOKEN` is optional.

## Run it locally against the simulator

```bash
# terminal 1: simulated robot (macOS needs mjpython for the MuJoCo window)
mjpython -m reachy_mini.daemon.app.main --sim

# terminal 2: the app with its web UI at http://127.0.0.1:7860/
uv pip install -e .
python -m morning_briefing.main --ui --no-camera
```

## Install on the robot

Open **Reachy Mini Control → Applications → Discover Apps** and install *Morning Briefing* from this Space, or:

```bash
curl -X POST http://reachy-mini.local:8000/api/apps/install \
  -H "Content-Type: application/json" \
  -d '{"name": "morning_briefing", "source_kind": "hf_space", "url": "https://huggingface.co/spaces/<user>/morning_briefing"}'
```

## Development

```bash
uv pip install -e . pytest pytest-asyncio ruff mypy
ruff check . && ruff format --check . && mypy src/morning_briefing/tools
pytest tests/tools
```

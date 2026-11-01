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
whether to bring an umbrella, when the next bus leaves and what is in the news. Built for a two-person
household: it asks who is up and reads each person their own outlet. The robot answers to the name Jonathan.

Forked from the [Reachy Mini conversation app](https://github.com/pollen-robotics/reachy_mini_conversation_app)
with the `reachy-mini-app-assistant` conversation template. The original README is kept as `README_OLD.md`.

## What it does

| Tool | Source | What the robot says |
|------|--------|---------------------|
| `rain_check` | [MET Norway Locationforecast 2.0](https://api.met.no/weatherapi/locationforecast/2.0/documentation) | Umbrella or not, when rain starts, precipitation total, temperature range, wind for the coming hours (default 12). |
| `next_bus` | [Entur JourneyPlanner v3](https://developer.entur.org/pages-journeyplanner-journeyplanner) | Next departures from the home stop with live times, optionally filtered by destination. |
| `news_headlines` | [NRK](https://www.nrk.no/toppsaker.rss), [BBC News](https://feeds.bbci.co.uk/news/rss.xml), [BBC World](https://feeds.bbci.co.uk/news/world/rss.xml), [Yle](https://feeds.yle.fi/uutiset/v1/majorHeadlines/YLE_UUTISET.rss) or [Yle News](https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_NEWS) RSS | The leading headlines with one-sentence summaries, from the outlet the listener prefers, in the conversation language. CNN is left out because its RSS feeds stopped updating in 2023. |

The assistant prompt and enabled tools live in `profiles/_morning_briefing_locked_profile/profile.md`.
The robot's usual conversation tools (emotions, head moves, memory, volume, sleep) stay enabled.

## Configuration

Everything has a default for Lervigbrygga, Stavanger. Override in `.env` (see `.env.example`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `MORNING_BRIEFING_STOP_PLACE_ID` | `NSR:StopPlace:27111` (Lervigsveien) | Entur NSR stop place for `next_bus`. Nearby: `NSR:StopPlace:27710` Søilands gate, `NSR:StopPlace:27113` Lervigtunet. |
| `MORNING_BRIEFING_LATITUDE` / `MORNING_BRIEFING_LONGITUDE` | `58.9664` / `5.7641` | Forecast point for `rain_check`. |
| `MORNING_BRIEFING_NEWS_SOURCE` | `nrk` | Outlet for `news_headlines` when nobody asks for one: `nrk`, `bbc`, `bbc_world`, `yle` or `yle_news`. The profile itself maps each person to their outlet. |

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

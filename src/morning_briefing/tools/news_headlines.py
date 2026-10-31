"""Top news headlines from a chosen RSS source."""

import os
import logging
from typing import Any
from xml.etree import ElementTree

import httpx

from morning_briefing.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

# CNN is deliberately absent: its public RSS feeds stopped updating in 2023.
NEWS_SOURCES: dict[str, tuple[str, str]] = {
    "nrk": ("NRK", "https://www.nrk.no/toppsaker.rss"),
    "bbc": ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml"),
    "bbc_world": ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
}
DEFAULT_SOURCE_ENV = "MORNING_BRIEFING_NEWS_SOURCE"
DEFAULT_SOURCE = "nrk"
MAX_HEADLINES = 10
_DEFAULT_HEADLINES = 5
_REQUEST_TIMEOUT_S = 10.0


def default_news_source() -> str:
    """Return the configured default source key, falling back to NRK for unknown values."""
    configured = os.getenv(DEFAULT_SOURCE_ENV, "").strip().lower()
    if configured and configured not in NEWS_SOURCES:
        logger.warning("Unknown %s=%r, using %s", DEFAULT_SOURCE_ENV, configured, DEFAULT_SOURCE)
    return configured if configured in NEWS_SOURCES else DEFAULT_SOURCE


def parse_headlines(feed_xml: str, count: int = _DEFAULT_HEADLINES) -> list[dict[str, Any]]:
    """Extract the first items of an RSS 2.0 feed as title, summary, categories and link."""
    channel = ElementTree.fromstring(feed_xml).find("channel")
    if channel is None:
        raise ValueError("feed has no RSS channel")

    headlines: list[dict[str, Any]] = []
    for item in channel.iterfind("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        headlines.append(
            {
                "title": title,
                "summary": " ".join((item.findtext("description") or "").split()),
                "categories": [category.text.strip() for category in item.iterfind("category") if category.text],
                "published": (item.findtext("pubDate") or "").strip() or None,
                "link": (item.findtext("link") or "").strip() or None,
            }
        )
        if len(headlines) >= count:
            break
    return headlines


async def fetch_feed(url: str) -> str:
    """Download the raw RSS document."""
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


class NewsHeadlines(Tool):
    """Read the current top headlines from NRK or the BBC."""

    name = "news_headlines"
    description = (
        "Get the current top news headlines with one-sentence summaries. Sources: 'nrk' (Norwegian public "
        "broadcaster, in Norwegian), 'bbc' (BBC News front page) or 'bbc_world' (BBC world news). Pick the source "
        "the listener prefers; translate or summarize into the conversation language."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": list(NEWS_SOURCES),
                "description": "Which outlet to read. Omit to use the household default.",
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_HEADLINES,
                "description": f"How many headlines to return (default {_DEFAULT_HEADLINES}).",
            },
        },
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Fetch the chosen feed and return the leading headlines."""
        source = str(kwargs.get("source") or default_news_source()).lower()
        if source not in NEWS_SOURCES:
            return {"error": f"unknown news source {source!r}; choose one of {', '.join(NEWS_SOURCES)}"}
        count = min(MAX_HEADLINES, max(1, int(kwargs.get("count") or _DEFAULT_HEADLINES)))
        display_name, url = NEWS_SOURCES[source]
        logger.info("Tool call: news_headlines source=%s count=%d", source, count)
        try:
            headlines = parse_headlines(await fetch_feed(url), count)
        except (httpx.HTTPError, ElementTree.ParseError, ValueError) as e:
            logger.error("news_headlines(%s) failed: %s", source, e)
            return {"error": f"could not read {display_name}: {e}"}
        return {"source": display_name, "headlines": headlines}

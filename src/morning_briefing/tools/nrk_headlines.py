"""Top news headlines from NRK's RSS feed."""

import os
import logging
from typing import Any
from xml.etree import ElementTree

import httpx

from morning_briefing.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

NEWS_FEED_URL_ENV = "MORNING_BRIEFING_NEWS_FEED_URL"
DEFAULT_NEWS_FEED_URL = "https://www.nrk.no/toppsaker.rss"
MAX_HEADLINES = 10
_DEFAULT_HEADLINES = 5
_REQUEST_TIMEOUT_S = 10.0


def news_feed_url() -> str:
    """Return the configured RSS feed, defaulting to NRK's top stories."""
    return os.getenv(NEWS_FEED_URL_ENV, "").strip() or DEFAULT_NEWS_FEED_URL


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


class NrkHeadlines(Tool):
    """Read the current top headlines from NRK."""

    name = "nrk_headlines"
    description = (
        "Get the current top news headlines from NRK (Norwegian public broadcaster), each with a one-sentence "
        "summary in Norwegian. Summarize or translate them for the user as the conversation language requires."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
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
        """Fetch the feed and return the leading headlines."""
        count = min(MAX_HEADLINES, max(1, int(kwargs.get("count") or _DEFAULT_HEADLINES)))
        url = news_feed_url()
        logger.info("Tool call: nrk_headlines url=%s count=%d", url, count)
        try:
            feed_xml = await fetch_feed(url)
            headlines = parse_headlines(feed_xml, count)
        except (httpx.HTTPError, ElementTree.ParseError, ValueError) as e:
            logger.error("nrk_headlines failed: %s", e)
            return {"error": f"could not read the news feed: {e}"}
        return {"source": "NRK", "headlines": headlines}

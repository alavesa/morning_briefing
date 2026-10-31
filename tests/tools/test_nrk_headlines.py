"""Tests for the nrk_headlines tool."""

from unittest.mock import MagicMock

import httpx
import pytest

from morning_briefing.tools import nrk_headlines
from morning_briefing.tools.nrk_headlines import NrkHeadlines, news_feed_url, parse_headlines


FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>NRK</title>
    <item>
      <title>Første sak</title>
      <link>https://www.nrk.no/1</link>
      <description>Linje én
        og linje to.</description>
      <category>Rogaland</category>
      <category>Politikk</category>
      <pubDate>Sat, 31 Oct 2026 05:55:40 GMT</pubDate>
    </item>
    <item>
      <title></title>
      <description>Item without a title is skipped.</description>
    </item>
    <item>
      <title>Andre sak</title>
      <description>Kort.</description>
    </item>
    <item>
      <title>Tredje sak</title>
    </item>
  </channel>
</rss>
"""


def test_parse_headlines_collapses_whitespace_and_skips_untitled_items() -> None:
    """Items map to title, summary, categories, date and link; untitled items are dropped."""
    headlines = parse_headlines(FEED, count=10)

    assert [h["title"] for h in headlines] == ["Første sak", "Andre sak", "Tredje sak"]
    assert headlines[0] == {
        "title": "Første sak",
        "summary": "Linje én og linje to.",
        "categories": ["Rogaland", "Politikk"],
        "published": "Sat, 31 Oct 2026 05:55:40 GMT",
        "link": "https://www.nrk.no/1",
    }
    assert headlines[2] == {"title": "Tredje sak", "summary": "", "categories": [], "published": None, "link": None}


def test_parse_headlines_respects_count() -> None:
    """Only the first count titled items are returned."""
    assert [h["title"] for h in parse_headlines(FEED, count=1)] == ["Første sak"]


def test_parse_headlines_rejects_non_rss() -> None:
    """A document without a channel is a feed error."""
    with pytest.raises(ValueError):
        parse_headlines("<html><body>not a feed</body></html>")


def test_news_feed_url_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """The feed URL can be swapped through the environment."""
    monkeypatch.setenv("MORNING_BRIEFING_NEWS_FEED_URL", "https://www.nrk.no/rogaland/toppsaker.rss")
    assert news_feed_url() == "https://www.nrk.no/rogaland/toppsaker.rss"
    monkeypatch.delenv("MORNING_BRIEFING_NEWS_FEED_URL")
    assert news_feed_url() == nrk_headlines.DEFAULT_NEWS_FEED_URL


@pytest.mark.asyncio
async def test_tool_returns_headlines(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tool downloads the configured feed and limits the result."""

    async def fake_fetch(url: str) -> str:
        assert url == nrk_headlines.DEFAULT_NEWS_FEED_URL
        return FEED

    monkeypatch.setattr(nrk_headlines, "fetch_feed", fake_fetch)
    monkeypatch.delenv("MORNING_BRIEFING_NEWS_FEED_URL", raising=False)

    result = await NrkHeadlines()(MagicMock(), count=2)

    assert result["source"] == "NRK"
    assert [h["title"] for h in result["headlines"]] == ["Første sak", "Andre sak"]


@pytest.mark.asyncio
async def test_tool_reports_bad_feed_and_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed XML and HTTP failures both become error payloads."""

    async def broken_feed(url: str) -> str:
        return "<rss><channel><item><title>unclosed"

    monkeypatch.setattr(nrk_headlines, "fetch_feed", broken_feed)
    assert "error" in await NrkHeadlines()(MagicMock())

    async def failing_fetch(url: str) -> str:
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(nrk_headlines, "fetch_feed", failing_fetch)
    assert "error" in await NrkHeadlines()(MagicMock())

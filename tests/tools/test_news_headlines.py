"""Tests for the news_headlines tool."""

from unittest.mock import MagicMock

import httpx
import pytest

from morning_briefing.tools import news_headlines
from morning_briefing.tools.news_headlines import NEWS_SOURCES, NewsHeadlines, parse_headlines, default_news_source


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


def test_default_news_source_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """The household default comes from the environment and ignores unknown outlets."""
    monkeypatch.setenv("MORNING_BRIEFING_NEWS_SOURCE", "BBC")
    assert default_news_source() == "bbc"
    monkeypatch.setenv("MORNING_BRIEFING_NEWS_SOURCE", "cnn")
    assert default_news_source() == "nrk"
    monkeypatch.delenv("MORNING_BRIEFING_NEWS_SOURCE")
    assert default_news_source() == news_headlines.DEFAULT_SOURCE


def test_spec_offers_every_source() -> None:
    """The LLM sees each configured outlet as an enum choice."""
    spec = NewsHeadlines().spec()
    assert spec["name"] == "news_headlines"
    assert spec["parameters"]["properties"]["source"]["enum"] == ["nrk", "bbc", "bbc_world", "yle", "yle_news"]
    assert set(spec["parameters"]["properties"]["source"]["enum"]) == set(NEWS_SOURCES)


@pytest.mark.asyncio
async def test_tool_reads_requested_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit source selects that outlet's feed and labels the result."""
    requested: list[str] = []

    async def fake_fetch(url: str) -> str:
        requested.append(url)
        return FEED

    monkeypatch.setattr(news_headlines, "fetch_feed", fake_fetch)

    result = await NewsHeadlines()(MagicMock(), source="bbc", count=2)

    assert requested == [NEWS_SOURCES["bbc"][1]]
    assert result["source"] == "BBC News"
    assert [h["title"] for h in result["headlines"]] == ["Første sak", "Andre sak"]


@pytest.mark.asyncio
async def test_tool_falls_back_to_household_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a source the environment default is used."""
    requested: list[str] = []

    async def fake_fetch(url: str) -> str:
        requested.append(url)
        return FEED

    monkeypatch.setattr(news_headlines, "fetch_feed", fake_fetch)
    monkeypatch.setenv("MORNING_BRIEFING_NEWS_SOURCE", "bbc_world")

    result = await NewsHeadlines()(MagicMock())

    assert requested == [NEWS_SOURCES["bbc_world"][1]]
    assert result["source"] == "BBC World"


@pytest.mark.asyncio
async def test_tool_rejects_unknown_source() -> None:
    """A source outside the enum is answered with an error, not a request."""
    result = await NewsHeadlines()(MagicMock(), source="cnn")
    assert "error" in result
    assert "cnn" in result["error"]


@pytest.mark.asyncio
async def test_tool_reports_bad_feed_and_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed XML and HTTP failures both become error payloads."""

    async def broken_feed(url: str) -> str:
        return "<rss><channel><item><title>unclosed"

    monkeypatch.setattr(news_headlines, "fetch_feed", broken_feed)
    assert "error" in await NewsHeadlines()(MagicMock())

    async def failing_fetch(url: str) -> str:
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(news_headlines, "fetch_feed", failing_fetch)
    assert "error" in await NewsHeadlines()(MagicMock())

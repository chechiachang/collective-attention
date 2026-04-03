"""
News Signal Agent

Counts the number of news articles matching an event's keywords and
builds a simple time series.

For the MVP this agent uses RSS feeds as the news source.  When an RSS
URL is provided it downloads the feed and counts articles whose titles
contain any of the event's keywords.  A fallback stub count is used
when no feed URL is configured or the request fails.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import requests

from core.models import Event

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10  # seconds

# Public RSS feeds that cover Taiwan news (Chinese)
DEFAULT_RSS_FEEDS: List[str] = [
    "https://www.cna.com.tw/rss/aall.aspx",  # CNA (Central News Agency)
    "https://news.ltn.com.tw/rss/all.xml",  # Liberty Times
]


class NewsSignalAgent:
    """
    Counts news articles matching event keywords.

    Parameters
    ----------
    rss_feeds : list of str, optional
        RSS feed URLs to poll.  Defaults to DEFAULT_RSS_FEEDS.
    fallback_count : int
        Article count to use when all feeds fail (for testing/offline use).
    """

    def __init__(
        self,
        rss_feeds: Optional[List[str]] = None,
        fallback_count: int = 0,
    ):
        self.rss_feeds = rss_feeds if rss_feeds is not None else DEFAULT_RSS_FEEDS
        self.fallback_count = fallback_count
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "CollectiveAttentionBot/1.0 (research project)"}
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, event: Event) -> None:
        """
        Populate event.signals.news_count.
        Modifies the event object in place.
        """
        if event.signals is None:
            return

        keywords = [kw.lower() for kw in event.keywords]
        if not keywords:
            event.signals.news_count = self.fallback_count
            return

        total = 0
        for feed_url in self.rss_feeds:
            count = self._count_articles(feed_url, keywords)
            total += count
            logger.debug(
                "NewsSignalAgent: '%s' count=%d from %s",
                event.title,
                count,
                feed_url,
            )

        if total == 0 and self.fallback_count:
            total = self.fallback_count

        event.signals.news_count = total
        logger.info("NewsSignalAgent: '%s' total news_count=%d", event.title, total)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _count_articles(self, feed_url: str, keywords: List[str]) -> int:
        """Count articles in `feed_url` whose titles contain any keyword."""
        try:
            import feedparser  # type: ignore

            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                title = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""
                text = title.lower() + " " + summary.lower()
                if any(kw in text for kw in keywords):
                    count += 1
            return count
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "NewsSignalAgent: feed fetch failed for %s: %s", feed_url, exc
            )
            return 0

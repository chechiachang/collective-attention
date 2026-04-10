"""
News Signal Agent

Counts the number of news articles matching an event's keywords and
builds a simple time series.

For the MVP this agent uses RSS feeds as the news source.  When an RSS
URL is provided it downloads the feed and counts articles whose titles
contain any of the event's keywords.  A fallback stub count is used
when no feed URL is configured or the request fails.

Improvements over v1:
  #1  GDELT DOC 2.0 fallback: when ``use_gdelt=True`` the agent queries
      the GDELT API for historical article counts keyed to the event
      date range.  This supplements RSS feeds with years of archive.
  #5  Article counts are cached to disk to avoid redundant fetches.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from json import JSONDecodeError
from typing import List, Optional

import requests

from core.cache import default_cache
from core.models import Event

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10  # seconds
_CACHE_AGENT = "news_signal"
WIKINEWS_API_URL = "https://{lang}.wikinews.org/w/api.php"

# GDELT DOC 2.0 API (improvement #1)
GDELT_API_URL = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
    "?query={query}&mode=artlist&format=json"
    "&startdatetime={start}&enddatetime={end}&maxrecords=250"
)
GDELT_TIMELINE_API_URL = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
    "?query={query}&mode=timelinevolraw&format=json"
    "&startdatetime={start}&enddatetime={end}"
)

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
    use_gdelt : bool
        When True, query the GDELT DOC 2.0 API for historical article
        counts keyed to the event date range (improvement #1).
        Supplements the RSS signal with years of archive data.
        Defaults to False for backward compatibility.
    use_cache : bool
        When True (default), persist article counts to disk (improvement #5).
    """

    def __init__(
        self,
        rss_feeds: Optional[List[str]] = None,
        fallback_count: int = 0,
        use_gdelt: bool = False,
        use_wikinews: bool = True,
        use_cache: bool = True,
    ):
        self.rss_feeds = rss_feeds if rss_feeds is not None else DEFAULT_RSS_FEEDS
        self.fallback_count = fallback_count
        self.use_gdelt = use_gdelt
        self.use_wikinews = use_wikinews
        self.use_cache = use_cache
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

        # Improvement #5 – check disk cache first
        date_key = f"{event.start_date}:{event.end_date}"
        cache_key = (
            f"{event.id}:{','.join(keywords)}:{date_key}:"
            f"gdelt={self.use_gdelt}:wikinews={self.use_wikinews}"
        )
        if self.use_cache:
            cached = default_cache.get(_CACHE_AGENT, cache_key)
            if cached is not None:
                event.signals.news_count = int(cached)
                logger.info(
                    "NewsSignalAgent: '%s' news_count=%d (cached)",
                    event.title,
                    event.signals.news_count,
                )
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

        # Improvement #1 – GDELT historical signal
        if self.use_gdelt:
            gdelt_count = self._count_gdelt(event)
            if gdelt_count:
                logger.info(
                    "NewsSignalAgent: '%s' gdelt_count=%d", event.title, gdelt_count
                )
                total += gdelt_count

        if self.use_wikinews:
            wikinews_count = self._count_wikinews(event)
            if wikinews_count:
                logger.info(
                    "NewsSignalAgent: '%s' wikinews_count=%d",
                    event.title,
                    wikinews_count,
                )
                total += wikinews_count

        if total == 0 and self.fallback_count:
            total = self.fallback_count

        event.signals.news_count = total
        logger.info("NewsSignalAgent: '%s' total news_count=%d", event.title, total)

        # Improvement #5 – persist to disk
        if self.use_cache:
            default_cache.set(_CACHE_AGENT, cache_key, total)

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

    def _count_gdelt(self, event: "Event") -> int:
        """
        Query the GDELT DOC 2.0 API for articles matching the primary
        keyword within the event date range (improvement #1).

        Returns the number of matched articles (capped at 250 by the API).
        Falls back to 0 on any failure.
        """
        keyword = event.keywords[0] if event.keywords else event.title
        start_dt = event.start_date or date(2014, 1, 1)
        end_dt = event.end_date or date.today()
        # GDELT requires at least 15 minutes; widen to ±7 days for single-day events
        window_start = start_dt - timedelta(days=7)
        window_end = end_dt + timedelta(days=7)
        start_str = window_start.strftime("%Y%m%d%H%M%S")
        end_str = window_end.strftime("%Y%m%d%H%M%S")

        import urllib.parse

        query_terms = event.keywords[:3] if event.keywords else [keyword]
        query = " OR ".join(f'"{term}"' for term in query_terms)
        url = GDELT_API_URL.format(
            query=urllib.parse.quote(query),
            start=start_str,
            end=end_str,
        )
        try:
            resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except (JSONDecodeError, ValueError) as exc:
                    logger.warning(
                        "NewsSignalAgent: GDELT returned non-JSON data for '%s': %s",
                        keyword,
                        exc,
                    )
                    data = {}
                articles = data.get("articles", [])
                if articles:
                    return len(articles)

            timeline_url = GDELT_TIMELINE_API_URL.format(
                query=urllib.parse.quote(query),
                start=start_str,
                end=end_str,
            )
            timeline_resp = self._session.get(timeline_url, timeout=REQUEST_TIMEOUT)
            if timeline_resp.status_code != 200:
                return 0
            timeline_data = timeline_resp.json()
            timeline = timeline_data.get("timeline", [])
            return sum(int(point.get("value", 0)) for point in timeline)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "NewsSignalAgent: GDELT fetch failed for '%s': %s", keyword, exc
            )
            return 0

    def _count_wikinews(self, event: Event) -> int:
        """Count archival Wikinews search hits as a secondary news proxy."""
        query_terms = event.keywords[:2] if event.keywords else [event.title]
        total_hits = 0
        for lang in ("zh", "en"):
            hits = self._wikinews_hits(lang, query_terms)
            total_hits += min(hits, 25)
        return total_hits

    def _wikinews_hits(self, lang: str, query_terms: List[str]) -> int:
        """Return total search hits from one Wikinews language edition."""
        query = " OR ".join(f'"{term}"' for term in query_terms)
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": "1",
            "format": "json",
        }
        url = WIKINEWS_API_URL.format(lang=lang)
        try:
            resp = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return 0
            data = resp.json()
            return int(data.get("query", {}).get("searchinfo", {}).get("totalhits", 0))
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "NewsSignalAgent: Wikinews search failed for '%s' (%s): %s",
                query,
                lang,
                exc,
            )
            return 0

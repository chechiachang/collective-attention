"""
Wikipedia Signal Agent

Fetches total pageviews for an event's canonical Wikipedia page
(and all its redirects) using the Wikimedia Pageviews REST API.

API docs: https://wikimedia.org/api/rest_v1/#/Pageviews%20data

Improvements over v1:
  #5  Pageview counts are cached to disk to avoid redundant API calls.
  #7  Optional English Wikipedia cross-lingual coverage: when
      ``include_en=True`` the agent also fetches en.wikipedia views,
      which improves recall for internationally notable events such as
      the COVID-19 pandemic.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from core.cache import default_cache
from core.models import Event

logger = logging.getLogger(__name__)

PAGEVIEWS_API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
    "/{project}/all-access/all-agents/{article}/monthly/{start}/{end}"
)
REQUEST_TIMEOUT = 10  # seconds
_CACHE_AGENT = "wiki_signal"
PAGEVIEWS_AVAILABLE_START = date(2015, 7, 1)


class WikiSignalAgent:
    """
    Fetches Wikimedia pageview data for an event.

    Parameters
    ----------
    lang : str
        Primary Wikipedia language edition (default "zh").
    include_en : bool
        When True, also fetch English Wikipedia views for events whose
        canonical title can be resolved in English (improvement #7).
        Helps avoid under-counting for internationally notable events.
    months_before : int
        How many months before event start_date to include (default 1).
    months_after : int
        How many months after event end_date to include (default 3).
    default_start : date
        Fallback start date when the event has no start_date.
    default_end : date
        Fallback end date when the event has no end_date.
    use_cache : bool
        When True (default), persist pageview counts to disk (improvement #5).
    """

    def __init__(
        self,
        lang: str = "zh",
        include_en: bool = True,
        months_before: int = 1,
        months_after: int = 3,
        default_start: date = date(2014, 1, 1),
        default_end: date = date(2024, 12, 31),
        use_cache: bool = True,
    ):
        self.lang = lang
        self.include_en = include_en
        self.months_before = months_before
        self.months_after = months_after
        self.default_start = default_start
        self.default_end = default_end
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
        Populate event.signals.wiki_views.
        Aggregates views across the canonical page and all redirect pages.
        Optionally adds English Wikipedia views (improvement #7).
        Modifies the event object in place.
        """
        if event.signals is None:
            return

        canonical = event.canonical_wiki_title
        if not canonical:
            logger.debug("WikiSignalAgent: no canonical title for '%s'", event.title)
            return

        start, end = self._date_range(event)
        pages = [canonical] + list(event.wiki_redirect_pages)

        total_views = 0
        for page in pages:
            views = self._fetch_pageviews_cached(page, self.lang, start, end)
            total_views += views
            logger.debug(
                "WikiSignalAgent: '%s' zh_views=%d (page=%s)", event.title, views, page
            )

        # Improvement #7 – cross-lingual: also count English Wikipedia views
        if self.include_en:
            en_views = self._fetch_en_views(event, start, end)
            if en_views:
                logger.info(
                    "WikiSignalAgent: '%s' en_wiki_views=%d", event.title, en_views
                )
                total_views += en_views

        event.signals.wiki_views = total_views
        logger.info(
            "WikiSignalAgent: '%s' total wiki_views=%d", event.title, total_views
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_en_views(self, event: Event, start: date, end: date) -> int:
        """
        Look up the English Wikipedia article for this event and return
        its pageviews.  Uses the first keyword as the search query.
        Falls back to 0 on any failure (improvement #7).
        """
        from agents.event_identity import EventIdentityAgent

        try:
            identity = EventIdentityAgent(lang="en")
            # Search using the first keyword (usually the most distinctive)
            query = event.keywords[0] if event.keywords else event.title
            canonical_en, _ = identity._resolve_title(query, "en")
            if not canonical_en:
                return 0
            views = self._fetch_pageviews_cached(canonical_en, "en", start, end)
            logger.debug(
                "WikiSignalAgent: '%s' en_page='%s' views=%d",
                event.title,
                canonical_en,
                views,
            )
            return views
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "WikiSignalAgent: en fallback failed for '%s': %s", event.title, exc
            )
            return 0

    def _date_range(self, event: Event) -> tuple[date, date]:
        start = event.start_date or self.default_start
        end = event.end_date or self.default_end

        # Expand range
        start = start - timedelta(days=30 * self.months_before)
        end = end + timedelta(days=30 * self.months_after)

        # Wikimedia pageviews do not exist before mid-2015. For older
        # events, fall back to the full available retrospective window
        # instead of returning a guaranteed zero.
        if end < PAGEVIEWS_AVAILABLE_START:
            return PAGEVIEWS_AVAILABLE_START, self.default_end

        if start < PAGEVIEWS_AVAILABLE_START:
            start = PAGEVIEWS_AVAILABLE_START

        return start, end

    def _fetch_pageviews_cached(
        self, title: str, lang: str, start: date, end: date
    ) -> int:
        """Return pageviews from cache when available (improvement #5)."""
        cache_key = f"{lang}:{title}:{start.isoformat()}:{end.isoformat()}"
        if self.use_cache:
            cached = default_cache.get(_CACHE_AGENT, cache_key)
            if cached is not None:
                return int(cached)

        views = self._fetch_pageviews(title, lang, start, end)

        if self.use_cache:
            default_cache.set(_CACHE_AGENT, cache_key, views)
        return views

    def _fetch_pageviews(self, title: str, lang: str, start: date, end: date) -> int:
        """Fetch total monthly pageviews for a single article."""
        import urllib.parse

        encoded_title = urllib.parse.quote(title.replace(" ", "_"), safe="")
        project = f"{lang}.wikipedia"
        url = PAGEVIEWS_API.format(
            project=project,
            article=encoded_title,
            start=start.strftime("%Y%m%d"),
            end=end.strftime("%Y%m%d"),
        )
        try:
            resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 404:
                return 0
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            return sum(item.get("views", 0) for item in items)
        except requests.RequestException as exc:
            logger.warning(
                "WikiSignalAgent: pageview fetch failed for '%s': %s", title, exc
            )
            return 0

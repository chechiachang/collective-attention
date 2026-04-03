"""
Wikipedia Signal Agent

Fetches total pageviews for an event's canonical Wikipedia page
(and all its redirects) using the Wikimedia Pageviews REST API.

API docs: https://wikimedia.org/api/rest_v1/#/Pageviews%20data
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from core.models import Event

logger = logging.getLogger(__name__)

PAGEVIEWS_API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
    "/{project}/all-access/all-agents/{article}/monthly/{start}/{end}"
)
REQUEST_TIMEOUT = 10  # seconds


class WikiSignalAgent:
    """
    Fetches Wikimedia pageview data for an event.

    Parameters
    ----------
    lang : str
        Wikipedia language edition (default "zh").
    months_before : int
        How many months before event start_date to include (default 1).
    months_after : int
        How many months after event end_date to include (default 3).
    default_start : date
        Fallback start date when the event has no start_date.
    default_end : date
        Fallback end date when the event has no end_date.
    """

    def __init__(
        self,
        lang: str = "zh",
        months_before: int = 1,
        months_after: int = 3,
        default_start: date = date(2014, 1, 1),
        default_end: date = date(2024, 12, 31),
    ):
        self.lang = lang
        self.months_before = months_before
        self.months_after = months_after
        self.default_start = default_start
        self.default_end = default_end
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
            views = self._fetch_pageviews(page, start, end)
            total_views += views
            logger.debug(
                "WikiSignalAgent: '%s' views=%d (page=%s)", event.title, views, page
            )

        event.signals.wiki_views = total_views
        logger.info(
            "WikiSignalAgent: '%s' total wiki_views=%d", event.title, total_views
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _date_range(self, event: Event) -> tuple[date, date]:
        start = event.start_date or self.default_start
        end = event.end_date or self.default_end

        # Expand range
        start = start - timedelta(days=30 * self.months_before)
        end = end + timedelta(days=30 * self.months_after)
        return start, end

    def _fetch_pageviews(self, title: str, start: date, end: date) -> int:
        """Fetch total monthly pageviews for a single article."""
        import urllib.parse

        encoded_title = urllib.parse.quote(title.replace(" ", "_"), safe="")
        project = f"{self.lang}.wikipedia"
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

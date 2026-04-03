"""
Search Signal Agent

Fetches Google Trends data via pytrends and returns a normalised
interest score (0–100) for each event's primary keyword.

An anchor keyword (default: "台灣" / "Taiwan") is used to make scores
comparable across different queries.

Improvements over v1:
  #2  Exponential back-off with jitter on HTTP 429 / transient errors.
  #5  Results cached to disk so that repeated pipeline runs skip the
      Google Trends request entirely.
"""

from __future__ import annotations

import logging
import random
import time

from core.cache import default_cache
from core.models import Event

logger = logging.getLogger(__name__)

_CACHE_AGENT = "search_signal"


class SearchSignalAgent:
    """
    Fetches normalised Google Trends scores via pytrends.

    Parameters
    ----------
    anchor_keyword : str
        Reference keyword included in every Trends request for normalisation.
    geo : str
        Google Trends geo filter (default "TW" = Taiwan).
    timeframe : str
        pytrends timeframe string (default "2014-01-01 2024-12-31").
    fallback_score : float
        Score to use when pytrends is unavailable (offline / rate-limited).
    request_delay : float
        Base seconds to wait between consecutive pytrends calls.
    max_retries : int
        Maximum number of retry attempts on transient failures (improvement #2).
    use_cache : bool
        Whether to persist results to disk (improvement #5, default True).
    """

    def __init__(
        self,
        anchor_keyword: str = "台灣",
        geo: str = "TW",
        timeframe: str = "2014-01-01 2024-12-31",
        fallback_score: float = 0.0,
        request_delay: float = 1.0,
        max_retries: int = 3,
        use_cache: bool = True,
    ):
        self.anchor_keyword = anchor_keyword
        self.geo = geo
        self.timeframe = timeframe
        self.fallback_score = fallback_score
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.use_cache = use_cache
        self._pytrends = None  # lazy init

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, event: Event) -> None:
        """
        Populate event.signals.search_score (0–100).
        Modifies the event object in place.
        """
        if event.signals is None:
            return

        keyword = event.keywords[0] if event.keywords else event.title

        # Improvement #5 – check disk cache first
        if self.use_cache:
            cached = default_cache.get(_CACHE_AGENT, keyword)
            if cached is not None:
                event.signals.search_score = float(cached)
                logger.info(
                    "SearchSignalAgent: '%s' search_score=%.2f (cached)",
                    event.title,
                    event.signals.search_score,
                )
                return

        score = self._fetch_trend_score(keyword)
        event.signals.search_score = score

        # Improvement #5 – persist to disk
        if self.use_cache:
            default_cache.set(_CACHE_AGENT, keyword, score)

        logger.info(
            "SearchSignalAgent: '%s' search_score=%.2f (keyword='%s')",
            event.title,
            score,
            keyword,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_pytrends(self):
        """Lazy initialise pytrends TrendReq."""
        if self._pytrends is None:
            try:
                from pytrends.request import TrendReq  # type: ignore

                self._pytrends = TrendReq(
                    hl="zh-TW",
                    tz=480,
                    timeout=(10, 25),
                    retries=1,
                    backoff_factor=0.5,
                )
            except ImportError:
                logger.warning("pytrends not installed – search scores will be zero")
        return self._pytrends

    def _fetch_trend_score(self, keyword: str) -> float:
        """
        Fetch the mean interest-over-time for `keyword` relative to anchor.

        Retries up to ``max_retries`` times with exponential back-off and
        jitter on any transient error (improvement #2).

        Returns a value in [0, 100].
        """
        pt = self._get_pytrends()
        if pt is None:
            return self.fallback_score

        for attempt in range(self.max_retries):
            try:
                kw_list = [keyword, self.anchor_keyword]
                pt.build_payload(
                    kw_list,
                    cat=0,
                    timeframe=self.timeframe,
                    geo=self.geo,
                )
                df = pt.interest_over_time()
                if df is None or df.empty or keyword not in df.columns:
                    return self.fallback_score

                # Mean interest for the event keyword, anchor-normalised
                anchor_mean = df[self.anchor_keyword].mean()
                if anchor_mean == 0:
                    return self.fallback_score

                keyword_mean = df[keyword].mean()
                # Scale so that anchor_mean → 50
                score = float(keyword_mean / anchor_mean * 50)
                score = max(0.0, min(100.0, score))

                time.sleep(self.request_delay)  # be polite to the API
                return score
            except Exception as exc:  # noqa: BLE001
                if attempt < self.max_retries - 1:
                    # Exponential back-off with jitter (improvement #2)
                    delay = self.request_delay * (2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        "SearchSignalAgent: attempt %d/%d failed for '%s': %s "
                        "– retrying in %.1fs",
                        attempt + 1,
                        self.max_retries,
                        keyword,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.warning(
                        "SearchSignalAgent: all %d attempts failed for '%s': %s",
                        self.max_retries,
                        keyword,
                        exc,
                    )
        return self.fallback_score

"""
Search Signal Agent

Fetches Google Trends data via pytrends and returns a normalised
interest score (0–100) for each event's primary keyword.

An anchor keyword (default: "台灣" / "Taiwan") is used to make scores
comparable across different queries.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from core.models import Event

logger = logging.getLogger(__name__)


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
        Seconds to wait between consecutive pytrends calls to avoid 429s.
    """

    def __init__(
        self,
        anchor_keyword: str = "台灣",
        geo: str = "TW",
        timeframe: str = "2014-01-01 2024-12-31",
        fallback_score: float = 0.0,
        request_delay: float = 1.0,
    ):
        self.anchor_keyword = anchor_keyword
        self.geo = geo
        self.timeframe = timeframe
        self.fallback_score = fallback_score
        self.request_delay = request_delay
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
        score = self._fetch_trend_score(keyword)
        event.signals.search_score = score
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
                logger.warning(
                    "pytrends not installed – search scores will be zero"
                )
        return self._pytrends

    def _fetch_trend_score(self, keyword: str) -> float:
        """
        Fetch the mean interest-over-time for `keyword` relative to anchor.

        Returns a value in [0, 100].
        """
        pt = self._get_pytrends()
        if pt is None:
            return self.fallback_score

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
            logger.warning(
                "SearchSignalAgent: pytrends failed for '%s': %s", keyword, exc
            )
            return self.fallback_score

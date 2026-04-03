"""
Pipeline orchestrator for the Collective Attention System.

Wires all agents together and drives the end-to-end flow:
  Ingestion → Event Detection → Event Identity → Signal Aggregation → Scoring
"""
from __future__ import annotations

import logging
from typing import List

from core.models import Event, compute_score

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Orchestrates the full multi-agent pipeline.

    Parameters
    ----------
    event_detection_agent  : detects / loads seed events
    event_identity_agent   : resolves Wikipedia canonical page
    wiki_signal_agent      : fetches Wikimedia pageviews
    news_signal_agent      : counts news articles
    search_signal_agent    : fetches Google Trends score
    scoring_agent          : assembles final score (optional – default logic used)
    """

    def __init__(
        self,
        event_detection_agent,
        event_identity_agent,
        wiki_signal_agent,
        news_signal_agent,
        search_signal_agent,
        scoring_agent=None,
    ):
        self.event_detection = event_detection_agent
        self.event_identity = event_identity_agent
        self.wiki_signal = wiki_signal_agent
        self.news_signal = news_signal_agent
        self.search_signal = search_signal_agent
        self.scoring = scoring_agent

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, top_n: int = 10) -> List[Event]:
        """
        Execute the full pipeline and return the top-N ranked events.
        """
        logger.info("=== Pipeline started ===")

        # 1. Event detection
        logger.info("Step 1/5 – Event Detection")
        events: List[Event] = self.event_detection.detect()
        logger.info("  Detected %d events", len(events))

        # 2. Event identity
        logger.info("Step 2/5 – Event Identity")
        for event in events:
            try:
                self.event_identity.resolve(event)
                logger.info(
                    "  [%s] canonical=%s redirects=%d",
                    event.title,
                    event.canonical_wiki_title,
                    len(event.wiki_redirect_pages),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("  Event identity failed for '%s': %s", event.title, exc)

        # 3. Signal aggregation
        logger.info("Step 3/5 – Signal Aggregation")
        for event in events:
            try:
                self.wiki_signal.fetch(event)
                logger.info(
                    "  [%s] wiki_views=%d", event.title, event.signals.wiki_views
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("  Wiki signal failed for '%s': %s", event.title, exc)

            try:
                self.news_signal.fetch(event)
                logger.info(
                    "  [%s] news_count=%d", event.title, event.signals.news_count
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("  News signal failed for '%s': %s", event.title, exc)

            try:
                self.search_signal.fetch(event)
                logger.info(
                    "  [%s] search_score=%.2f",
                    event.title,
                    event.signals.search_score,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "  Search signal failed for '%s': %s", event.title, exc
                )

        # 4. Scoring
        logger.info("Step 4/5 – Scoring")
        for event in events:
            if event.signals is None:
                logger.warning("  No signals for '%s', skipping score", event.title)
                continue
            try:
                if self.scoring:
                    self.scoring.score(event)
                else:
                    event.score_breakdown = compute_score(event.signals)
                    event.score = event.score_breakdown.total
                logger.info(
                    "  [%s] score=%.4f | %s",
                    event.title,
                    event.score,
                    event.score_breakdown.explanation if event.score_breakdown else "",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("  Scoring failed for '%s': %s", event.title, exc)

        # 5. Rank
        logger.info("Step 5/5 – Ranking")
        ranked = sorted(events, key=lambda e: e.score, reverse=True)[:top_n]

        logger.info("=== Pipeline complete – top %d events ===", len(ranked))
        for rank, event in enumerate(ranked, 1):
            logger.info("  #%d %s (score=%.4f)", rank, event.title, event.score)

        return ranked

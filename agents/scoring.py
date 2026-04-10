"""
Scoring Agent

Combines wiki, news and search signals into a final explainable score
and attaches a human-readable explanation to each event.

Formula (no black-box ML):
    score = log(wiki_views + 1) + log(news_count + 1) + normalized_search

Delegates the actual arithmetic to core.models.compute_score so the
formula stays in one place.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List

from core.models import Event, compute_score

logger = logging.getLogger(__name__)


class ScoringAgent:
    """
    Computes the collective-attention score for each event.

    The score is fully explainable: every component is logged and
    attached to the event's score_breakdown field.
    """

    def _weights_for_event(self, event: Event) -> tuple[float, float, float]:
        """Return era-aware source weights for one event."""
        start_date = event.start_date
        if start_date is None:
            return (0.5, 0.3, 0.2)

        if start_date < date(2004, 1, 1):
            return (0.75, 0.25, 0.0)

        if start_date < date(2015, 7, 1):
            return (0.6, 0.25, 0.15)

        return (0.4, 0.35, 0.25)

    def score(self, event: Event) -> None:
        """
        Compute and attach score to event.
        Modifies the event object in place.
        """
        if event.signals is None:
            logger.warning("ScoringAgent: no signals for '%s'", event.title)
            return

        wiki_weight, news_weight, search_weight = self._weights_for_event(event)
        breakdown = compute_score(
            event.signals,
            wiki_weight=wiki_weight,
            news_weight=news_weight,
            search_weight=search_weight,
        )
        event.score_breakdown = breakdown
        event.score = breakdown.total

        logger.info(
            "ScoringAgent: '%s' → score=%.4f | wiki=%.4f | news=%.4f | search=%.4f | %s",
            event.title,
            breakdown.total,
            breakdown.wiki_component,
            breakdown.news_component,
            breakdown.search_component,
            breakdown.explanation,
        )

    def score_all(self, events: List[Event]) -> List[Event]:
        """Score all events and return them sorted by score descending."""
        for event in events:
            self.score(event)
        return sorted(events, key=lambda e: e.score, reverse=True)

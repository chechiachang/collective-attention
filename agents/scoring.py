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
from typing import List

from core.models import Event, compute_score

logger = logging.getLogger(__name__)


class ScoringAgent:
    """
    Computes the collective-attention score for each event.

    The score is fully explainable: every component is logged and
    attached to the event's score_breakdown field.
    """

    def score(self, event: Event) -> None:
        """
        Compute and attach score to event.
        Modifies the event object in place.
        """
        if event.signals is None:
            logger.warning("ScoringAgent: no signals for '%s'", event.title)
            return

        breakdown = compute_score(event.signals)
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

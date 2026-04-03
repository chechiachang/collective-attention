"""
Core data models for the Collective Attention System.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class Signals:
    """Aggregated signals for a single event."""

    event_id: str
    wiki_views: int = 0
    news_count: int = 0
    search_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "wiki_views": self.wiki_views,
            "news_count": self.news_count,
            "search_score": round(self.search_score, 4),
        }


@dataclass
class ScoreBreakdown:
    """Score breakdown showing contribution of each signal."""

    wiki_component: float = 0.0
    news_component: float = 0.0
    search_component: float = 0.0
    total: float = 0.0
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "wiki_component": round(self.wiki_component, 4),
            "news_component": round(self.news_component, 4),
            "search_component": round(self.search_component, 4),
            "total": round(self.total, 4),
            "explanation": self.explanation,
        }


@dataclass
class Event:
    """A real-world event with associated signals and score."""

    id: str
    title: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    keywords: List[str] = field(default_factory=list)
    canonical_wiki_title: Optional[str] = None
    wiki_redirect_pages: List[str] = field(default_factory=list)
    signals: Optional[Signals] = None
    score_breakdown: Optional[ScoreBreakdown] = None
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "keywords": self.keywords,
            "canonical_wiki_title": self.canonical_wiki_title,
            "wiki_redirect_pages": self.wiki_redirect_pages,
            "score": round(self.score, 4),
            "signals": self.signals.to_dict() if self.signals else None,
            "score_breakdown": (
                self.score_breakdown.to_dict() if self.score_breakdown else None
            ),
        }


def compute_score(signals: Signals) -> ScoreBreakdown:
    """
    Compute an explainable score from multi-source signals.

    Formula:
        score = log(wiki_views + 1) + log(news_count + 1) + normalized_search

    The +1 guards against log(0).
    """
    wiki_component = math.log(signals.wiki_views + 1)
    news_component = math.log(signals.news_count + 1)
    search_component = float(signals.search_score)  # already normalised 0–100

    total = wiki_component + news_component + search_component

    # Build a human-readable explanation
    parts: List[str] = []
    if signals.wiki_views > 100_000:
        parts.append("Very high Wikipedia traffic")
    elif signals.wiki_views > 10_000:
        parts.append("High Wikipedia traffic")
    elif signals.wiki_views > 1_000:
        parts.append("Moderate Wikipedia traffic")
    else:
        parts.append("Low Wikipedia traffic")

    if signals.news_count > 100:
        parts.append("very high news coverage")
    elif signals.news_count > 20:
        parts.append("high news coverage")
    elif signals.news_count > 5:
        parts.append("moderate news coverage")
    else:
        parts.append("low news coverage")

    if signals.search_score > 70:
        parts.append("high search interest")
    elif signals.search_score > 30:
        parts.append("moderate search interest")
    else:
        parts.append("low search interest")

    explanation = "; ".join(parts).capitalize() + "."

    return ScoreBreakdown(
        wiki_component=wiki_component,
        news_component=news_component,
        search_component=search_component,
        total=total,
        explanation=explanation,
    )

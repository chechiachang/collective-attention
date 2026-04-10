"""
Core data models for the Collective Attention System.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

# ── Normalisation constants ───────────────────────────────────────────────────
# Each signal component is scaled to [0, 100/3] so the combined score is
# always in [0, 100] (three equal-weight components that each cap at ~33.33).
_WIKI_LOG_MAX: float = math.log(10_000_001)  # log(10 M + 1) ≈ 16.12
_NEWS_LOG_MAX: float = math.log(10_001)  # log(10 K + 1) ≈  9.21
_COMPONENT_MAX: float = 100.0 / 3.0  # each component cap ≈ 33.33


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


def compute_score(
    signals: Signals,
    wiki_weight: float = 1.0,
    news_weight: float = 1.0,
    search_weight: float = 1.0,
) -> ScoreBreakdown:
    """
    Compute an explainable, normalised score from multi-source signals.

    The raw wiki/news/search components are first normalised into **[0, 1]**,
    then weighted and re-scaled so the combined score stays in **[0, 100]**.
    When weights differ, their relative shares are re-normalised instead of
    simply multiplying the final score.

    ::

        weight_sum       = wiki_weight + news_weight + search_weight
        wiki_component   = (wiki_weight / weight_sum)   * log(wiki_views + 1) / log(10_000_001) * 100
        news_component   = (news_weight / weight_sum)   * log(news_count + 1) / log(10_001)     * 100
        search_component = (search_weight / weight_sum) * search_score / 100                      * 100
        score            = wiki_component + news_component + search_component

    The ``+1`` guards against ``log(0)``.  The normalisation denominators are
    generous upper bounds (10 M wiki-views, 10 K news articles) so real-world
    events rarely hit the cap.  Default weights of 1.0 give each source equal
    influence.

    Parameters
    ----------
    signals : Signals
        Raw signal values for the event.
    wiki_weight : float
        Multiplier for the Wikipedia pageview log-component (default 1.0).
    news_weight : float
        Multiplier for the news-count log-component (default 1.0).
    search_weight : float
        Multiplier for the search-score component (default 1.0).
    """
    weights = [max(0.0, wiki_weight), max(0.0, news_weight), max(0.0, search_weight)]
    weight_sum = sum(weights) or 1.0

    wiki_share = weights[0] / weight_sum
    news_share = weights[1] / weight_sum
    search_share = weights[2] / weight_sum

    wiki_component = (
        wiki_share * math.log(signals.wiki_views + 1) / _WIKI_LOG_MAX * 100.0
    )
    news_component = (
        news_share * math.log(signals.news_count + 1) / _NEWS_LOG_MAX * 100.0
    )
    search_component = search_share * float(signals.search_score)

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

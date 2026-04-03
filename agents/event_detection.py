"""
Event Detection Agent

Responsibilities:
  1. Load seed events from hardcoded config or RSS feed.
  2. (Optional) Parse RSS articles, generate embeddings, and cluster into events.

For the MVP the agent ships with hardcoded Taiwan events (original 5 plus
significant social/political events from the past five years) and also
attempts to ingest a configurable RSS feed when a URL is provided.

Improvements over v1:
  #4  Deduplication now uses keyword-overlap scoring instead of exact title
      matching so that RSS articles that describe a seed event under a
      slightly different headline are filtered out correctly.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import List, Optional

from core.models import Event, Signals

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed events (MVP hardcoded events per requirements)
# ---------------------------------------------------------------------------

SEED_EVENTS: List[dict] = [
    # ── Original five ──────────────────────────────────────────────────────
    {
        "title": "普悠瑪列車出軌事故",
        "keywords": ["普悠瑪", "出軌", "台鐵", "事故", "宜蘭"],
        "start_date": date(2018, 10, 21),
        "end_date": date(2018, 10, 21),
    },
    {
        "title": "鄭捷事件",
        "keywords": ["鄭捷", "捷運隨機殺人", "台北捷運", "板南線"],
        "start_date": date(2014, 5, 21),
        "end_date": date(2014, 5, 21),
    },
    {
        "title": "花蓮地震",
        "keywords": ["花蓮", "地震", "0206", "台灣地震"],
        "start_date": date(2018, 2, 6),
        "end_date": date(2018, 2, 6),
    },
    {
        "title": "太陽花學運",
        "keywords": ["太陽花", "佔領立法院", "服貿協議", "學運"],
        "start_date": date(2014, 3, 18),
        "end_date": date(2014, 4, 10),
    },
    {
        "title": "COVID-19台灣疫情",
        "keywords": ["COVID-19", "台灣疫情", "新冠肺炎", "本土確診"],
        "start_date": date(2020, 1, 21),
        "end_date": date(2022, 12, 31),
    },
    # ── Significant events from the past five years (2021–2026) ───────────
    {
        "title": "太魯閣號出軌事故",
        "keywords": ["太魯閣號", "出軌", "台鐵408", "清水隧道", "列車事故"],
        "start_date": date(2021, 4, 2),
        "end_date": date(2021, 4, 2),
    },
    {
        "title": "裴洛西訪台",
        "keywords": ["裴洛西", "佩洛西", "訪台", "台海軍演", "解放軍演習"],
        "start_date": date(2022, 8, 2),
        "end_date": date(2022, 8, 10),
    },
    {
        "title": "2022年九合一選舉",
        "keywords": ["九合一選舉", "地方選舉", "民進黨", "國民黨", "2022選舉"],
        "start_date": date(2022, 11, 26),
        "end_date": date(2022, 11, 26),
    },
    {
        "title": "2024年台灣總統大選",
        "keywords": ["台灣大選", "賴清德", "總統選舉", "2024選舉", "民進黨"],
        "start_date": date(2024, 1, 13),
        "end_date": date(2024, 1, 13),
    },
    {
        "title": "2024年花蓮強震",
        "keywords": ["花蓮地震", "強震", "2024地震", "台灣地震", "7.4地震"],
        "start_date": date(2024, 4, 3),
        "end_date": date(2024, 4, 3),
    },
]


def _make_id(title: str) -> str:
    """Deterministic short ID derived from the event title."""
    return hashlib.md5(title.encode()).hexdigest()[:8]


class EventDetectionAgent:
    """
    Detects events from seed data and/or RSS feeds.

    Parameters
    ----------
    rss_url : str, optional
        If provided the agent will attempt to fetch and parse the RSS feed.
        Articles are deduplicated against seed titles using a simple
        keyword-overlap heuristic (no embedding required for MVP).
    include_seeds : bool
        Always include the hardcoded seed events (default True).
    """

    def __init__(
        self,
        rss_url: Optional[str] = None,
        include_seeds: bool = True,
    ):
        self.rss_url = rss_url
        self.include_seeds = include_seeds

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def detect(self) -> List[Event]:
        events: List[Event] = []

        if self.include_seeds:
            for seed in SEED_EVENTS:
                event_id = _make_id(seed["title"])
                event = Event(
                    id=event_id,
                    title=seed["title"],
                    keywords=list(seed["keywords"]),
                    start_date=seed.get("start_date"),
                    end_date=seed.get("end_date"),
                    signals=Signals(event_id=event_id),
                )
                events.append(event)
                logger.debug("Seed event loaded: %s", event.title)

        if self.rss_url:
            rss_events = self._ingest_rss(self.rss_url)
            # Improvement #4 – keyword-overlap deduplication
            # Build a flat set of all seed keywords for quick overlap check
            seed_keyword_sets = [
                {kw.lower() for kw in e.keywords} for e in events
            ]
            for e in rss_events:
                if self._is_duplicate(e, events, seed_keyword_sets):
                    logger.debug(
                        "RSS event deduplicated (keyword overlap): %s", e.title
                    )
                    continue
                events.append(e)
                seed_keyword_sets.append({kw.lower() for kw in e.keywords})

        logger.info("EventDetectionAgent: %d events detected", len(events))
        return events

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _keyword_overlap(set_a: set, set_b: set) -> float:
        """Jaccard-like overlap ratio between two keyword sets."""
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union else 0.0

    def _is_duplicate(
        self,
        candidate: "Event",
        existing: List["Event"],
        existing_kw_sets: List[set],
        title_match: bool = True,
        overlap_threshold: float = 0.4,
    ) -> bool:
        """
        Return True if *candidate* is a near-duplicate of any existing event.

        A duplicate is detected when:
        - Exact title match, OR
        - Keyword-overlap ratio ≥ *overlap_threshold* (improvement #4).
        """
        candidate_kws = {kw.lower() for kw in candidate.keywords}
        cand_title = candidate.title.lower()
        for event, kw_set in zip(existing, existing_kw_sets):
            if title_match and cand_title == event.title.lower():
                return True
            if self._keyword_overlap(candidate_kws, kw_set) >= overlap_threshold:
                return True
        return False

    def _ingest_rss(self, url: str) -> List[Event]:
        """Fetch and parse an RSS feed, returning a list of candidate events."""
        try:
            import feedparser  # type: ignore

            feed = feedparser.parse(url)
            events: List[Event] = []
            for entry in feed.entries[:50]:  # cap at 50 articles
                title = entry.get("title", "").strip()
                if not title:
                    continue
                event_id = _make_id(title)
                events.append(
                    Event(
                        id=event_id,
                        title=title,
                        keywords=title.split()[:5],
                        signals=Signals(event_id=event_id),
                    )
                )
            logger.info("RSS ingestion: %d articles from %s", len(events), url)
            return events
        except Exception as exc:  # noqa: BLE001
            logger.warning("RSS ingestion failed for %s: %s", url, exc)
            return []

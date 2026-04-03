"""
Event Detection Agent

Responsibilities:
  1. Load seed events from hardcoded config or RSS feed.
  2. (Optional) Parse RSS articles, generate embeddings, and cluster into events.

For the MVP the agent ships with 3 hardcoded Taiwan events and also
attempts to ingest a configurable RSS feed when a URL is provided.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date
from typing import List, Optional

from core.models import Event, Signals

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed events (MVP hardcoded events per requirements)
# ---------------------------------------------------------------------------

SEED_EVENTS: List[dict] = [
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
            # Deduplicate: skip if title already present
            existing_titles = {e.title for e in events}
            for e in rss_events:
                if e.title not in existing_titles:
                    events.append(e)
                    existing_titles.add(e.title)

        logger.info("EventDetectionAgent: %d events detected", len(events))
        return events

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

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

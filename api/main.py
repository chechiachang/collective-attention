"""
FastAPI application – Collective Attention System API.

Run with:
    uvicorn api.main:app --reload

Endpoints:
    GET /events/top          – top-N ranked events with score breakdown
    GET /events/{event_id}   – single event detail
    GET /health              – health check
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import List, Optional

# Make the project root importable when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from agents.event_detection import EventDetectionAgent
from agents.event_identity import EventIdentityAgent
from agents.news_signal import NewsSignalAgent
from agents.scoring import ScoringAgent
from agents.search_signal import SearchSignalAgent
from agents.wiki_signal import WikiSignalAgent
from core.models import Event
from core.pipeline import Pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Build the pipeline once at startup (cached in module scope)
# ---------------------------------------------------------------------------

_pipeline: Optional[Pipeline] = None
_ranked_events: Optional[List[Event]] = None


def _build_pipeline() -> Pipeline:
    return Pipeline(
        event_detection_agent=EventDetectionAgent(include_seeds=True),
        event_identity_agent=EventIdentityAgent(),
        wiki_signal_agent=WikiSignalAgent(),
        news_signal_agent=NewsSignalAgent(),
        search_signal_agent=SearchSignalAgent(fallback_score=0.0),
        scoring_agent=ScoringAgent(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the pipeline on startup so results are cached."""
    global _pipeline, _ranked_events
    logger.info("Running pipeline on startup …")
    _pipeline = _build_pipeline()
    _ranked_events = _pipeline.run(top_n=50)
    logger.info("Pipeline complete – %d events ranked", len(_ranked_events))
    yield


app = FastAPI(
    title="Collective Attention System",
    description=(
        "Quantifies collective attention of real-world events in Taiwan "
        "(2014–2024) using Wikipedia, news and search signals."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/events/top")
def get_top_events(
    n: int = Query(
        default=10, ge=1, le=50, description="Number of top events to return"
    ),
) -> JSONResponse:
    """
    Return the top-N ranked events with their score breakdown.

    Each event includes:
    - id, title, start_date, end_date, keywords
    - score (total collective-attention score)
    - score_breakdown (wiki, news, search components + human explanation)
    - signals (raw signal values)
    """
    if _ranked_events is None:
        raise HTTPException(status_code=503, detail="Pipeline not yet initialised")

    top = _ranked_events[:n]
    return JSONResponse(
        content={
            "count": len(top),
            "events": [e.to_dict() for e in top],
        }
    )


@app.get("/events/{event_id}")
def get_event(event_id: str) -> JSONResponse:
    """Return a single event by its ID."""
    if _ranked_events is None:
        raise HTTPException(status_code=503, detail="Pipeline not yet initialised")

    for event in _ranked_events:
        if event.id == event_id:
            return JSONResponse(content=event.to_dict())

    raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")

"""
Tests for the Collective Attention System.

These tests avoid any real network calls by using mocks/stubs, so the
suite is fully offline and fast.
"""

from __future__ import annotations

import math
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from agents.event_detection import SEED_EVENTS, EventDetectionAgent
from agents.event_identity import EventIdentityAgent
from agents.news_signal import NewsSignalAgent
from agents.scoring import ScoringAgent
from agents.wiki_signal import WikiSignalAgent
from api.main import app
from core.models import Event, ScoreBreakdown, Signals, compute_score
from core.pipeline import Pipeline


class TestComputeScore:
    # Normalisation constants mirrored from core.models for assertion math
    _WIKI_LOG_MAX = math.log(10_000_001)
    _NEWS_LOG_MAX = math.log(10_001)
    _CMAX = 100.0 / 3.0

    def test_formula_values(self):
        s = Signals(event_id="e1", wiki_views=1000, news_count=50, search_score=60.0)
        bd = compute_score(s)
        expected_wiki = math.log(1001) / self._WIKI_LOG_MAX * self._CMAX
        expected_news = math.log(51) / self._NEWS_LOG_MAX * self._CMAX
        expected_search = 60.0 / 100.0 * self._CMAX
        assert bd.wiki_component == pytest.approx(expected_wiki, rel=1e-6)
        assert bd.news_component == pytest.approx(expected_news, rel=1e-6)
        assert bd.search_component == pytest.approx(expected_search, rel=1e-6)
        assert bd.total == pytest.approx(
            expected_wiki + expected_news + expected_search, rel=1e-6
        )

    def test_score_always_at_most_100(self):
        """Normalised score must never exceed 100 regardless of input magnitude."""
        extreme = Signals(
            event_id="max",
            wiki_views=10_000_000,
            news_count=10_000,
            search_score=100.0,
        )
        bd = compute_score(extreme)
        assert bd.total <= 100.0 + 1e-9  # allow tiny floating-point slack

    def test_score_bounded_for_realistic_inputs(self):
        """Real-world high-signal events (like COVID) must score ≤ 100."""
        s = Signals(
            event_id="covid",
            wiki_views=1_540_000,
            news_count=241,
            search_score=95.2,
        )
        bd = compute_score(s)
        assert bd.total <= 100.0

    def test_zero_signals(self):
        s = Signals(event_id="e0")
        bd = compute_score(s)
        assert bd.wiki_component == pytest.approx(0.0, abs=1e-9)
        assert bd.news_component == pytest.approx(0.0, abs=1e-9)
        assert bd.search_component == pytest.approx(0.0, abs=1e-9)
        assert bd.total == pytest.approx(0.0, abs=1e-9)

    def test_explanation_high_signals(self):
        s = Signals(
            event_id="e2", wiki_views=200_000, news_count=200, search_score=80.0
        )
        bd = compute_score(s)
        explanation = bd.explanation.lower()
        assert "wikipedia" in explanation
        assert "news" in explanation
        assert "search" in explanation

    def test_explanation_low_signals(self):
        s = Signals(event_id="e3", wiki_views=100, news_count=3, search_score=10.0)
        bd = compute_score(s)
        assert "low" in bd.explanation.lower()

    def test_score_breakdown_to_dict(self):
        bd = ScoreBreakdown(
            wiki_component=1.1,
            news_component=2.2,
            search_component=3.3,
            total=6.6,
            explanation="Test.",
        )
        d = bd.to_dict()
        assert d["total"] == pytest.approx(6.6, rel=1e-4)
        assert d["explanation"] == "Test."


class TestEvent:
    def test_to_dict_minimal(self):
        event = Event(id="abc", title="Test Event")
        d = event.to_dict()
        assert d["id"] == "abc"
        assert d["title"] == "Test Event"
        assert d["start_date"] is None
        assert d["score"] == 0.0

    def test_to_dict_with_signals_and_breakdown(self):
        signals = Signals(
            event_id="abc", wiki_views=500, news_count=10, search_score=25.0
        )
        bd = compute_score(signals)
        event = Event(
            id="abc",
            title="Test",
            start_date=date(2020, 1, 1),
            signals=signals,
            score_breakdown=bd,
            score=bd.total,
        )
        d = event.to_dict()
        assert d["signals"]["wiki_views"] == 500
        assert d["score_breakdown"]["total"] == pytest.approx(bd.total, rel=1e-4)


# ---------------------------------------------------------------------------
# agents.event_detection
# ---------------------------------------------------------------------------


class TestEventDetectionAgent:
    def test_seed_events_loaded(self):
        agent = EventDetectionAgent(include_seeds=True)
        events = agent.detect()
        assert len(events) == len(SEED_EVENTS)

    def test_seed_event_ids_are_deterministic(self):
        agent = EventDetectionAgent(include_seeds=True)
        events1 = agent.detect()
        events2 = agent.detect()
        assert [e.id for e in events1] == [e.id for e in events2]

    def test_seed_events_have_signals_initialised(self):
        agent = EventDetectionAgent(include_seeds=True)
        for event in agent.detect():
            assert event.signals is not None
            assert event.signals.event_id == event.id

    def test_required_seed_events_present(self):
        agent = EventDetectionAgent(include_seeds=True)
        titles = {e.title for e in agent.detect()}
        assert "普悠瑪列車出軌事故" in titles
        assert "鄭捷事件" in titles
        assert "花蓮地震" in titles

    def test_rss_failure_is_graceful(self):
        agent = EventDetectionAgent(
            rss_url="http://invalid.example.invalid/feed",
            include_seeds=True,
        )
        # Should not raise; falls back to seeds only
        events = agent.detect()
        assert len(events) == len(SEED_EVENTS)


# ---------------------------------------------------------------------------
# agents.event_identity
# ---------------------------------------------------------------------------


class TestEventIdentityAgent:
    def _make_event(self, title="Test", keywords=None):
        eid = "test123"
        return Event(
            id=eid,
            title=title,
            keywords=keywords or [title],
            signals=Signals(event_id=eid),
        )

    def test_resolve_sets_canonical(self, requests_mock):
        """Mock Wikipedia search and redirect API responses."""
        agent = EventIdentityAgent(lang="zh", fallback_lang="en")
        event = self._make_event("花蓮地震", ["花蓮", "地震"])

        # Mock the search call
        requests_mock.get(
            "https://zh.wikipedia.org/w/api.php",
            [
                {"json": {"query": {"search": [{"title": "花蓮地震 (2018年)"}]}}},
                {
                    "json": {
                        "query": {
                            "pages": {
                                "1": {
                                    "title": "花蓮地震 (2018年)",
                                    "redirects": [
                                        {"title": "0206花蓮地震"},
                                        {"title": "花蓮大地震"},
                                    ],
                                }
                            }
                        }
                    }
                },
            ],
        )

        agent.resolve(event)
        assert event.canonical_wiki_title == "花蓮地震 (2018年)"
        assert "0206花蓮地震" in event.wiki_redirect_pages

    def test_resolve_handles_empty_search(self, requests_mock):
        agent = EventIdentityAgent(lang="zh", fallback_lang="")
        event = self._make_event("非常罕見的事件標題XYZ")

        requests_mock.get(
            "https://zh.wikipedia.org/w/api.php",
            json={"query": {"search": []}},
        )

        agent.resolve(event)
        assert event.canonical_wiki_title is None
        assert event.wiki_redirect_pages == []


# ---------------------------------------------------------------------------
# agents.wiki_signal
# ---------------------------------------------------------------------------


class TestWikiSignalAgent:
    def _make_event_with_canonical(self, title, canonical, redirects=None):
        eid = "wikitest"
        return Event(
            id=eid,
            title=title,
            canonical_wiki_title=canonical,
            wiki_redirect_pages=redirects or [],
            signals=Signals(event_id=eid),
        )

    def test_fetch_aggregates_views(self, requests_mock):
        import re

        agent = WikiSignalAgent(lang="zh")
        event = self._make_event_with_canonical(
            "普悠瑪列車出軌事故",
            "普悠瑪列車出軌事故",
            redirects=["台鐵0206事故"],
        )
        event.start_date = date(2018, 10, 21)
        event.end_date = date(2018, 10, 21)

        # Match any Wikimedia pageviews request (URL-pattern independent of dates)
        requests_mock.get(
            re.compile(r"https://wikimedia\.org/api/rest_v1/metrics/pageviews/.*"),
            [
                {"json": {"items": [{"views": 100}]}},
                {"json": {"items": [{"views": 50}]}},
            ],
        )

        agent.fetch(event)
        assert event.signals.wiki_views == 150

    def test_fetch_skips_404(self, requests_mock):
        import re

        agent = WikiSignalAgent(lang="zh")
        event = self._make_event_with_canonical("Some Event", "NonExistentPage")
        event.start_date = date(2014, 1, 1)
        event.end_date = date(2014, 1, 1)

        requests_mock.get(
            re.compile(r"https://wikimedia\.org/api/rest_v1/metrics/pageviews/.*"),
            status_code=404,
        )
        agent.fetch(event)
        assert event.signals.wiki_views == 0

    def test_fetch_no_canonical_skips(self):
        agent = WikiSignalAgent(lang="zh")
        event = Event(
            id="x",
            title="No Wiki",
            signals=Signals(event_id="x"),
        )
        agent.fetch(event)
        assert event.signals.wiki_views == 0


# ---------------------------------------------------------------------------
# agents.news_signal
# ---------------------------------------------------------------------------


class TestNewsSignalAgent:
    def _make_event(self, title, keywords):
        eid = "newstest"
        return Event(
            id=eid,
            title=title,
            keywords=keywords,
            signals=Signals(event_id=eid),
        )

    def test_count_matching_articles(self, mocker):
        agent = NewsSignalAgent(rss_feeds=["http://fake.feed/rss"])

        fake_feed = MagicMock()
        fake_feed.entries = [
            MagicMock(title="花蓮強震造成多人傷亡", summary=""),
            MagicMock(title="地震預警系統啟動", summary="花蓮"),
            MagicMock(title="台北今日天氣晴", summary=""),
        ]
        mocker.patch("feedparser.parse", return_value=fake_feed)

        event = self._make_event("花蓮地震", ["花蓮", "地震"])
        agent.fetch(event)
        assert event.signals.news_count == 2

    def test_fallback_count_on_failure(self, mocker):
        agent = NewsSignalAgent(rss_feeds=["http://bad.feed/rss"], fallback_count=42)
        mocker.patch("feedparser.parse", side_effect=Exception("network error"))

        event = self._make_event("Test", ["keyword"])
        agent.fetch(event)
        assert event.signals.news_count == 42

    def test_no_keywords_uses_fallback(self):
        agent = NewsSignalAgent(rss_feeds=[], fallback_count=99)
        event = self._make_event("Test", [])
        agent.fetch(event)
        assert event.signals.news_count == 99


# ---------------------------------------------------------------------------
# agents.scoring
# ---------------------------------------------------------------------------


class TestScoringAgent:
    def test_score_sets_total_and_breakdown(self):
        agent = ScoringAgent()
        signals = Signals(
            event_id="s1", wiki_views=10000, news_count=50, search_score=40.0
        )
        event = Event(id="s1", title="Test", signals=signals)
        agent.score(event)

        assert event.score > 0
        assert event.score_breakdown is not None
        assert event.score == pytest.approx(event.score_breakdown.total, rel=1e-6)

    def test_score_all_returns_sorted(self):
        agent = ScoringAgent()
        e1 = Event(id="a", title="A", signals=Signals(event_id="a", wiki_views=100))
        e2 = Event(
            id="b", title="B", signals=Signals(event_id="b", wiki_views=1_000_000)
        )
        ranked = agent.score_all([e1, e2])
        assert ranked[0].id == "b"
        assert ranked[1].id == "a"

    def test_score_no_signals_skips(self):
        agent = ScoringAgent()
        event = Event(id="x", title="No signals")
        agent.score(event)
        assert event.score == 0.0
        assert event.score_breakdown is None


# ---------------------------------------------------------------------------
# core.pipeline
# ---------------------------------------------------------------------------


class TestPipeline:
    def _build_pipeline(self, events, wiki_views=500, news_count=10, search_score=30.0):
        detection_agent = MagicMock()
        detection_agent.detect.return_value = events

        def resolve(event):
            event.canonical_wiki_title = event.title
            event.wiki_redirect_pages = []

        def fetch_wiki(event):
            event.signals.wiki_views = wiki_views

        def fetch_news(event):
            event.signals.news_count = news_count

        def fetch_search(event):
            event.signals.search_score = search_score

        identity_agent = MagicMock()
        identity_agent.resolve.side_effect = resolve

        wiki_agent = MagicMock()
        wiki_agent.fetch.side_effect = fetch_wiki

        news_agent = MagicMock()
        news_agent.fetch.side_effect = fetch_news

        search_agent = MagicMock()
        search_agent.fetch.side_effect = fetch_search

        return Pipeline(
            event_detection_agent=detection_agent,
            event_identity_agent=identity_agent,
            wiki_signal_agent=wiki_agent,
            news_signal_agent=news_agent,
            search_signal_agent=search_agent,
        )

    def _make_events(self, n=3):
        events = []
        for i in range(n):
            eid = f"e{i}"
            events.append(
                Event(
                    id=eid,
                    title=f"Event {i}",
                    signals=Signals(event_id=eid),
                )
            )
        return events

    def test_run_returns_ranked_events(self):
        events = self._make_events(3)
        pipeline = self._build_pipeline(events)
        ranked = pipeline.run(top_n=10)
        assert len(ranked) == 3
        # All events should have a score
        for e in ranked:
            assert e.score > 0

    def test_run_top_n_respected(self):
        events = self._make_events(5)
        pipeline = self._build_pipeline(events)
        ranked = pipeline.run(top_n=2)
        assert len(ranked) == 2

    def test_run_sorted_descending(self):
        events = self._make_events(3)
        pipeline = self._build_pipeline(events)
        ranked = pipeline.run(top_n=10)
        scores = [e.score for e in ranked]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# api.main (FastAPI)
# ---------------------------------------------------------------------------


class TestAPI:
    def _client_with_events(self, events):
        """Build a TestClient with pre-populated _ranked_events."""
        api_main._ranked_events = events
        return TestClient(app)

    def _make_scored_events(self, n=5):
        events = []
        for i in range(n):
            eid = f"api{i}"
            signals = Signals(event_id=eid, wiki_views=(i + 1) * 1000, news_count=i * 5)
            bd = compute_score(signals)
            event = Event(
                id=eid,
                title=f"API Event {i}",
                signals=signals,
                score_breakdown=bd,
                score=bd.total,
            )
            events.append(event)
        return sorted(events, key=lambda e: e.score, reverse=True)

    def test_health(self):
        api_main._ranked_events = []
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_top_events_default(self):
        events = self._make_scored_events(5)
        client = self._client_with_events(events)
        response = client.get("/events/top")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5
        assert len(data["events"]) == 5

    def test_top_events_n_param(self):
        events = self._make_scored_events(5)
        client = self._client_with_events(events)
        response = client.get("/events/top?n=3")
        assert response.status_code == 200
        assert response.json()["count"] == 3

    def test_top_events_score_breakdown_present(self):
        events = self._make_scored_events(2)
        client = self._client_with_events(events)
        response = client.get("/events/top")
        first = response.json()["events"][0]
        assert "score_breakdown" in first
        assert "explanation" in first["score_breakdown"]

    def test_get_event_by_id(self):
        events = self._make_scored_events(3)
        client = self._client_with_events(events)
        event_id = events[0].id
        response = client.get(f"/events/{event_id}")
        assert response.status_code == 200
        assert response.json()["id"] == event_id

    def test_get_event_not_found(self):
        client = self._client_with_events([])
        response = client.get("/events/nonexistent")
        assert response.status_code == 404

    def test_top_events_503_when_none(self):
        api_main._ranked_events = None
        client = TestClient(app)
        response = client.get("/events/top")
        assert response.status_code == 503

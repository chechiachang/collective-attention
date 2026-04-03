"""
Tests for frontend/index.html

Validates that the frontend page contains the expected HTML structure,
required JavaScript functions, and correct API/fallback endpoints.
No browser or network required – pure static-file parsing.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

FRONTEND_PATH = Path(__file__).parent.parent / "docs" / "index.html"


@pytest.fixture(scope="module")
def html_content() -> str:
    assert FRONTEND_PATH.is_file(), f"frontend/index.html not found at {FRONTEND_PATH}"
    return FRONTEND_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML structure helpers
# ---------------------------------------------------------------------------


class _AttrCollector(HTMLParser):
    """Collects all tag names and their attributes encountered while parsing."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: List[Tuple[str, Dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Any]]) -> None:
        self.tags.append((tag, dict(attrs)))


def _collect_tags(html: str) -> List[Tuple[str, Dict[str, str]]]:
    collector = _AttrCollector()
    collector.feed(html)
    return collector.tags


def _ids(tags: List[Tuple[str, Dict[str, str]]]) -> List[str]:
    return [attrs.get("id", "") for _, attrs in tags if attrs.get("id")]


def _by_tag(tags: List[Tuple[str, Dict[str, str]]], tag_name: str):
    return [(t, a) for t, a in tags if t == tag_name]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFrontendExists:
    def test_file_exists(self):
        assert FRONTEND_PATH.is_file()

    def test_file_not_empty(self, html_content):
        assert len(html_content) > 500


class TestHTMLStructure:
    def test_has_doctype(self, html_content):
        assert html_content.strip().lower().startswith("<!doctype html")

    def test_has_html_tag_with_lang(self, html_content):
        tags = _collect_tags(html_content)
        html_tags = _by_tag(tags, "html")
        assert html_tags, "Missing <html> element"
        assert html_tags[0][1].get("lang"), "<html> should have a lang attribute"

    def test_has_head_and_body(self, html_content):
        tags = _collect_tags(html_content)
        tag_names = {t for t, _ in tags}
        assert "head" in tag_names
        assert "body" in tag_names

    def test_has_meta_charset(self, html_content):
        tags = _collect_tags(html_content)
        meta_tags = _by_tag(tags, "meta")
        charsets = [a.get("charset", "").lower() for _, a in meta_tags]
        assert any("utf-8" in c for c in charsets), "Expected meta charset=UTF-8"

    def test_has_meta_viewport(self, html_content):
        tags = _collect_tags(html_content)
        meta_tags = _by_tag(tags, "meta")
        viewports = [a for _, a in meta_tags if a.get("name") == "viewport"]
        assert viewports, "Missing <meta name='viewport'>"

    def test_has_title(self, html_content):
        tags = _collect_tags(html_content)
        assert _by_tag(tags, "title"), "Missing <title>"


class TestRequiredIDs:
    """All DOM element IDs that JavaScript references must be present."""

    REQUIRED_IDS = [
        "ranking-view",
        "timeline-view",
        "controls",
        "status",
        "n-slider",
        "n-label",
        "btn-ranking",
        "btn-timeline",
    ]

    def test_required_ids_present(self, html_content):
        tags = _collect_tags(html_content)
        found = set(_ids(tags))
        missing = [eid for eid in self.REQUIRED_IDS if eid not in found]
        assert not missing, f"Missing required element IDs: {missing}"


class TestTabButtons:
    def test_ranking_tab_button_exists(self, html_content):
        assert 'id="btn-ranking"' in html_content

    def test_timeline_tab_button_exists(self, html_content):
        assert 'id="btn-timeline"' in html_content

    def test_tabs_call_switch_view(self, html_content):
        assert "switchView('ranking')" in html_content
        assert "switchView('timeline')" in html_content


class TestJavaScriptFunctions:
    """Key JavaScript functions that must be defined in the page."""

    REQUIRED_FUNCTIONS = [
        "function loadData",
        "function render",
        "function renderRanking",
        "function renderTimeline",
        "function switchView",
        "function toggleCard",
        "function onNChange",
        "function buildCard",
    ]

    def test_required_functions_defined(self, html_content):
        missing = [fn for fn in self.REQUIRED_FUNCTIONS if fn not in html_content]
        assert not missing, f"Missing JavaScript functions: {missing}"


class TestAPIEndpoints:
    def test_references_events_top_endpoint(self, html_content):
        assert "/events/top" in html_content

    def test_references_sort_param(self, html_content):
        assert "sort=attention" in html_content

    def test_fallback_to_results_json(self, html_content):
        assert "results.json" in html_content


class TestSlider:
    def test_slider_has_min_max(self, html_content):
        assert 'id="n-slider"' in html_content
        assert "min=" in html_content
        assert "max=" in html_content

    def test_slider_calls_on_n_change(self, html_content):
        assert "onNChange" in html_content

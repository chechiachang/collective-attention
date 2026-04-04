"""
Tests for docs/index.html

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
    assert FRONTEND_PATH.is_file(), f"docs/index.html not found at {FRONTEND_PATH}"
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


class TestTimelineConsistency:
    """Tests that verify timeline and ranking views show a consistent number of events."""

    def test_switch_view_uses_explicit_display_block(self, html_content):
        """switchView must set display='block' explicitly, not '' (empty string).

        Using '' removes the inline style and causes the CSS ``#timeline-view { display: none }``
        rule to take effect, which keeps the timeline hidden even after clicking the tab.
        """
        import re

        match = re.search(
            r"function switchView\b.*?^}",
            html_content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "function switchView not found"
        code = match.group(0)
        assert "? 'block' : 'none'" in code or '? "block" : "none"' in code, (
            "switchView must use 'block' (not empty string) to show views; "
            "setting display='' reverts to the CSS display:none rule"
        )

    def test_render_calls_both_ranking_and_timeline(self, html_content):
        """render() must call both renderRanking and renderTimeline with the same events."""
        import re

        match = re.search(
            r"function render\b.*?^}",
            html_content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "function render not found"
        code = match.group(0)
        assert "renderRanking" in code, "render() must call renderRanking"
        assert "renderTimeline" in code, "render() must call renderTimeline"

    def test_render_timeline_handles_missing_start_date(self, html_content):
        """renderTimeline must not silently drop events without a start_date."""
        import re

        match = re.search(
            r"function renderTimeline\b.*?^}",
            html_content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "function renderTimeline not found"
        code = match.group(0)
        # Events without start_date should be grouped (e.g. under '?') not discarded
        assert (
            "start_date" in code
        ), "renderTimeline must handle events with no start_date"

    def test_timeline_proportional_axis(self, html_content):
        """renderTimeline must emit year and quarter axis tick labels."""
        import re

        match = re.search(
            r"function renderTimeline\b.*?^}",
            html_content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "function renderTimeline not found"
        code = match.group(0)
        # Year labels
        assert "tl-axis-year" in code, (
            "renderTimeline must emit year labels (class tl-axis-year) for a "
            "proportional time axis"
        )
        # Quarter labels
        assert "tl-axis-qtr" in code, (
            "renderTimeline must emit quarter labels (class tl-axis-qtr) for a "
            "proportional time axis"
        )
        # Fixed spacing constant
        assert (
            "PX_PER_MONTH" in code
        ), "renderTimeline must use a PX_PER_MONTH constant for consistent spacing"

    def test_timeline_cards_are_clickable(self, html_content):
        """Cards in the timeline must use toggleCard so details can be expanded."""
        import re

        match = re.search(
            r"function renderTimeline\b.*?^}",
            html_content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "function renderTimeline not found"
        code = match.group(0)
        assert "buildCard" in code, (
            "renderTimeline must call buildCard (which embeds the toggleCard handler) "
            "so timeline events are clickable"
        )

    def test_toggle_card_elevates_timeline_item_z_index(self, html_content):
        """toggleCard must raise the z-index of the parent .tl-prop-item so that
        an expanded card is rendered above sibling absolutely-positioned items.

        Without this fix, expanding a card in the proportional timeline is
        visually invisible because later DOM siblings paint over the expanded
        content (they are absolutely positioned in the same stacking context).
        """
        import re

        match = re.search(
            r"function toggleCard\b.*?^}",
            html_content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "function toggleCard not found"
        code = match.group(0)
        assert "tl-prop-item" in code, (
            "toggleCard must reference tl-prop-item to update its z-index so that "
            "expanded timeline cards are not hidden behind sibling items"
        )
        assert "zIndex" in code or "z-index" in code, (
            "toggleCard must set z-index on the parent tl-prop-item so the expanded "
            "card renders above other timeline items"
        )

    def test_css_timeline_item_z_index_on_expand(self, html_content):
        """CSS must elevate .tl-prop-item when it contains an expanded card.

        The :has() selector rule provides a CSS-native complement to the JS
        z-index update and ensures the expanded card is always on top.
        """
        assert ".tl-prop-item:has(.event-card.expanded)" in html_content, (
            "CSS must contain a .tl-prop-item:has(.event-card.expanded) rule to "
            "elevate the expanded card above sibling timeline items"
        )


class TestSourceLinking:
    """The Wikipedia source link must be always visible in the card header."""

    def test_wiki_link_in_build_card(self, html_content):
        """buildCard must render a Wikipedia anchor tag."""
        import re

        match = re.search(
            r"function buildCard\b.*?^}",
            html_content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "function buildCard not found"
        code = match.group(0)
        assert (
            "zh.wikipedia.org/wiki/" in code
        ), "buildCard must include a zh.wikipedia.org link for the canonical wiki title"

    def test_wiki_link_outside_signals_row(self, html_content):
        """The Wikipedia link must appear before the signals-row so it is always visible."""
        import re

        match = re.search(
            r"function buildCard\b.*?^}",
            html_content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "function buildCard not found"
        code = match.group(0)
        wiki_pos = code.find("zh.wikipedia.org")
        signals_row_pos = code.find("signals-row")
        assert wiki_pos != -1, "Wikipedia link not found in buildCard"
        assert signals_row_pos != -1, "signals-row not found in buildCard"
        assert wiki_pos < signals_row_pos, (
            "Wikipedia link must appear before signals-row (i.e. in the always-visible "
            "card header, not inside the collapsed signals section)"
        )

    def test_wiki_link_stops_propagation(self, html_content):
        """Clicking the wiki link must not toggle card expansion."""
        import re

        match = re.search(
            r"function buildCard\b.*?^}",
            html_content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "function buildCard not found"
        code = match.group(0)
        assert "stopPropagation" in code, (
            "The wiki link must call stopPropagation() so clicking it does not "
            "also toggle the card expanded/collapsed state"
        )

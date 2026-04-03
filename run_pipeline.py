"""
run_pipeline.py – Collective Attention System runnable pipeline entry point.

Usage:
    python run_pipeline.py [--top N] [--output path/to/output.json] [--report path/to/report.md]
    python run_pipeline.py --mock           # use offline demo data (no internet needed)

This script:
  1. Loads seed events (hardcoded Taiwan events)
  2. Resolves Wikipedia canonical pages
  3. Fetches Wikipedia pageviews
  4. Counts news articles
  5. Fetches Google Trends scores
  6. Computes final explainable score
  7. Prints top-N events to stdout
  8. Optionally saves results as JSON and/or a Markdown report
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import List

from agents.event_detection import EventDetectionAgent
from agents.event_identity import EventIdentityAgent
from agents.news_signal import NewsSignalAgent
from agents.scoring import ScoringAgent
from agents.search_signal import SearchSignalAgent
from agents.wiki_signal import WikiSignalAgent
from core.models import Event, compute_score
from core.pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)

# ---------------------------------------------------------------------------
# Mock / offline demo data
# ---------------------------------------------------------------------------

# Pre-populated realistic signal values so the pipeline can be demonstrated
# without live internet access.  Values are representative of historical data.
_MOCK_SIGNALS: dict[str, dict] = {
    "普悠瑪列車出軌事故": {
        "canonical_wiki_title": "普悠瑪列車出軌事故",
        "wiki_redirect_pages": ["台鐵1051021事故", "普悠瑪事故"],
        "wiki_views": 285_000,
        "news_count": 47,
        "search_score": 62.5,
    },
    "鄭捷事件": {
        "canonical_wiki_title": "鄭捷事件",
        "wiki_redirect_pages": ["台北捷運隨機殺人事件", "鄭捷殺人事件"],
        "wiki_views": 320_000,
        "news_count": 55,
        "search_score": 58.3,
    },
    "花蓮地震": {
        "canonical_wiki_title": "2018年花蓮地震",
        "wiki_redirect_pages": ["0206花蓮地震", "花蓮206地震"],
        "wiki_views": 410_000,
        "news_count": 89,
        "search_score": 74.1,
    },
    "太陽花學運": {
        "canonical_wiki_title": "太陽花學運",
        "wiki_redirect_pages": ["佔領立法院事件", "318學運", "反服貿運動"],
        "wiki_views": 890_000,
        "news_count": 132,
        "search_score": 88.7,
    },
    "COVID-19台灣疫情": {
        "canonical_wiki_title": "2019冠狀病毒病台灣疫情",
        "wiki_redirect_pages": ["台灣COVID-19疫情", "新冠肺炎台灣疫情"],
        "wiki_views": 1_540_000,
        "news_count": 241,
        "search_score": 95.2,
    },
    # ── New events (past 5 years) ──────────────────────────────────────────
    "太魯閣號出軌事故": {
        "canonical_wiki_title": "太魯閣號列車出軌事故",
        "wiki_redirect_pages": ["台鐵408次事故", "2021年太魯閣號事故", "清水隧道事故"],
        "wiki_views": 380_000,
        "news_count": 95,
        "search_score": 71.3,
    },
    "裴洛西訪台": {
        "canonical_wiki_title": "南希·裴洛西訪台",
        "wiki_redirect_pages": ["佩洛西訪台", "裴洛西台灣行", "2022年台海危機"],
        "wiki_views": 520_000,
        "news_count": 118,
        "search_score": 82.4,
    },
    "2022年九合一選舉": {
        "canonical_wiki_title": "2022年中華民國地方公職人員選舉",
        "wiki_redirect_pages": ["2022地方選舉", "九合一選舉2022"],
        "wiki_views": 190_000,
        "news_count": 76,
        "search_score": 63.8,
    },
    "2024年台灣總統大選": {
        "canonical_wiki_title": "2024年中華民國總統選舉",
        "wiki_redirect_pages": ["2024總統大選", "賴清德當選", "台灣2024選舉"],
        "wiki_views": 650_000,
        "news_count": 148,
        "search_score": 86.5,
    },
    "2024年花蓮強震": {
        "canonical_wiki_title": "2024年花蓮地震",
        "wiki_redirect_pages": ["0403花蓮地震", "2024花蓮強震", "花蓮7.4地震"],
        "wiki_views": 430_000,
        "news_count": 102,
        "search_score": 78.9,
    },
}


def _apply_mock_signals(events: List[Event]) -> None:
    """Inject pre-populated demo signals into events (for offline use)."""
    for event in events:
        mock = _MOCK_SIGNALS.get(event.title)
        if mock is None:
            continue
        event.canonical_wiki_title = mock["canonical_wiki_title"]
        event.wiki_redirect_pages = list(mock["wiki_redirect_pages"])
        if event.signals is None:
            from core.models import Signals

            event.signals = Signals(event_id=event.id)
        event.signals.wiki_views = mock["wiki_views"]
        event.signals.news_count = mock["news_count"]
        event.signals.search_score = mock["search_score"]
        breakdown = compute_score(event.signals)
        event.score_breakdown = breakdown
        event.score = breakdown.total


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_results(events: List[Event]) -> None:
    """Print ranked results to stdout in a readable table format."""
    width = 62
    print()
    print("┌" + "─" * width + "┐")
    print(f"│{'  TOP ' + str(len(events)) + ' EVENTS – COLLECTIVE ATTENTION (TAIWAN)':^{width}}│")
    print(f"│{'  Ranked by: log(wiki_views+1) + log(news_count+1) + search_score':^{width}}│")
    print("├" + "─" * width + "┤")

    for rank, event in enumerate(events, 1):
        sb = event.score_breakdown
        signals = event.signals
        print(f"│{'':^{width}}│")
        title_line = f"  #{rank}  {event.title}"
        print(f"│{title_line:<{width}}│")
        score_line = f"       Score       : {event.score:.2f}"
        print(f"│{score_line:<{width}}│")
        if sb:
            expl_line = f"       Explanation : {sb.explanation}"
            # Wrap long explanation lines
            if len(expl_line) > width:
                expl_line = expl_line[: width - 3] + "..."
            print(f"│{expl_line:<{width}}│")
            bdwn_line = (
                f"       Components  : wiki={sb.wiki_component:.2f} | "
                f"news={sb.news_component:.2f} | "
                f"search={sb.search_component:.2f}"
            )
            print(f"│{bdwn_line:<{width}}│")
        if signals:
            sig_line = (
                f"       Raw signals : wiki_views={signals.wiki_views:,} | "
                f"news={signals.news_count} | "
                f"search={signals.search_score:.1f}"
            )
            print(f"│{sig_line:<{width}}│")
        if event.canonical_wiki_title:
            wiki_line = f"       Wikipedia   : {event.canonical_wiki_title}"
            print(f"│{wiki_line:<{width}}│")
        if event.start_date:
            date_str = str(event.start_date)
            if event.end_date and event.end_date != event.start_date:
                date_str += f" → {event.end_date}"
            date_line = f"       Date        : {date_str}"
            print(f"│{date_line:<{width}}│")
        if rank < len(events):
            print("├" + "─" * width + "┤")

    print(f"│{'':^{width}}│")
    print("└" + "─" * width + "┘")
    print()


def _save_json(events: List[Event], path: str) -> None:
    """Save events as a JSON file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(events),
        "events": [e.to_dict() for e in events],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logging.getLogger(__name__).info("JSON output saved to %s", path)


def _save_markdown(events: List[Event], path: str, is_mock: bool = False) -> None:
    """Save a human-readable Markdown report."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lines: List[str] = []
    lines.append("# Collective Attention – Taiwan Events Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    if is_mock:
        lines.append("")
        lines.append(
            "> ⚠️ **Offline / demo mode** – signals are pre-populated representative values,"
            " not live API data."
        )
    lines.append("")
    lines.append("## Scoring Formula")
    lines.append("")
    lines.append("```")
    lines.append("score = log(wiki_views + 1)   # Wikipedia component")
    lines.append("      + log(news_count + 1)   # News component")
    lines.append("      + search_score          # Google Trends component (0–100)")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Rankings")
    lines.append("")

    # Summary table
    lines.append("| Rank | Event | Score | Wiki Views | News | Search |")
    lines.append("|-----:|-------|------:|-----------:|-----:|-------:|")
    for rank, event in enumerate(events, 1):
        s = event.signals
        wiki_views = f"{s.wiki_views:,}" if s else "—"
        news_count = str(s.news_count) if s else "—"
        search_score = f"{s.search_score:.1f}" if s else "—"
        lines.append(
            f"| {rank} | {event.title} | {event.score:.2f}"
            f" | {wiki_views} | {news_count} | {search_score} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Detailed breakdown
    lines.append("## Detailed Breakdown")
    lines.append("")
    for rank, event in enumerate(events, 1):
        sb = event.score_breakdown
        s = event.signals
        lines.append(f"### #{rank} {event.title}")
        lines.append("")
        if event.start_date:
            date_str = str(event.start_date)
            if event.end_date and event.end_date != event.start_date:
                date_str += f" → {event.end_date}"
            lines.append(f"**Date:** {date_str}")
            lines.append("")
        if event.canonical_wiki_title:
            lines.append(f"**Wikipedia:** {event.canonical_wiki_title}")
            if event.wiki_redirect_pages:
                lines.append(
                    f"**Redirects:** {', '.join(event.wiki_redirect_pages)}"
                )
            lines.append("")
        lines.append(f"**Score:** `{event.score:.4f}`")
        lines.append("")
        if sb:
            lines.append(f"**Explanation:** {sb.explanation}")
            lines.append("")
            lines.append("| Component | Raw Value | Score Component |")
            lines.append("|-----------|-----------|----------------|")
            wiki_raw = f"{s.wiki_views:,}" if s else "0"
            news_raw = str(s.news_count) if s else "0"
            search_raw = f"{s.search_score:.1f}" if s else "0.0"
            lines.append(
                f"| Wikipedia pageviews | {wiki_raw} | {sb.wiki_component:.4f} |"
            )
            lines.append(
                f"| News articles | {news_raw} | {sb.news_component:.4f} |"
            )
            lines.append(
                f"| Google Trends score | {search_raw} | {sb.search_component:.4f} |"
            )
            lines.append(f"| **Total** | | **{sb.total:.4f}** |")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Improvement Suggestions")
    lines.append("")
    lines.append(
        "1. **Historical news signal** ✅ – `NewsSignalAgent` now supports a `use_gdelt=True`"
        " parameter that queries the GDELT DOC 2.0 API for historical article counts keyed to"
        " event date ranges, supplementing the RSS signal with years of archive data."
    )
    lines.append(
        "2. **Search signal rate-limit** ✅ – `SearchSignalAgent` now retries up to"
        " `max_retries` times with exponential back-off and random jitter on any transient"
        " pytrends failure, dramatically reducing the impact of HTTP 429 throttling."
    )
    lines.append(
        "3. **Score normalisation** ✅ – `compute_score()` now accepts `wiki_weight`,"
        " `news_weight`, and `search_weight` parameters so callers can re-balance the three"
        " components without touching the formula.  Default weights of 1.0 preserve backward"
        " compatibility."
    )
    lines.append(
        "4. **Event deduplication** ✅ – `EventDetectionAgent` now uses Jaccard keyword-overlap"
        " scoring (threshold 0.4) to detect near-duplicate RSS articles that describe a seed"
        " event under a slightly different headline, not just exact title matching."
    )
    lines.append(
        "5. **Persistent cache** ✅ – `core/cache.py` introduces a `CacheStore` backed by"
        " per-agent JSON files in `.cache/`.  All three signal agents use it by default"
        " (`use_cache=True`) so repeated pipeline runs skip redundant API calls."
    )
    lines.append(
        "6. **Output format** – expose a `--format csv` option so results can be"
        " loaded directly into spreadsheets or BI tools."
    )
    lines.append(
        "7. **Cross-lingual coverage** ✅ – `WikiSignalAgent` now fetches English Wikipedia"
        " pageviews in addition to the primary Chinese article when `include_en=True`"
        " (the new default).  Avoids under-counting for internationally notable events"
        " such as COVID-19 and the Pelosi visit."
    )
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logging.getLogger(__name__).info("Markdown report saved to %s", path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Collective Attention pipeline"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top events to display (default: 10)",
    )
    parser.add_argument(
        "--rss",
        type=str,
        default=None,
        help="Optional RSS feed URL to ingest additional events",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="Save ranked events as JSON to FILE (e.g. output/results.json)",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        metavar="FILE",
        help="Save a Markdown report to FILE (e.g. output/report.md)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help=(
            "Use pre-populated demo signals instead of live API calls. "
            "Useful for offline/CI environments."
        ),
    )
    args = parser.parse_args()

    pipeline = Pipeline(
        event_detection_agent=EventDetectionAgent(
            rss_url=args.rss,
            include_seeds=True,
        ),
        event_identity_agent=EventIdentityAgent(),
        wiki_signal_agent=WikiSignalAgent(),
        news_signal_agent=NewsSignalAgent(),
        search_signal_agent=SearchSignalAgent(fallback_score=0.0),
        scoring_agent=ScoringAgent(),
    )

    if args.mock:
        logging.getLogger(__name__).info(
            "Mock mode: skipping live API calls, using pre-populated demo signals"
        )
        # Detect events only (no network calls for identity/signals/scoring)
        events_all = pipeline.event_detection.detect()
        _apply_mock_signals(events_all)
        events = sorted(events_all, key=lambda e: e.score, reverse=True)[: args.top]
    else:
        events = pipeline.run(top_n=args.top)

    _print_results(events)

    if args.output:
        _save_json(events, args.output)
        print(f"  ✓ JSON saved  → {args.output}")

    if args.report:
        _save_markdown(events, args.report, is_mock=args.mock)
        print(f"  ✓ Report saved → {args.report}")
        print()


if __name__ == "__main__":
    main()

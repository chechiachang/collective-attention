"""
run_pipeline.py – Collective Attention System runnable pipeline entry point.

Usage:
    python run_pipeline.py [--top N]

This script:
  1. Loads seed events (hardcoded Taiwan events)
  2. Resolves Wikipedia canonical pages
  3. Fetches Wikipedia pageviews
  4. Counts news articles
  5. Fetches Google Trends scores
  6. Computes final explainable score
  7. Prints top-10 events to stdout
"""

from __future__ import annotations

import argparse
import logging
import sys

from agents.event_detection import EventDetectionAgent
from agents.event_identity import EventIdentityAgent
from agents.news_signal import NewsSignalAgent
from agents.scoring import ScoringAgent
from agents.search_signal import SearchSignalAgent
from agents.wiki_signal import WikiSignalAgent
from core.pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)


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

    events = pipeline.run(top_n=args.top)

    print("\n" + "=" * 60)
    print(f"  TOP {len(events)} EVENTS – COLLECTIVE ATTENTION (TAIWAN)")
    print("=" * 60)
    for rank, event in enumerate(events, 1):
        sb = event.score_breakdown
        signals = event.signals
        print(f"\n#{rank}  {event.title}")
        print(f"    Score      : {event.score:.4f}")
        if sb:
            print(f"    Explanation: {sb.explanation}")
            print(
                f"    Breakdown  : wiki={sb.wiki_component:.2f} | "
                f"news={sb.news_component:.2f} | "
                f"search={sb.search_component:.2f}"
            )
        if signals:
            print(
                f"    Raw signals: wiki_views={signals.wiki_views:,} | "
                f"news_count={signals.news_count} | "
                f"search_score={signals.search_score:.1f}"
            )
        if event.canonical_wiki_title:
            print(f"    Wikipedia  : {event.canonical_wiki_title}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

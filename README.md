# Collective Attention System

> Reconstructing **collective human memory** from observable signals.

A data pipeline and API that quantifies which real-world events people collectively cared about during a given time period, using explainable, multi-source scoring.

---

## What It Does

The system answers:

> *"What events did people collectively care about in Taiwan between 2014 and 2024?"*

It collects three independent signals for each event —

| Signal | Source | Metric |
|--------|--------|--------|
| **Wikipedia traffic** | Wikimedia Pageviews REST API | total pageviews across canonical page + all redirects |
| **News coverage** | RSS feeds (CNA, Liberty Times) | article count matching event keywords |
| **Search interest** | Google Trends via `pytrends` | normalised score 0–100 (anchored to `台灣`) |

— combines them with a transparent log-scale formula, and returns a ranked list of events with a human-readable explanation for every score.

---

## Architecture

```
SEED_EVENTS / RSS feed
      ↓
EventDetectionAgent      agents/event_detection.py
      ↓
EventIdentityAgent       agents/event_identity.py   (Wikipedia canonical + redirects)
      ↓
 ┌────┴──────────────────────┐
 ↓                           ↓                        ↓
WikiSignalAgent         NewsSignalAgent          SearchSignalAgent
agents/wiki_signal.py   agents/news_signal.py    agents/search_signal.py
 └────┬──────────────────────┘
      ↓
ScoringAgent             agents/scoring.py
      ↓
Ranked event list        core/pipeline.py  →  api/main.py
```

### Scoring formula

```
score = log(wiki_views + 1)   # wiki_component
      + log(news_count + 1)   # news_component
      + search_score          # search_component  (already 0–100 normalised)
```

Every score ships with a `score_breakdown` object explaining each component in plain language.

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)

---

## Quick Start

```bash
# 1. Install uv (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone and enter the repo
git clone https://github.com/chechiachang/collective-attention.git
cd collective-attention

# 3. Install all dependencies (runtime + dev)
uv sync --all-extras

# 4. Run the pipeline (top-10 events, seed data only)
uv run python run_pipeline.py

# 5. Or start the API server
uv run uvicorn api.main:app --reload
```

---

## CLI

```bash
# Default: top 10 seed events
uv run python run_pipeline.py

# Custom top-N and live RSS ingestion
uv run python run_pipeline.py --top 20 --rss https://example.com/feed.xml
```

---

## API

```bash
uv run uvicorn api.main:app --reload
# Swagger UI: http://localhost:8000/docs
```

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/events/top?n=10` | Top-N ranked events with score breakdown |
| `GET` | `/events/{event_id}` | Single event by ID |
| `GET` | `/health` | Health check |

**Example response (`/events/top?n=1`):**

```json
{
  "count": 1,
  "events": [
    {
      "id": "e1863468",
      "title": "普悠瑪列車出軌事故",
      "start_date": "2018-10-21",
      "end_date": "2018-10-21",
      "keywords": ["普悠瑪", "出軌", "台鐵", "事故", "宜蘭"],
      "canonical_wiki_title": "普悠瑪列車出軌事故",
      "score": 58.81,
      "score_breakdown": {
        "wiki_component": 11.92,
        "news_component": 4.39,
        "search_component": 42.50,
        "total": 58.81,
        "explanation": "High Wikipedia traffic; high news coverage; moderate search interest."
      },
      "signals": {
        "wiki_views": 150000,
        "news_count": 80,
        "search_score": 42.5
      }
    }
  ]
}
```

---

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Format
uv run black .

# Lint
uv run ruff check .

# Type check
uv run mypy .

# Tests
uv run pytest

# All checks at once
make check
```

See the [Makefile](Makefile) for all available targets.

---

## Seed Events (MVP)

| Title | Period |
|-------|--------|
| 普悠瑪列車出軌事故 | 2018-10-21 |
| 鄭捷事件 | 2014-05-21 |
| 花蓮地震 | 2018-02-06 |
| 太陽花學運 | 2014-03-18 – 2014-04-10 |
| COVID-19台灣疫情 | 2020-01-21 – 2022-12-31 |

---

## Project Structure

```
collective-attention/
├── agents/                  # One agent per signal source
│   ├── event_detection.py   # Seed events + RSS ingestion
│   ├── event_identity.py    # Wikipedia canonical page resolution
│   ├── wiki_signal.py       # Wikimedia Pageviews API
│   ├── news_signal.py       # RSS news article counting
│   ├── search_signal.py     # Google Trends via pytrends
│   └── scoring.py           # Score assembly
├── api/
│   └── main.py              # FastAPI application
├── core/
│   ├── models.py            # Event, Signals, ScoreBreakdown, compute_score()
│   └── pipeline.py          # Pipeline orchestrator
├── tests/
│   └── test_system.py       # Offline unit tests (no network calls)
├── run_pipeline.py          # CLI entry point
├── pyproject.toml           # Project metadata + tool config
├── Makefile                 # Dev convenience targets
└── .github/workflows/ci.yml # CI: fmt + lint + type-check + test
```

---

## Known Limitations

| Challenge | Mitigation |
|-----------|-----------|
| Event fragmentation from RSS | Seed deduplication in MVP; HDBSCAN clustering planned |
| Wikipedia page renames | Redirect aggregation in `EventIdentityAgent` |
| Search score normalisation | Anchor keyword `台灣` in every pytrends request |
| pytrends rate limits | 1 s delay between requests; graceful fallback to 0 |
| Bias transparency | Every event exposes `score_breakdown` |

---

## Roadmap

- [ ] HDBSCAN clustering for RSS-derived event detection
- [ ] Wikidata entity linking (`wikidata_id`)
- [ ] GDELT / Media Cloud for historical news signal
- [ ] Social signals (PTT / Dcard / Reddit)
- [ ] Time-series visualisation
- [ ] Cross-language aggregation (zh + en Wikipedia)
- [ ] Long-term memory decay modelling

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

When you open or update a pull request, a live preview of `docs/index.html` is automatically
deployed to GitHub Pages and linked in a PR comment:

```
https://chechia.net/collective-attention/pr-preview/pr-<number>/
```

---

## License

[MIT](LICENSE)

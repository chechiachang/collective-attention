# Collective Attention System — Agent Collaboration Guide

## 🎯 Objective

Build a system that quantifies **collective attention of real-world events** using multi-source signals, with **explainable scoring**.

The system should answer:

> "What events did people collectively care about during a given time period?"

---

## 🧱 Core Principles

1. **No single source is truth**
2. **All signals must be explainable**
3. **Event > keyword**
4. **Prefer reproducibility over accuracy illusion**

---

## 🧠 Core Abstractions

### Event (`core/models.py`)

```python
@dataclass
class Event:
    id: str                          # deterministic MD5-derived short ID
    title: str
    start_date: Optional[date]
    end_date: Optional[date]
    keywords: List[str]
    canonical_wiki_title: Optional[str]
    wiki_redirect_pages: List[str]
    signals: Optional[Signals]
    score_breakdown: Optional[ScoreBreakdown]
    score: float
```

JSON representation:

```json
{
  "id": "e1863468",
  "title": "普悠瑪列車出軌事故",
  "start_date": "2018-10-21",
  "end_date": "2018-10-21",
  "keywords": ["普悠瑪", "出軌", "台鐵", "事故", "宜蘭"],
  "canonical_wiki_title": "普悠瑪列車出軌事故",
  "wiki_redirect_pages": [],
  "score": 12.34,
  "signals": {
    "event_id": "e1863468",
    "wiki_views": 150000,
    "news_count": 80,
    "search_score": 42.5
  },
  "score_breakdown": {
    "wiki_component": 11.92,
    "news_component": 4.39,
    "search_component": 42.5,
    "total": 58.81,
    "explanation": "High Wikipedia traffic; high news coverage; moderate search interest."
  }
}
```

---

## 🔄 Data Flow

```
SEED_EVENTS / RSS feed
      ↓
Event Detection Agent      (agents/event_detection.py)
      ↓
Event Identity Agent       (agents/event_identity.py)
      ↓
 ┌────┴────────────────┐
 ↓                     ↓                     ↓
Wiki Signal Agent   News Signal Agent   Search Signal Agent
(wiki_signal.py)    (news_signal.py)    (search_signal.py)
 └────┬────────────────┘
      ↓
Scoring Agent              (agents/scoring.py)
      ↓
Ranked events list         (core/pipeline.py  →  api/main.py)
```

---

## 🤖 Agent Roles

---

### 1️⃣ Event Detection Agent

**File:** `agents/event_detection.py`

**Goal:** Produce candidate `Event` objects from seed data and/or live RSS feeds.

**Input:**

* Hardcoded `SEED_EVENTS` list (5 Taiwan events, always included)
* Optional RSS feed URL (`rss_url` parameter)

**Output:**

```python
List[Event]   # each with id, title, keywords, start_date, end_date, signals=Signals(...)
```

**MVP seed events:**

| Title | Date |
|-------|------|
| 普悠瑪列車出軌事故 | 2018-10-21 |
| 鄭捷事件 | 2014-05-21 |
| 花蓮地震 | 2018-02-06 |
| 太陽花學運 | 2014-03-18 – 2014-04-10 |
| COVID-19台灣疫情 | 2020-01-21 – 2022-12-31 |

**RSS behaviour:**

* Parses up to 50 articles via `feedparser`
* Deduplicates against seed titles
* Fails gracefully (returns seeds only) when the feed is unreachable

**Future extensions:**

* Text embedding + HDBSCAN clustering to merge similar articles into events
* GDELT / Media Cloud ingestion

---

### 2️⃣ Event Identity Agent 🔥

**File:** `agents/event_identity.py`

**Goal:** Map each event → canonical Wikipedia page + all redirect pages.

**Input:**

* `event.title` and `event.keywords`

**Output** (written to event in-place):

```python
event.canonical_wiki_title  # e.g. "普悠瑪列車出軌事故"
event.wiki_redirect_pages   # e.g. ["台鐵1051021事故", ...]
```

**Implementation:**

* Primary language: `zh` (Traditional Chinese Wikipedia)
* Fallback language: `en` (uses `event.keywords[0]` as query)
* MediaWiki API endpoints used:
  * `action=query&list=search` — find canonical title
  * `action=query&prop=redirects` — collect all redirect pages
* No API key required; polite `User-Agent` header sent

**Known challenges:**

* Wikipedia page renames → solved by redirect aggregation
* Ambiguous titles → resolved by taking the top search result

---

### 3️⃣ Wikipedia Signal Agent

**File:** `agents/wiki_signal.py`

**Goal:** Compute total pageviews for an event's Wikipedia presence.

**Input:**

* `event.canonical_wiki_title`
* `event.wiki_redirect_pages`

**Output** (written to event in-place):

```python
event.signals.wiki_views   # int, sum across canonical + all redirects
```

**API:** `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/all-access/all-agents/{article}/monthly/{start}/{end}`

**Date window:**

* Default: `1 month before start_date` → `3 months after end_date`
* Falls back to `2014-01-01` – `2024-12-31` when event has no dates

**Rules:**

* Sums pageviews across canonical page and every redirect
* Returns 0 on 404 (page not yet created at that date range)
* Fails gracefully on network errors

---

### 4️⃣ News Signal Agent

**File:** `agents/news_signal.py`

**Goal:** Quantify media coverage by counting articles that mention event keywords.

**Input:**

* `event.keywords`

**Output** (written to event in-place):

```python
event.signals.news_count   # int, total matching articles across all feeds
```

**Default RSS feeds (Taiwan, Chinese):**

| Feed | Source |
|------|--------|
| `https://www.cna.com.tw/rss/aall.aspx` | Central News Agency |
| `https://news.ltn.com.tw/rss/all.xml` | Liberty Times |

**Matching logic:** keyword substring match on article `title + summary` (case-insensitive).

**Future extensions:**

* GDELT API (historical coverage)
* Media Cloud API
* Time-series output (article counts per day/week)

---

### 5️⃣ Search Signal Agent

**File:** `agents/search_signal.py`

**Goal:** Approximate public search interest via Google Trends.

**Input:**

* `event.keywords[0]` (primary keyword)

**Output** (written to event in-place):

```python
event.signals.search_score   # float in [0, 100]
```

**Implementation:**

* Uses `pytrends.TrendReq` (locale `zh-TW`, timezone `UTC+8`, geo `TW`)
* Always includes anchor keyword `"台灣"` to normalise relative scores
* Timeframe: `2014-01-01 2024-12-31`
* Normalisation formula: `score = (keyword_mean / anchor_mean) × 50`, clamped to `[0, 100]`
* 1-second delay between requests to avoid rate-limiting (HTTP 429)
* Falls back to `fallback_score=0.0` when pytrends is not installed or the request fails

---

### 6️⃣ Scoring Agent 🔥

**File:** `agents/scoring.py`  |  formula in `core/models.py:compute_score()`

**Goal:** Combine signals into a single explainable attention score.

**Input:**

* `event.signals` (`wiki_views`, `news_count`, `search_score`)

**Output** (written to event in-place):

```python
event.score            # float, total score
event.score_breakdown  # ScoreBreakdown with per-signal components + explanation
```

**Formula (v1 — no black-box ML):**

```
score = log(wiki_views + 1)   # wiki_component
      + log(news_count + 1)   # news_component
      + search_score          # search_component  (already 0–100 normalised)
```

The `+1` guards against `log(0)`.

**Score breakdown example:**

```json
{
  "wiki_component":   11.92,
  "news_component":    4.39,
  "search_component": 42.50,
  "total":            58.81,
  "explanation": "High Wikipedia traffic; high news coverage; moderate search interest."
}
```

**Explainability tiers:**

| Signal | Threshold | Label |
|--------|-----------|-------|
| `wiki_views` | > 100 000 | Very high Wikipedia traffic |
| | > 10 000 | High Wikipedia traffic |
| | > 1 000 | Moderate Wikipedia traffic |
| | ≤ 1 000 | Low Wikipedia traffic |
| `news_count` | > 100 | Very high news coverage |
| | > 20 | High news coverage |
| | > 5 | Moderate news coverage |
| | ≤ 5 | Low news coverage |
| `search_score` | > 70 | High search interest |
| | > 30 | Moderate search interest |
| | ≤ 30 | Low search interest |

---

### 7️⃣ Social Signal Agent *(optional / future)*

**Goal:** Measure discussion intensity on social platforms.

**Planned sources:** PTT, Dcard, Reddit

**Not yet implemented in MVP.**

---

## 🔌 External APIs

| Agent | API | Auth |
|-------|-----|------|
| Event Identity | MediaWiki API (`zh.wikipedia.org/w/api.php`) | None |
| Wikipedia Signal | Wikimedia Pageviews REST API | None |
| News Signal | RSS feeds (CNA, Liberty Times) | None |
| Search Signal | Google Trends via `pytrends` | None (unofficial) |

---

## 🗄️ Data Model Summary

```
Event
├── id                    str       MD5-derived 8-char hex
├── title                 str
├── start_date            date?
├── end_date              date?
├── keywords              List[str]
├── canonical_wiki_title  str?
├── wiki_redirect_pages   List[str]
├── score                 float
├── signals               Signals?
│   ├── wiki_views        int
│   ├── news_count        int
│   └── search_score      float     0–100
└── score_breakdown       ScoreBreakdown?
    ├── wiki_component    float
    ├── news_component    float
    ├── search_component  float
    ├── total             float
    └── explanation       str
```

---

## 🚀 Running the Pipeline

### CLI

```bash
python run_pipeline.py          # top 10 events
python run_pipeline.py --top 50 --rss https://example.com/feed.xml
```

### API server

```bash
uvicorn api.main:app --reload
```

Endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/events/top?n=10` | Top-N ranked events with score breakdown |
| `GET` | `/events/{event_id}` | Single event by ID |
| `GET` | `/health` | Health check |

---

## 🧪 MVP Scope

* Region: Taiwan
* Period: 2014–2024
* Sources: Wikipedia pageviews, RSS news, Google Trends
* Output: top 50 events ranked by collective-attention score

---

## ⚠️ Known Challenges

| Challenge | Mitigation |
|-----------|-----------|
| Event fragmentation | Merge RSS clusters by keyword overlap (seed deduplication in MVP) |
| Wikipedia page rename | Redirect aggregation in WikiSignalAgent |
| Search normalisation | Anchor keyword `"台灣"` in every pytrends request |
| Bias transparency | Always expose `score_breakdown` with per-signal components |
| pytrends rate limits | 1 s delay between requests; graceful fallback to 0 |

---

## 📊 Success Criteria

* Can rank:

  * 普悠瑪事故
  * 鄭捷事件
  * 花蓮地震

* Scores are:

  * **Stable** — deterministic IDs, reproducible signal fetches
  * **Explainable** — every point in `score_breakdown` is human-readable
  * **Reproducible** — no random or black-box components

---

## 🚀 Future Extensions

* HDBSCAN clustering for RSS-derived event detection
* Wikidata entity linking (`wikidata_id` field)
* GDELT / Media Cloud for historical news signal
* Social signals (PTT / Dcard / Reddit)
* Time-series visualisation
* Cross-language aggregation (zh + en Wikipedia)
* Long-term memory decay modelling

---

## 🧭 Philosophy

We are not building a trend tool.

We are building:

> A system that reconstructs **collective human memory** from observable signals.

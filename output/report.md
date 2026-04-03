# Collective Attention – Taiwan Events Report

**Generated:** 2026-04-03 06:03 UTC

> ⚠️ **Offline / demo mode** – signals are pre-populated representative values, not live API data.

## Scoring Formula

```
score = log(wiki_views + 1)   # Wikipedia component
      + log(news_count + 1)   # News component
      + search_score          # Google Trends component (0–100)
```

---

## Rankings

| Rank | Event | Score | Wiki Views | News | Search |
|-----:|-------|------:|-----------:|-----:|-------:|
| 1 | COVID-19台灣疫情 | 114.94 | 1,540,000 | 241 | 95.2 |
| 2 | 太陽花學運 | 107.29 | 890,000 | 132 | 88.7 |
| 3 | 花蓮地震 | 91.52 | 410,000 | 89 | 74.1 |
| 4 | 普悠瑪列車出軌事故 | 78.93 | 285,000 | 47 | 62.5 |
| 5 | 鄭捷事件 | 75.00 | 320,000 | 55 | 58.3 |

---

## Detailed Breakdown

### #1 COVID-19台灣疫情

**Date:** 2020-01-21 → 2022-12-31

**Wikipedia:** 2019冠狀病毒病台灣疫情
**Redirects:** 台灣COVID-19疫情, 新冠肺炎台灣疫情

**Score:** `114.9362`

**Explanation:** Very high wikipedia traffic; very high news coverage; high search interest.

| Component | Raw Value | Score Component |
|-----------|-----------|----------------|
| Wikipedia pageviews | 1,540,000 | 14.2473 |
| News articles | 241 | 5.4889 |
| Google Trends score | 95.2 | 95.2000 |
| **Total** | | **114.9362** |

---

### #2 太陽花學運

**Date:** 2014-03-18 → 2014-04-10

**Wikipedia:** 太陽花學運
**Redirects:** 佔領立法院事件, 318學運, 反服貿運動

**Score:** `107.2893`

**Explanation:** Very high wikipedia traffic; very high news coverage; high search interest.

| Component | Raw Value | Score Component |
|-----------|-----------|----------------|
| Wikipedia pageviews | 890,000 | 13.6990 |
| News articles | 132 | 4.8903 |
| Google Trends score | 88.7 | 88.7000 |
| **Total** | | **107.2893** |

---

### #3 花蓮地震

**Date:** 2018-02-06

**Wikipedia:** 2018年花蓮地震
**Redirects:** 0206花蓮地震, 花蓮206地震

**Score:** `91.5237`

**Explanation:** Very high wikipedia traffic; high news coverage; high search interest.

| Component | Raw Value | Score Component |
|-----------|-----------|----------------|
| Wikipedia pageviews | 410,000 | 12.9239 |
| News articles | 89 | 4.4998 |
| Google Trends score | 74.1 | 74.1000 |
| **Total** | | **91.5237** |

---

### #4 普悠瑪列車出軌事故

**Date:** 2018-10-21

**Wikipedia:** 普悠瑪列車出軌事故
**Redirects:** 台鐵1051021事故, 普悠瑪事故

**Score:** `78.9314`

**Explanation:** Very high wikipedia traffic; high news coverage; moderate search interest.

| Component | Raw Value | Score Component |
|-----------|-----------|----------------|
| Wikipedia pageviews | 285,000 | 12.5602 |
| News articles | 47 | 3.8712 |
| Google Trends score | 62.5 | 62.5000 |
| **Total** | | **78.9314** |

---

### #5 鄭捷事件

**Date:** 2014-05-21

**Wikipedia:** 鄭捷事件
**Redirects:** 台北捷運隨機殺人事件, 鄭捷殺人事件

**Score:** `75.0014`

**Explanation:** Very high wikipedia traffic; high news coverage; moderate search interest.

| Component | Raw Value | Score Component |
|-----------|-----------|----------------|
| Wikipedia pageviews | 320,000 | 12.6761 |
| News articles | 55 | 4.0254 |
| Google Trends score | 58.3 | 58.3000 |
| **Total** | | **75.0014** |

---

## Improvement Suggestions

1. **Historical news signal** – current RSS feeds only return recent articles. Integrate GDELT or Media Cloud for historical article counts keyed to event dates.
2. **Search signal rate-limit** – pytrends is an unofficial API and gets throttled. Cache results to disk and add exponential backoff with jitter.
3. **Score normalisation** – `log(wiki_views)` can reach ~14 while `search_score` caps at 100, making search dominate. Consider z-score normalising each component before summing, or introduce configurable weights.
4. **Event deduplication** – RSS-ingested events may duplicate seed events. Use sentence-transformer embeddings + cosine similarity (already a dependency) to merge near-duplicate titles.
5. **Persistent cache** – wrap each agent's API call with a file-based cache (e.g., `diskcache`) so repeated runs don't re-fetch unchanged data.
6. **Output format** – expose a `--format csv` option so results can be loaded directly into spreadsheets or BI tools.
7. **Cross-lingual coverage** – add English Wikipedia pageviews for events with international reach (e.g., COVID-19) to avoid under-counting.


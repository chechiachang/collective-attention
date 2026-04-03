"""
Event Identity Agent

Resolves a canonical Wikipedia page for each event and collects
redirect pages that should be aggregated when counting pageviews.

Uses the Wikipedia REST API (no API key required):
  https://en.wikipedia.org/api/rest_v1/
  https://zh.wikipedia.org/api/rest_v1/
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import List, Optional

import requests

from core.models import Event

logger = logging.getLogger(__name__)

WIKIPEDIA_API_URL = "https://{lang}.wikipedia.org/w/api.php"
DEFAULT_LANG = "zh"
REQUEST_TIMEOUT = 10  # seconds


class EventIdentityAgent:
    """
    Resolves Wikipedia canonical title and redirect pages for each event.

    Parameters
    ----------
    lang : str
        Wikipedia language code (default "zh" for Traditional Chinese).
    fallback_lang : str
        Secondary language to try when the primary language returns nothing.
    """

    def __init__(self, lang: str = DEFAULT_LANG, fallback_lang: str = "en"):
        self.lang = lang
        self.fallback_lang = fallback_lang
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "CollectiveAttentionBot/1.0 (research project)"}
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def resolve(self, event: Event) -> None:
        """
        Populate event.canonical_wiki_title and event.wiki_redirect_pages.
        Modifies the event object in place.
        """
        query = event.title
        canonical, redirects = self._resolve_title(query, self.lang)

        if canonical is None and self.fallback_lang:
            # Try English with the first keyword
            alt_query = event.keywords[0] if event.keywords else query
            canonical, redirects = self._resolve_title(alt_query, self.fallback_lang)

        event.canonical_wiki_title = canonical
        event.wiki_redirect_pages = redirects
        logger.debug(
            "EventIdentityAgent: '%s' → canonical='%s', redirects=%d",
            event.title,
            canonical,
            len(redirects),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_title(
        self, query: str, lang: str
    ) -> tuple[Optional[str], List[str]]:
        """
        Look up `query` on Wikipedia (lang edition).

        Returns (canonical_title, list_of_redirect_titles).
        """
        canonical = self._search_canonical(query, lang)
        if canonical is None:
            return None, []

        redirects = self._fetch_redirects(canonical, lang)
        return canonical, redirects

    def _search_canonical(self, query: str, lang: str) -> Optional[str]:
        """Use the Wikipedia search API to find the best matching page title."""
        url = WIKIPEDIA_API_URL.format(lang=lang)
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 1,
            "format": "json",
            "redirects": 1,
        }
        try:
            resp = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("query", {}).get("search", [])
            if results:
                return results[0]["title"]
        except requests.RequestException as exc:
            logger.warning("Wikipedia search failed for '%s' (%s): %s", query, lang, exc)
        return None

    def _fetch_redirects(self, title: str, lang: str) -> List[str]:
        """Fetch all pages that redirect to `title`."""
        url = WIKIPEDIA_API_URL.format(lang=lang)
        params = {
            "action": "query",
            "titles": title,
            "prop": "redirects",
            "rdlimit": "max",
            "format": "json",
        }
        redirects: List[str] = []
        try:
            resp = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                for rd in page.get("redirects", []):
                    redirects.append(rd["title"])
        except requests.RequestException as exc:
            logger.warning(
                "Redirect fetch failed for '%s' (%s): %s", title, lang, exc
            )
        return redirects

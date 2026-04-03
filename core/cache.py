"""
Persistent file-based JSON cache for agent signal fetches.  (Improvement #5)

Provides ``CacheStore``: a lightweight key-value store backed by per-agent
JSON files so that repeated pipeline runs skip redundant network calls.

Usage example::

    from core.cache import default_cache

    cached = default_cache.get("wiki_signal", page_title)
    if cached is not None:
        return cached
    result = _fetch_from_api(page_title)
    default_cache.set("wiki_signal", page_title, result)
    return result

The cache directory defaults to ``.cache/`` in the project root but can be
overridden via the ``CA_CACHE_DIR`` environment variable.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CacheStore:
    """
    Persistent JSON file-based cache.

    Each *agent_name* gets its own ``<cache_dir>/<agent_name>.json`` file.
    Entries are loaded lazily on first access and flushed to disk on every
    write.

    Parameters
    ----------
    cache_dir : str or Path, optional
        Directory for cache files.  Defaults to ``.cache/`` next to the
        project root.  Override with the ``CA_CACHE_DIR`` environment
        variable.
    """

    def __init__(self, cache_dir: Optional[str | Path] = None) -> None:
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            env_dir = os.environ.get("CA_CACHE_DIR", "")
            self.cache_dir = (
                Path(env_dir) if env_dir else Path(__file__).parent.parent / ".cache"
            )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, agent_name: str, key: str) -> Optional[Any]:
        """Return the cached value for *key* under *agent_name*, or None."""
        return self._load(agent_name).get(key)

    def set(self, agent_name: str, key: str, value: Any) -> None:
        """Store *value* under *agent_name*/*key* and persist to disk."""
        self._load(agent_name)[key] = value
        self._flush(agent_name)

    def invalidate(self, agent_name: str, key: str) -> None:
        """Remove a single cache entry (no-op if not present)."""
        bucket = self._load(agent_name)
        if key in bucket:
            del bucket[key]
            self._flush(agent_name)

    def clear(self, agent_name: Optional[str] = None) -> None:
        """Clear cache for one agent, or all agents when *agent_name* is None."""
        if agent_name:
            self._data[agent_name] = {}
            self._flush(agent_name)
        else:
            for name in list(self._data):
                self._data[name] = {}
                self._flush(name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _path(self, agent_name: str) -> Path:
        return self.cache_dir / f"{agent_name}.json"

    def _load(self, agent_name: str) -> dict:
        """Return the in-memory bucket, loading from disk on first access."""
        if agent_name not in self._data:
            path = self._path(agent_name)
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        self._data[agent_name] = json.load(fh)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Cache read failed for '%s': %s", agent_name, exc)
                    self._data[agent_name] = {}
            else:
                self._data[agent_name] = {}
        return self._data[agent_name]

    def _flush(self, agent_name: str) -> None:
        """Write the in-memory bucket to disk."""
        path = self._path(agent_name)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._data[agent_name], fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("Cache write failed for '%s': %s", agent_name, exc)


# ---------------------------------------------------------------------------
# Module-level default instance (shared across agents in the same process)
# ---------------------------------------------------------------------------

default_cache = CacheStore()

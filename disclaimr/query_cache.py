"""Thread-safe in-memory cache for milter LDAP lookups."""

from __future__ import annotations

import threading
import time
from typing import Any


class QueryCache:
    """Process-global cache for LDAP query results.

    The cache is keyed by ``(directory_server.id, query)``. Each directory
    server entry stores its own timeout (refreshed on every write, so a
    changed ``cache_timeout`` takes effect) plus the individual query results.

    Note that the milter forks one process per MTA connection, so an entry
    lives as long as that connection does.
    """

    _cache: dict[int, dict[str, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def get(cls, directory_server: Any, query: str) -> Any | None:
        """Return a cached query result or ``None`` if missing / timed out."""
        with cls._lock:
            ds_cache = cls._cache.get(directory_server.id)
            if ds_cache is None or query not in ds_cache:
                return None

            entry = ds_cache[query]
            if time.monotonic() - entry["timestamp"] > ds_cache["_timeout"]:
                return None
            return entry["data"]

    @classmethod
    def set(cls, directory_server: Any, query: str, data: Any) -> None:
        """Add a query result to the cache."""
        with cls._lock:
            ds_cache = cls._cache.setdefault(directory_server.id, {})
            ds_cache["_timeout"] = directory_server.cache_timeout
            ds_cache[query] = {
                "timestamp": time.monotonic(),
                "data": data,
            }

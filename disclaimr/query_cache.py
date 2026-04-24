"""Thread-safe in-memory cache for milter LDAP lookups."""

from __future__ import annotations

import datetime
import threading
from typing import Any


class QueryCache:
    """Process-global cache for LDAP query results.

    The cache is keyed by ``(directory_server.id, query)``. Each directory
    server entry stores its own timeout (set on first write) plus the
    individual query results.
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
            timeout = ds_cache["_timeout"]
            age = (datetime.datetime.now() - entry["timestamp"]).total_seconds()
            if age > timeout:
                return None
            return entry["data"]

    @classmethod
    def set(cls, directory_server: Any, query: str, data: Any) -> None:
        """Add a query result to the cache."""
        with cls._lock:
            ds_cache = cls._cache.setdefault(
                directory_server.id, {"_timeout": directory_server.cache_timeout}
            )
            ds_cache[query] = {
                "timestamp": datetime.datetime.now(),
                "data": data,
            }

    @classmethod
    def flush(cls) -> None:
        """Drop all timed-out entries from the cache."""
        with cls._lock:
            now = datetime.datetime.now()
            for ds_id in list(cls._cache):
                ds_cache = cls._cache[ds_id]
                timeout = ds_cache["_timeout"]
                for query in list(ds_cache):
                    if query == "_timeout":
                        continue
                    age = (now - ds_cache[query]["timestamp"]).total_seconds()
                    if age > timeout:
                        del ds_cache[query]
                if len(ds_cache) == 1:
                    del cls._cache[ds_id]

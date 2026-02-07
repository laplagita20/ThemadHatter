"""File-based cache with TTL support."""

import json
import hashlib
import time
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("stock_model.cache")


class FileCache:
    """Simple file-based cache with time-to-live expiration."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, key: str) -> Path:
        hashed = hashlib.sha256(key.encode()).hexdigest()[:16]
        safe_key = "".join(c if c.isalnum() else "_" for c in key)[:60]
        return self.cache_dir / f"{safe_key}_{hashed}.json"

    def get(self, key: str) -> Any | None:
        """Retrieve a cached value if it exists and hasn't expired."""
        path = self._key_path(key)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("expires_at", 0) < time.time():
                path.unlink(missing_ok=True)
                return None
            return data["value"]
        except (json.JSONDecodeError, KeyError, OSError):
            path.unlink(missing_ok=True)
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Store a value in the cache with a TTL."""
        path = self._key_path(key)
        data = {
            "value": value,
            "created_at": time.time(),
            "expires_at": time.time() + ttl_seconds,
            "key": key,
        }
        try:
            path.write_text(json.dumps(data, default=str), encoding="utf-8")
        except OSError as e:
            logger.warning("Cache write failed for %s: %s", key, e)

    def invalidate(self, key: str):
        """Remove a cached entry."""
        path = self._key_path(key)
        path.unlink(missing_ok=True)

    def clear(self):
        """Remove all cached entries."""
        for f in self.cache_dir.glob("*.json"):
            f.unlink(missing_ok=True)

    def cleanup_expired(self):
        """Remove all expired cache entries."""
        now = time.time()
        removed = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("expires_at", 0) < now:
                    f.unlink()
                    removed += 1
            except (json.JSONDecodeError, OSError):
                f.unlink(missing_ok=True)
                removed += 1
        if removed:
            logger.debug("Cleaned up %d expired cache entries", removed)

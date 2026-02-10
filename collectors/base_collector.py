"""Base collector ABC with rate limiting, caching, circuit breaker, and retry logic."""

import logging
import time
from abc import ABC, abstractmethod
from utils.rate_limiter import RateLimiter
from utils.cache import FileCache
from config.settings import get_settings

logger = logging.getLogger("stock_model.collectors.base")

# Circuit breaker settings
_CIRCUIT_MAX_FAILURES = 3
_CIRCUIT_COOLDOWN_SECS = 30 * 60  # 30 minutes


class BaseCollector(ABC):
    """Abstract base class for all data collectors."""

    name: str = "base"
    rate_limit: float = 2.0  # requests per second
    rate_period: float = 1.0  # period in seconds

    # Class-level circuit state shared across instances of the same collector
    _circuit_state: dict = {}  # {api_key: {"failures": int, "open_until": float}}

    def __init__(self):
        self.settings = get_settings()
        self._limiter = RateLimiter(self.rate_limit, self.rate_period)
        self._cache = FileCache(self.settings.cache_dir / self.name)

    # ------------------------------------------------------------------
    # Circuit breaker helpers
    # ------------------------------------------------------------------
    def _circuit_key(self, api_name: str = None) -> str:
        return f"{self.name}:{api_name or 'default'}"

    def _is_circuit_open(self, api_name: str = None) -> bool:
        key = self._circuit_key(api_name)
        state = self._circuit_state.get(key)
        if state and state["failures"] >= _CIRCUIT_MAX_FAILURES:
            if time.time() < state["open_until"]:
                return True
            # Cooldown expired — half-open, allow retry
            state["failures"] = _CIRCUIT_MAX_FAILURES - 1
        return False

    def _record_failure(self, api_name: str = None):
        key = self._circuit_key(api_name)
        state = self._circuit_state.setdefault(key, {"failures": 0, "open_until": 0})
        state["failures"] += 1
        if state["failures"] >= _CIRCUIT_MAX_FAILURES:
            state["open_until"] = time.time() + _CIRCUIT_COOLDOWN_SECS
            logger.warning(
                "%s: circuit breaker OPEN — %d consecutive failures, skipping for %d min",
                key, state["failures"], _CIRCUIT_COOLDOWN_SECS // 60,
            )

    def _record_success(self, api_name: str = None):
        key = self._circuit_key(api_name)
        if key in self._circuit_state:
            self._circuit_state[key] = {"failures": 0, "open_until": 0}

    def _rate_limited_call(self, func, *args, **kwargs):
        """Execute a function respecting rate limits with retries."""
        self._limiter.acquire()
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = func(*args, **kwargs)
                self._record_success()
                return result
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        "%s: attempt %d failed: %s, retrying in %ds",
                        self.name, attempt + 1, e, wait,
                    )
                    time.sleep(wait)
                else:
                    self._record_failure()
                    logger.error("%s: all %d attempts failed: %s", self.name, max_retries, e)
                    raise

    def _cached_call(self, key: str, func, *args, ttl: int = 3600, **kwargs):
        """Execute a function with caching. Falls back to stale cache when circuit is open."""
        cached = self._cache.get(key)
        if cached is not None:
            logger.debug("%s: cache hit for %s", self.name, key)
            return cached

        # Circuit breaker check — return stale cache if available
        if self._is_circuit_open():
            stale = self._cache.get(key, ignore_ttl=True) if hasattr(self._cache, 'get') else None
            if stale is not None:
                logger.info("%s: circuit open, returning stale cache for %s", self.name, key)
                return stale
            logger.warning("%s: circuit open and no cached data for %s", self.name, key)
            return None

        result = self._rate_limited_call(func, *args, **kwargs)
        if result is not None:
            self._cache.set(key, result, ttl_seconds=ttl)
        return result

    @abstractmethod
    def collect(self, ticker: str = None) -> dict:
        """Collect data, optionally for a specific ticker."""
        ...

    @abstractmethod
    def store(self, data: dict):
        """Store collected data in the database."""
        ...

    def collect_and_store(self, ticker: str = None):
        """Collect data and store it."""
        try:
            data = self.collect(ticker)
            if data:
                self.store(data)
                logger.info("%s: collected and stored data for %s", self.name, ticker or "all")
            return data
        except Exception as e:
            logger.error("%s: collect_and_store failed for %s: %s", self.name, ticker, e)
            return None

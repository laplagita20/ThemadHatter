"""Base collector ABC with rate limiting, caching, and retry logic."""

import logging
import time
from abc import ABC, abstractmethod
from utils.rate_limiter import RateLimiter
from utils.cache import FileCache
from config.settings import get_settings

logger = logging.getLogger("stock_model.collectors.base")


class BaseCollector(ABC):
    """Abstract base class for all data collectors."""

    name: str = "base"
    rate_limit: float = 2.0  # requests per second
    rate_period: float = 1.0  # period in seconds

    def __init__(self):
        self.settings = get_settings()
        self._limiter = RateLimiter(self.rate_limit, self.rate_period)
        self._cache = FileCache(self.settings.cache_dir / self.name)

    def _rate_limited_call(self, func, *args, **kwargs):
        """Execute a function respecting rate limits with retries."""
        self._limiter.acquire()
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        "%s: attempt %d failed: %s, retrying in %ds",
                        self.name, attempt + 1, e, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error("%s: all %d attempts failed: %s", self.name, max_retries, e)
                    raise

    def _cached_call(self, key: str, func, *args, ttl: int = 3600, **kwargs):
        """Execute a function with caching."""
        cached = self._cache.get(key)
        if cached is not None:
            logger.debug("%s: cache hit for %s", self.name, key)
            return cached

        result = self._rate_limited_call(func, *args, **kwargs)
        if result is not None:
            self._cache.set(key, result, ttl)
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

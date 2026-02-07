"""Token bucket rate limiter for API calls."""

import time
import threading


class RateLimiter:
    """Token bucket rate limiter.

    Args:
        rate: Maximum number of requests per period.
        period: Time period in seconds (default 1.0 = per second).
    """

    def __init__(self, rate: float, period: float = 1.0):
        self.rate = rate
        self.period = period
        self.tokens = rate
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.rate, self.tokens + elapsed * (self.rate / self.period))
        self.last_refill = now

    def acquire(self):
        """Block until a token is available, then consume one."""
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
            time.sleep(self.period / self.rate)

    def try_acquire(self) -> bool:
        """Try to consume a token without blocking. Returns True if successful."""
        with self._lock:
            self._refill()
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

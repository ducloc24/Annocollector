"""In-memory sliding-window limiter for login attempts.

Only correct with a single API process; move to a shared store before scaling out.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable

from app.core.exceptions import AppError

WINDOW_SECONDS = 60.0


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class SlidingWindowLimiter:
    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> None:
        """Record an attempt; raise when the key is over the limit."""
        now = self.clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self.limit:
            raise RateLimitedError("Too many attempts, try again later")
        hits.append(now)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

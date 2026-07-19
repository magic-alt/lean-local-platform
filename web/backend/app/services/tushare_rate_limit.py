from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timedelta, timezone
import os
import threading
import time
import uuid
from typing import Any, Callable

from ..core.config import REDIS_URL


DEFAULT_CALLS_PER_MINUTE = max(1, int(os.environ.get("LEAN_TUSHARE_CALLS_PER_MINUTE", "500")))


class TushareRateLimiter:
    """A token-wide rolling-window limiter shared by every TuShare caller.

    Redis provides cross-process coordination.  The in-process deque is a safe
    fallback for tests and for a temporarily unavailable Redis instance.
    """

    _LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count < limit then
  redis.call('ZADD', key, now, member)
  redis.call('PEXPIRE', key, math.ceil(window * 2))
  return {1, 0, count + 1}
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local wait = window
if oldest[2] then wait = math.max(1, tonumber(oldest[2]) + window - now) end
return {0, wait, count}
"""

    def __init__(self, *, calls_per_minute: int = DEFAULT_CALLS_PER_MINUTE) -> None:
        self.calls_per_minute = max(1, calls_per_minute)
        self._local: deque[float] = deque()
        self._endpoint_local: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._redis: Any | None = None
        try:
            import redis

            client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=0.5, socket_timeout=1)
            client.ping()
            self._redis = client
        except Exception:
            self._redis = None

    def _redis_wait(self) -> float | None:
        if self._redis is None:
            return None
        now_ms = int(time.time() * 1000)
        try:
            allowed, wait_ms, _ = self._redis.eval(
                self._LUA,
                1,
                "lean:tushare:rate:global",
                now_ms,
                60_000,
                self.calls_per_minute,
                f"{now_ms}:{uuid.uuid4().hex}",
            )
            return 0.0 if int(allowed) else max(0.001, int(wait_ms) / 1000.0)
        except Exception:
            self._redis = None
            return None

    def _local_wait(self) -> float:
        now = time.monotonic()
        with self._lock:
            while self._local and self._local[0] <= now - 60.0:
                self._local.popleft()
            if len(self._local) < self.calls_per_minute:
                self._local.append(now)
                return 0.0
            return max(0.001, self._local[0] + 60.0 - now)

    def acquire(self) -> None:
        while True:
            wait = self._redis_wait()
            if wait is None:
                wait = self._local_wait()
            if wait <= 0:
                return
            time.sleep(min(wait, 1.0))

    def acquire_endpoint(self, endpoint: str, *, calls: int, period_seconds: int, wait: bool) -> None:
        key = f"lean:tushare:rate:endpoint:{endpoint}"
        while True:
            wait_seconds: float | None = None
            if self._redis is not None:
                now_ms = int(time.time() * 1000)
                try:
                    allowed, wait_ms, _ = self._redis.eval(
                        self._LUA,
                        1,
                        key,
                        now_ms,
                        period_seconds * 1000,
                        calls,
                        f"{now_ms}:{uuid.uuid4().hex}",
                    )
                    wait_seconds = 0.0 if int(allowed) else max(0.001, int(wait_ms) / 1000.0)
                except Exception:
                    self._redis = None
            if wait_seconds is None:
                now = time.monotonic()
                with self._lock:
                    history = self._endpoint_local.setdefault(endpoint, deque())
                    while history and history[0] <= now - period_seconds:
                        history.popleft()
                    if len(history) < calls:
                        history.append(now)
                        wait_seconds = 0.0
                    else:
                        wait_seconds = max(0.001, history[0] + period_seconds - now)
            if wait_seconds <= 0:
                return
            if not wait:
                next_allowed = datetime.now(timezone.utc) + timedelta(seconds=wait_seconds)
                raise RuntimeError(
                    f"tushare_endpoint_rate_limited:{endpoint};nextAllowedAt={next_allowed.isoformat()}"
                )
            time.sleep(min(wait_seconds, 1.0))


_GLOBAL_LIMITER: TushareRateLimiter | None = None
_GLOBAL_LOCK = threading.Lock()


def global_tushare_limiter() -> TushareRateLimiter:
    global _GLOBAL_LIMITER
    with _GLOBAL_LOCK:
        if _GLOBAL_LIMITER is None:
            _GLOBAL_LIMITER = TushareRateLimiter()
        return _GLOBAL_LIMITER


class RateLimitedProProxy:
    """Proxy SDK methods so nested adapter calls also share the global quota."""

    def __init__(self, target: Any, limiter: TushareRateLimiter | None = None) -> None:
        self._target = target
        self._limiter = limiter or global_tushare_limiter()
        self._call_counts: Counter[str] = Counter()
        self._count_lock = threading.Lock()

    def call_counts(self) -> dict[str, int]:
        """Return a stable snapshot of actual SDK method invocations."""
        with self._count_lock:
            return dict(self._call_counts)

    def call_count(self) -> int:
        with self._count_lock:
            return sum(self._call_counts.values())

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._target, name)
        if not callable(value):
            return value

        def limited(*args: Any, **kwargs: Any) -> Any:
            if name.startswith("hk_"):
                self._limiter.acquire_endpoint(
                    name,
                    calls=max(1, int(os.environ.get("LEAN_TUSHARE_HK_CALLS_PER_HOUR", "1"))),
                    period_seconds=3600,
                    wait=False,
                )
            self._limiter.acquire()
            with self._count_lock:
                self._call_counts[name] += 1
            return value(*args, **kwargs)

        return limited

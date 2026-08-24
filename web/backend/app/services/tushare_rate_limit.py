from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timedelta, timezone
import os
import threading
import time
import uuid
from typing import Any, Callable

from ..db import database_backend, db


DEFAULT_CALLS_PER_MINUTE = max(1, int(os.environ.get("LEAN_TUSHARE_CALLS_PER_MINUTE", "500")))


class TushareRateLimiter:
    """A token-wide rolling-window limiter shared by every TuShare caller.

    PostgreSQL provides cross-process coordination. The in-process deque is
    retained only for the explicit SQLite unit-test backend.
    """

    def __init__(self, *, calls_per_minute: int = DEFAULT_CALLS_PER_MINUTE) -> None:
        self.calls_per_minute = max(1, calls_per_minute)
        self._local: deque[float] = deque()
        self._endpoint_local: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
    def _database_window(
        self,
        bucket: str,
        *,
        window_ms: int,
        limit: int,
        consume: bool,
    ) -> tuple[int, int] | None:
        if database_backend() != "postgresql":
            return None
        now_ms = int(time.time() * 1000)
        with db() as connection:
            connection.execute(
                "select pg_advisory_xact_lock(hashtext(?))",
                (f"lean:tushare:rate:{bucket}",),
            )
            connection.execute(
                "delete from provider_rate_limit_events where bucket_key=? and occurred_at_ms<=?",
                (bucket, now_ms - window_ms),
            )
            row = connection.execute(
                "select count(*) as count,min(occurred_at_ms) as oldest from provider_rate_limit_events where bucket_key=?",
                (bucket,),
            ).fetchone()
            count = int(row["count"] or 0)
            oldest = int(row["oldest"] or now_ms)
            admitted = False
            if consume and count < limit:
                connection.execute(
                    "insert into provider_rate_limit_events(bucket_key,event_id,occurred_at_ms) values (?,?,?)",
                    (bucket, uuid.uuid4().hex, now_ms),
                )
                count += 1
                admitted = True
            wait_ms = (
                0
                if admitted
                else max(1, oldest + window_ms - now_ms) if count >= limit else 0
            )
        return count, wait_ms

    def _database_wait(self) -> float | None:
        result = self._database_window(
            "global", window_ms=60_000, limit=self.calls_per_minute, consume=True
        )
        if result is None:
            return None
        count, wait_ms = result
        return max(0.001, wait_ms / 1000.0) if count >= self.calls_per_minute and wait_ms else 0.0

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
            wait = self._database_wait()
            if wait is None:
                wait = self._local_wait()
            if wait <= 0:
                return
            time.sleep(min(wait, 1.0))

    def status(self) -> dict[str, Any]:
        """Expose the shared rolling-window state without consuming a call."""
        now_ms = int(time.time() * 1000)
        count = 0
        wait_ms = 0
        shared = self._database_window(
            "global", window_ms=60_000, limit=self.calls_per_minute, consume=False
        )
        if shared is not None:
            count, wait_ms = shared
        else:
            now = time.monotonic()
            with self._lock:
                while self._local and self._local[0] <= now - 60.0:
                    self._local.popleft()
                count = len(self._local)
                if count >= self.calls_per_minute and self._local:
                    wait_ms = max(1, int((self._local[0] + 60.0 - now) * 1000))
        waiting = count >= self.calls_per_minute and wait_ms > 0
        return {
            "apiCallsInWindow": count,
            "apiQuotaWaiting": waiting,
            "apiQuotaRetryAfterSeconds": round(wait_ms / 1000.0, 1) if waiting else 0.0,
            "apiQuotaNextAllowedAt": (
                datetime.fromtimestamp((now_ms + wait_ms) / 1000.0, timezone.utc).isoformat()
                if waiting
                else None
            ),
        }

    def acquire_endpoint(self, endpoint: str, *, calls: int, period_seconds: int, wait: bool) -> None:
        key = f"endpoint:{endpoint}"
        while True:
            shared = self._database_window(
                key,
                window_ms=period_seconds * 1000,
                limit=calls,
                consume=True,
            )
            wait_seconds = (
                None
                if shared is None
                else (max(0.001, shared[1] / 1000.0) if shared[0] >= calls and shared[1] else 0.0)
            )
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


def global_tushare_quota_status() -> dict[str, Any]:
    return global_tushare_limiter().status()


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

    def quota_status(self) -> dict[str, Any]:
        return self._limiter.status()

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

from collections import defaultdict, deque
import math
import threading
import time
from typing import Optional

from app.core.config import get_settings


class LoginRateLimiter:
    """In-memory sliding-window + lockout rate limiter for login brute-force / AD lockout protection."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[tuple[str, ...], deque[float]] = defaultdict(deque)
        self._locked_until: dict[tuple[str, ...], float] = {}

    def _prune(self, key: tuple[str, ...], now: float, window_seconds: int) -> deque[float]:
        dq = self._failures[key]
        cutoff = now - window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()
        return dq

    def check_allowed(self, ip: str, username: str) -> Optional[int]:
        """Return retry-after seconds if blocked, or None if attempt is allowed."""
        now = time.monotonic()
        user_key = ("user", ip, username)
        ip_key = ("ip", ip)

        with self._lock:
            for key in (user_key, ip_key):
                until = self._locked_until.get(key)
                if until is not None:
                    if until > now:
                        return max(1, math.ceil(until - now))
                    del self._locked_until[key]
                    self._failures.pop(key, None)
        return None

    def record_failure(self, ip: str, username: str) -> None:
        settings = get_settings()
        max_attempts = max(1, settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS)
        window = max(1, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        lockout = max(1, settings.LOGIN_RATE_LIMIT_LOCKOUT_SECONDS)

        now = time.monotonic()
        user_key = ("user", ip, username)
        ip_key = ("ip", ip)

        with self._lock:
            user_dq = self._prune(user_key, now, window)
            user_dq.append(now)
            if len(user_dq) >= max_attempts:
                self._locked_until[user_key] = now + lockout

            ip_dq = self._prune(ip_key, now, window)
            ip_dq.append(now)
            if len(ip_dq) >= max_attempts * 4:
                self._locked_until[ip_key] = now + lockout

    def record_success(self, ip: str, username: str) -> None:
        user_key = ("user", ip, username)
        with self._lock:
            self._failures.pop(user_key, None)
            self._locked_until.pop(user_key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()


login_rate_limiter = LoginRateLimiter()


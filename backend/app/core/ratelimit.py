import threading
import time

class LoginLimiter:
    """Limita tentativas de login com falha por IP + e-mail (memória do processo da API)."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 900):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        items = [t for t in self._failures.get(key, []) if now - t < self.window]
        if items:
            self._failures[key] = items
        else:
            self._failures.pop(key, None)
        return items

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            items = self._recent(key, now)
            if len(items) < self.max_failures:
                return 0
            return max(1, int(self.window - (now - items[0])))

    def fail(self, key: str) -> None:
        with self._lock:
            self._failures.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

login_limiter = LoginLimiter()

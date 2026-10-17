"""Limite de débit des appels d'outils.

Chaque utilisateur consulte PISTE avec ses propres identifiants, donc sur son
propre quota : le serveur ne protège plus que lui-même, par une limite de
débit par adresse IP. Un dépassement lève ``QuotaExceeded``, qui porte un
message explicite et le délai d'attente en secondes (``retry_after``). Un
appel refusé ne consomme rien.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from mcp_server.runtime import RuntimeCapacityError

class QuotaExceeded(RuntimeCapacityError):
    """Quota atteint : message destiné à l'utilisateur et délai d'attente."""

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


def format_delay(seconds: int) -> str:
    """Durée lisible : « 42 s », « 3 min 05 s », « 2 h 07 min »."""
    seconds = max(1, int(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {rest:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


class SlidingWindow:
    """Fenêtre glissante en mémoire, par clé, avec délai d'attente exact.

    Les clés inactives sont purgées à chaque passage, ce qui borne la mémoire
    sans tâche de fond, même face à une rafale d'adresses IP distinctes.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit <= 0:
            raise ValueError("La limite doit être strictement positive.")
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def wait_time(self, key: str) -> float:
        """Secondes avant qu'un appel soit permis ; 0 si permis, sans l'enregistrer."""
        now = self._clock()
        with self._lock:
            bucket = self._prune(key, now)
            if len(bucket) < self._limit:
                return 0.0
            return bucket[0] + self._window - now

    def hit(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            self._prune(key, now).append(now)

    def _prune(self, key: str, now: float) -> deque[float]:
        horizon = now - self._window
        for stale in [k for k, v in self._buckets.items() if not v or v[-1] <= horizon]:
            del self._buckets[stale]
        bucket = self._buckets.setdefault(key, deque())
        while bucket and bucket[0] <= horizon:
            bucket.popleft()
        return bucket

    @property
    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._buckets)


class IpRateLimit:
    """Appels d'outils par minute et par adresse IP."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._window = SlidingWindow(per_minute, 60.0, clock)
        self._lock = threading.Lock()

    def check(self, client_ip: str) -> None:
        key = f"ip:{client_ip}"
        with self._lock:
            wait = self._window.wait_time(key)
            if wait > 0:
                raise QuotaExceeded(
                    "Trop d'appels depuis cette adresse ; "
                    f"réessayez dans {format_delay(int(wait) + 1)}.",
                    int(wait) + 1,
                )
            self._window.hit(key)

"""Quotas d'appels d'outils des deux modes d'accès.

* Mode « serveur partagé » : les appels consomment le quota PISTE du titulaire.
  Chaque utilisateur est limité par minute (en mémoire) et par jour (SQLite),
  et l'ensemble des utilisateurs par une limite journalière globale.
* Mode « clés personnelles » : les appels consomment le quota PISTE de
  l'utilisateur ; seule une limite de débit par adresse IP s'applique, contre
  les abus de l'instance elle-même.

Un dépassement lève ``QuotaExceeded``, qui porte un message explicite et le
délai d'attente en secondes (``retry_after``). Un appel refusé ne consomme
aucun compteur.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from collections import deque
from typing import Callable

from mcp_server.runtime import RuntimeCapacityError
from mcp_server.store import Store

GLOBAL_SCOPE = "global"


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


def _seconds_until_utc_midnight(now: dt.datetime) -> int:
    tomorrow = (now + dt.timedelta(days=1)).date()
    midnight = dt.datetime.combine(tomorrow, dt.time(0), tzinfo=dt.timezone.utc)
    return int((midnight - now).total_seconds()) + 1


class QuotaPolicy:
    """Applique les quotas des deux modes."""

    def __init__(
        self,
        store: Store,
        *,
        user_per_minute: int,
        user_per_day: int,
        global_per_day: int,
        keys_per_minute_per_ip: int,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
    ) -> None:
        self._store = store
        self._user_per_day = user_per_day
        self._global_per_day = global_per_day
        self._user_minute = SlidingWindow(user_per_minute, clock=clock)
        self._ip_minute = SlidingWindow(keys_per_minute_per_ip, clock=clock)
        self._now = now
        self._last_day: str | None = None
        self._day_lock = threading.Lock()
        #: Rend atomique « vérifier la minute, consommer le jour, compter la
        #: minute » : deux appels simultanés ne peuvent pas franchir ensemble
        #: le dernier créneau disponible.
        self._shared_lock = threading.Lock()
        self._ip_lock = threading.Lock()

    def _today(self) -> tuple[str, dt.datetime]:
        now = self._now()
        day = now.date().isoformat()
        with self._day_lock:
            if day != self._last_day:
                self._store.purge_counters_before(day)
                self._last_day = day
        return day, now

    def check_shared(self, subject: str) -> None:
        """Mode partagé : minute et jour par utilisateur, puis jour global."""
        key = f"user:{subject}"
        with self._shared_lock:
            self._check_shared_locked(key)

    def _check_shared_locked(self, key: str) -> None:
        wait = self._user_minute.wait_time(key)
        if wait > 0:
            raise QuotaExceeded(
                "Quota par minute atteint pour votre compte ; "
                f"réessayez dans {format_delay(int(wait) + 1)}.",
                int(wait) + 1,
            )
        day, now = self._today()
        saturated = self._store.consume(
            day, ((key, self._user_per_day), (GLOBAL_SCOPE, self._global_per_day))
        )
        if saturated is not None:
            retry = _seconds_until_utc_midnight(now)
            if saturated == GLOBAL_SCOPE:
                message = (
                    "Le serveur partagé a atteint sa limite d'appels pour aujourd'hui. "
                    f"Réessayez dans {format_delay(retry)} (00:00 UTC), "
                    "ou utilisez vos propres clés PISTE."
                )
            else:
                message = (
                    f"Quota journalier atteint pour votre compte ({self._user_per_day} "
                    f"appels). Réessayez dans {format_delay(retry)} (00:00 UTC), "
                    "ou utilisez vos propres clés PISTE."
                )
            raise QuotaExceeded(message, retry)
        self._user_minute.hit(key)

    def usage_today(self, subject: str) -> tuple[int, int]:
        """Appels consommés aujourd'hui par un sujet, et son plafond journalier."""
        day, _ = self._today()
        return self._store.count(f"user:{subject}", day), self._user_per_day

    def check_personal_keys(self, client_ip: str) -> None:
        """Mode clés personnelles : seul le débit par adresse IP est limité."""
        key = f"ip:{client_ip}"
        with self._ip_lock:
            wait = self._ip_minute.wait_time(key)
            if wait > 0:
                raise QuotaExceeded(
                    "Trop d'appels depuis cette adresse ; "
                    f"réessayez dans {format_delay(int(wait) + 1)}.",
                    int(wait) + 1,
                )
            self._ip_minute.hit(key)

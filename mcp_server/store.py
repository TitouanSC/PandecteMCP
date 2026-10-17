"""Cache SQLite des réponses publiques des API juridiques.

Base en mémoire vive (``:memory:``) sur le serveur hébergé : rien n'est
écrit sur disque, tout disparaît au redémarrage. Seules y figurent des
réponses publiques (articles, textes, décisions), indexées par une empreinte
de la demande — jamais par utilisateur. Aucun identifiant PISTE n'est jamais
écrit ici. Le module ne dépend que de la bibliothèque standard.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS response_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    stored_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS response_cache_stored ON response_cache (stored_at);
"""


class Store:
    """Accès sérialisé à la base : un verrou, une connexion, des transactions courtes."""

    def __init__(self, path: str | Path) -> None:
        target = str(path)
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(
            target, check_same_thread=False, isolation_level=None, timeout=5
        )
        with self._lock:
            if target != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- Cache des réponses --------------------------------------------------

    def cache_get(self, key: str, now: int) -> tuple[str, int] | None:
        """Valeur encore valide et sa date d'enregistrement, ou ``None``."""
        with self._lock:
            row = self._db.execute(
                "SELECT value, stored_at FROM response_cache WHERE key = ? AND expires_at > ?",
                (key, now),
            ).fetchone()
        return (row[0], row[1]) if row else None

    def cache_put(self, key: str, value: str, stored_at: int, expires_at: int) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO response_cache (key, value, stored_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (key, value, stored_at, expires_at),
            )

    def cache_delete(self, key: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM response_cache WHERE key = ?", (key,))

    def cache_trim(self, now: int, max_bytes: int) -> None:
        """Retire les entrées expirées, puis les plus anciennes au-delà du plafond."""
        with self._lock:
            self._db.execute("DELETE FROM response_cache WHERE expires_at <= ?", (now,))
            total = self._db.execute(
                "SELECT COALESCE(SUM(LENGTH(value)), 0) FROM response_cache"
            ).fetchone()[0]
            if total <= max_bytes:
                return
            excess = total - max_bytes
            rows = self._db.execute(
                "SELECT key, LENGTH(value) FROM response_cache ORDER BY stored_at"
            ).fetchall()
            doomed = []
            for key, size in rows:
                if excess <= 0:
                    break
                doomed.append((key,))
                excess -= size
            self._db.executemany("DELETE FROM response_cache WHERE key = ?", doomed)

    def cache_size(self) -> tuple[int, int]:
        """Nombre d'entrées et taille totale des valeurs, en octets."""
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(value)), 0) FROM response_cache"
            ).fetchone()
        return row[0], row[1]

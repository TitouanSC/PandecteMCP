"""Stockage persistant du serveur : jetons personnels et compteurs journaliers.

Une base SQLite sur le disque persistant de l'hébergeur suffit : une seule
instance écrit, et chaque opération tient en quelques microsecondes. Le module
ne dépend que de la bibliothèque standard.

Ce qui est stocké, et rien d'autre :

* ``personal_tokens`` : l'empreinte HMAC d'un jeton personnel (jamais le jeton
  lui-même) et le sujet WorkOS auquel il appartient ;
* ``daily_counters`` : le nombre d'appels d'outils par portée et par jour UTC.

Aucun identifiant PISTE n'est jamais écrit ici.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS personal_tokens (
    token_hash TEXT PRIMARY KEY,
    subject TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_counters (
    scope TEXT NOT NULL,
    day TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (scope, day)
);
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

    # -- Jetons personnels -------------------------------------------------

    def replace_token(self, subject: str, token_hash: str) -> None:
        """Enregistre le jeton d'un sujet ; l'éventuel jeton précédent est révoqué."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute("DELETE FROM personal_tokens WHERE subject = ?", (subject,))
                self._db.execute(
                    "INSERT INTO personal_tokens (token_hash, subject, created_at) VALUES (?, ?, ?)",
                    (token_hash, subject, int(time.time())),
                )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def subject_for(self, token_hash: str) -> str | None:
        with self._lock:
            row = self._db.execute(
                "SELECT subject FROM personal_tokens WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        return row[0] if row else None

    def has_token(self, subject: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM personal_tokens WHERE subject = ?", (subject,)
            ).fetchone()
        return row is not None

    def revoke(self, subject: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM personal_tokens WHERE subject = ?", (subject,))

    # -- Compteurs journaliers ---------------------------------------------

    def consume(self, day: str, limits: Iterable[tuple[str, int]]) -> str | None:
        """Incrémente atomiquement chaque compteur, ou aucun.

        Rend ``None`` si tous les plafonds le permettent, sinon la portée du
        premier compteur saturé — sans rien avoir incrémenté : un appel refusé
        ne consomme le quota de personne.
        """
        limits = list(limits)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for scope, limit in limits:
                    row = self._db.execute(
                        "SELECT count FROM daily_counters WHERE scope = ? AND day = ?",
                        (scope, day),
                    ).fetchone()
                    if (row[0] if row else 0) >= limit:
                        self._db.execute("ROLLBACK")
                        return scope
                for scope, _ in limits:
                    self._db.execute(
                        "INSERT INTO daily_counters (scope, day, count) VALUES (?, ?, 1) "
                        "ON CONFLICT (scope, day) DO UPDATE SET count = count + 1",
                        (scope, day),
                    )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return None

    def count(self, scope: str, day: str) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT count FROM daily_counters WHERE scope = ? AND day = ?",
                (scope, day),
            ).fetchone()
        return row[0] if row else 0

    def purge_counters_before(self, day: str) -> None:
        """Les compteurs passés n'ont plus d'usage : ils ne sont pas conservés."""
        with self._lock:
            self._db.execute("DELETE FROM daily_counters WHERE day < ?", (day,))

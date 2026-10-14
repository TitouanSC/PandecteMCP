"""Cache des réponses publiques des API juridiques.

Ménage le quota PISTE du titulaire sans tromper l'utilisateur :

* seules les **lectures** sont mises en cache — articles, sections et textes
  (6 h par défaut), décisions Judilibre (24 h par défaut) ; jamais les
  recherches, dont les résultats bougent avec le fonds ;
* la clé comprend la **date du jour du serveur** : une réponse datée « en
  vigueur aujourd'hui » n'est jamais resservie le lendemain ;
* une réponse resservie porte ``metadata.from_cache = true`` et la date de sa
  récupération réelle (``metadata.retrieved_at``), jamais l'heure de relecture ;
* la liste de retrait d'urgence Judilibre est vérifiée **à chaque lecture** :
  une décision retirée n'est plus servie, même déjà en cache ;
* seules les réponses complètes sont enregistrées : une erreur n'est jamais
  mise en cache ;
* aucune donnée utilisateur : la clé n'est faite que des paramètres publics de
  la demande, la valeur que de la réponse publique.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from mcp_server.store import Store

LOGGER = logging.getLogger("pandecte.mcp")

#: Outils de lecture et nature de ce qu'ils rendent.
TEXT_OPERATIONS = frozenset({"get_article", "get_section", "get_text"})
DECISION_OPERATIONS = frozenset({"get_decision"})
#: Fréquence du ménage (expiration, plafond de taille), en écritures.
TRIM_EVERY = 50


@dataclass(frozen=True)
class CachePlan:
    key: str
    kind: str  # « text » ou « decision »
    ttl: int
    requested_id: str


def _kind(operation: str, args: tuple[Any, ...]) -> str | None:
    if operation in TEXT_OPERATIONS:
        return "text"
    if operation in DECISION_OPERATIONS:
        return "decision"
    if operation == "fetch" and args:
        identifier = str(args[0]).strip().upper()
        # Même aiguillage que pandecte.tools.fetch.
        if identifier.startswith(("LEGIARTI", "LEGITEXT", "LEGISCTA", "JORF")):
            return "text"
        return "decision"
    return None


def _iso(timestamp: int) -> str:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat()


class ResponseCache:
    def __init__(
        self,
        store: Store,
        *,
        text_ttl: int,
        decision_ttl: int,
        max_bytes: int,
        suppressed: Callable[[], frozenset[str]],
        clock: Callable[[], float] = time.time,
        today: Callable[[], dt.date] = dt.date.today,
    ) -> None:
        self._store = store
        self._ttl = {"text": text_ttl, "decision": decision_ttl}
        self._max_bytes = max_bytes
        self._suppressed = suppressed
        self._clock = clock
        self._today = today
        self._writes = 0
        self._writes_lock = threading.Lock()

    def plan(
        self, operation: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> CachePlan | None:
        kind = _kind(operation, args)
        if kind is None or self._ttl[kind] <= 0:
            return None
        material = json.dumps(
            [operation, list(args), sorted(kwargs.items()), self._today().isoformat()],
            default=str,
            ensure_ascii=True,
        )
        key = hashlib.sha256(material.encode("ascii")).hexdigest()
        requested = str(args[0]).strip() if args else ""
        return CachePlan(key, kind, self._ttl[kind], requested)

    def _withdrawn(self, plan: CachePlan, result: dict[str, Any]) -> bool:
        if plan.kind != "decision":
            return False
        suppressed = self._suppressed()
        if not suppressed:
            return False
        ids = (plan.requested_id, str(result.get("id") or ""))
        return any(value.strip().lower() in suppressed for value in ids if value)

    def get(self, plan: CachePlan) -> dict[str, Any] | None:
        found = self._store.cache_get(plan.key, int(self._clock()))
        if found is None:
            return None
        value, stored_at = found
        try:
            result = json.loads(value)
        except ValueError:
            self._store.cache_delete(plan.key)
            return None
        if not isinstance(result, dict) or self._withdrawn(plan, result):
            # Décision retirée depuis : l'entrée disparaît, et l'appel réel
            # rendra l'erreur prévue par l'outil.
            self._store.cache_delete(plan.key)
            return None
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            metadata.setdefault("retrieved_at", _iso(stored_at))
            metadata["from_cache"] = True
        return result

    def put(self, plan: CachePlan, result: dict[str, Any]) -> None:
        if not isinstance(result, dict) or not result.get("id"):
            return
        try:
            value = json.dumps(result, ensure_ascii=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return
        if len(value) > self._max_bytes // 10:
            return  # une seule réponse ne doit pas évincer tout le cache
        now = int(self._clock())
        self._store.cache_put(plan.key, value, now, now + plan.ttl)
        with self._writes_lock:
            self._writes += 1
            trim = self._writes % TRIM_EVERY == 0
        if trim:
            self._store.cache_trim(now, self._max_bytes)

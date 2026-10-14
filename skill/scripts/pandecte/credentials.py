"""Identifiants PISTE de l'appel en cours.

Deux origines possibles :

* **la requête** — mode « clés personnelles » du serveur MCP : l'utilisateur
  transmet ses propres identifiants, qui ne servent que le temps de l'appel.
  Ils vivent dans une ``ContextVar`` : jamais dans ``os.environ``, jamais sur
  disque, jamais partagés avec un appel concurrent ;
* **l'environnement** — CLI, transport stdio et mode « serveur partagé » :
  ``LEGIFRANCE_CLIENT_ID``, ``LEGIFRANCE_CLIENT_SECRET`` et, facultatif,
  ``JUDILIBRE_KEY_ID`` (ou ``PISTE_KEY_ID``).

Des identifiants posés pour la requête l'emportent toujours et ne retombent
jamais sur ceux de l'environnement, même incomplets : un appel en mode
« clés personnelles » ne doit pas consommer le quota du titulaire du serveur.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import urllib.parse
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

#: Clé HMAC tirée au démarrage du processus. L'empreinte ne sert qu'à indexer
#: le cache de jetons en mémoire : elle n'a pas à survivre au processus, et une
#: clé aléatoire évite qu'une empreinte observée permette de tester des secrets.
_FINGERPRINT_KEY = secrets.token_bytes(32)

#: En deçà, une valeur est trop courte pour être masquée sans abîmer le texte
#: (un identifiant PISTE réel est bien plus long).
_MIN_MASKED_LENGTH = 4

MASK = "[secret masqué]"


@dataclass(frozen=True, repr=False)
class PisteCredentials:
    """Identifiants PISTE, sans représentation textuelle révélatrice."""

    client_id: str
    client_secret: str
    key_id: str | None = None

    def __repr__(self) -> str:
        return "PisteCredentials(<masqué>)"

    __str__ = __repr__

    @property
    def fingerprint(self) -> str:
        """Empreinte stable dans le processus, couvrant identifiant ET secret."""
        material = f"{self.client_id}\0{self.client_secret}".encode("utf-8")
        return hmac.new(_FINGERPRINT_KEY, material, hashlib.sha256).hexdigest()

    def secret_values(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (self.client_id, self.client_secret, self.key_id)
            if value
        )


_REQUEST_CREDENTIALS: ContextVar[PisteCredentials | None] = ContextVar(
    "pandecte_request_credentials", default=None
)


@contextmanager
def use_credentials(credentials: PisteCredentials) -> Iterator[None]:
    """Pose les identifiants de la requête pour la durée du bloc."""
    reset = _REQUEST_CREDENTIALS.set(credentials)
    try:
        yield
    finally:
        _REQUEST_CREDENTIALS.reset(reset)


def request_credentials() -> PisteCredentials | None:
    """Identifiants posés pour la requête courante, ou ``None``."""
    return _REQUEST_CREDENTIALS.get()


def environment_credentials() -> PisteCredentials | None:
    """Identifiants du titulaire, lus dans l'environnement."""
    client_id = os.environ.get("LEGIFRANCE_CLIENT_ID")
    client_secret = os.environ.get("LEGIFRANCE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    key_id = os.environ.get("JUDILIBRE_KEY_ID") or os.environ.get("PISTE_KEY_ID")
    return PisteCredentials(client_id, client_secret, key_id or None)


def judilibre_key_id() -> str | None:
    """KeyId Judilibre applicable, sans jamais mélanger les deux origines."""
    credentials = request_credentials()
    if credentials is not None:
        return credentials.key_id
    return os.environ.get("JUDILIBRE_KEY_ID") or os.environ.get("PISTE_KEY_ID") or None


def active_credentials() -> PisteCredentials | None:
    """Identifiants à utiliser : ceux de la requête, sinon l'environnement."""
    credentials = request_credentials()
    if credentials is not None:
        return credentials
    return environment_credentials()


#: Variables d'environnement dont la valeur ne doit jamais apparaître.
SECRET_VARIABLES = (
    "LEGIFRANCE_CLIENT_ID",
    "LEGIFRANCE_CLIENT_SECRET",
    "JUDILIBRE_KEY_ID",
    "PISTE_KEY_ID",
)


def _known_secrets() -> list[str]:
    values = [os.environ.get(name) for name in SECRET_VARIABLES]
    credentials = request_credentials()
    if credentials is not None:
        values.extend(credentials.secret_values())
    return [value for value in values if value and len(value) >= _MIN_MASKED_LENGTH]


def mask_secrets(text: str) -> str:
    """Masque tout identifiant connu, brut ou encodé dans une URL ou un formulaire."""
    secrets_found = _known_secrets()
    variants: set[str] = set()
    for value in secrets_found:
        variants.update(
            {value, urllib.parse.quote(value, safe=""), urllib.parse.quote_plus(value)}
        )
    # Les plus longues d'abord : un secret qui en contient un autre reste masqué
    # en entier.
    for variant in sorted(variants, key=len, reverse=True):
        text = text.replace(variant, MASK)
    return text

"""Enveloppes chiffrées : tout l'état OAuth voyage chez le client, jamais ici.

Le serveur ne stocke ni client enregistré, ni code, ni jeton, ni identifiant
PISTE. Chaque élément est une enveloppe AES-256-GCM que seul le serveur sait
ouvrir ; le client (claude.ai, ChatGPT…) la conserve et la renvoie telle
quelle. Propriétés :

* **confidentialité** — le contenu (identifiants PISTE compris) est illisible
  pour le client qui transporte l'enveloppe ;
* **intégrité** — toute modification fait échouer l'ouverture (GCM) ;
* **cloisonnement** — chaque enveloppe porte son usage en données associées
  (AAD) : un code ne s'ouvre pas comme jeton d'accès, ni l'inverse ;
* **expiration** — ``exp`` est contrôlé à l'ouverture ;
* **rotation** — une clé précédente reste acceptée en lecture le temps de la
  transition ; la nouvelle clé seule sert à sceller.

Format : ``pse1.`` + base64url(identifiant de clé (4 o) ‖ nonce (12 o) ‖
chiffré). L'identifiant de clé est un préfixe d'empreinte, pas la clé.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any, Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "pse1."
KEY_BYTES = 32
NONCE_BYTES = 12
KEY_ID_BYTES = 4
#: Plafond d'une enveloppe reçue : bien au-delà du plus gros contenu légitime
#: (métadonnées de client), assez bas pour ne rien décoder d'aberrant.
MAX_SEALED_CHARS = 8192

#: Usages admis. Toute enveloppe est liée à exactement l'un d'eux.
PURPOSES = frozenset({"client", "authreq", "code", "access", "refresh"})


class SealError(Exception):
    """Enveloppe illisible, altérée, d'un autre usage ou expirée.

    Le message reste générique : il ne dit jamais laquelle de ces raisons
    s'applique, pour ne rien apprendre à qui sonde le serveur.
    """


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def parse_key(text: str) -> bytes:
    """Clé de scellement depuis sa forme base64url (43 caractères)."""
    try:
        raw = _b64decode(text.strip())
    except (ValueError, TypeError) as exc:
        raise ValueError("Clé de scellement illisible (base64url attendu).") from exc
    if len(raw) != KEY_BYTES:
        raise ValueError(f"Clé de scellement : {KEY_BYTES} octets attendus.")
    return raw


def new_key_text() -> str:
    """Nouvelle clé aléatoire, au format attendu par PANDECTE_SEAL_KEY."""
    return _b64encode(os.urandom(KEY_BYTES))


def _key_id(key: bytes) -> bytes:
    return hashlib.sha256(b"pandecte-seal-key-id" + key).digest()[:KEY_ID_BYTES]


class Sealer:
    def __init__(
        self,
        key: bytes,
        previous_keys: tuple[bytes, ...] = (),
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        keys = (key, *previous_keys)
        if any(len(item) != KEY_BYTES for item in keys):
            raise ValueError(f"Clé de scellement : {KEY_BYTES} octets attendus.")
        self._current = (_key_id(key), AESGCM(key))
        self._readers = {_key_id(item): AESGCM(item) for item in keys}
        self._clock = clock

    def seal(self, purpose: str, claims: dict[str, Any], ttl_seconds: int) -> str:
        if purpose not in PURPOSES:
            raise ValueError(f"Usage d'enveloppe inconnu : {purpose}")
        body = dict(claims)
        body["exp"] = int(self._clock()) + int(ttl_seconds)
        plaintext = json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode()
        key_id, aead = self._current
        nonce = os.urandom(NONCE_BYTES)
        sealed = aead.encrypt(nonce, plaintext, self._aad(purpose))
        return PREFIX + _b64encode(key_id + nonce + sealed)

    def open(self, purpose: str, text: str) -> dict[str, Any]:
        """Contenu de l'enveloppe, ou ``SealError`` sans autre précision."""
        if purpose not in PURPOSES:
            raise ValueError(f"Usage d'enveloppe inconnu : {purpose}")
        if (
            not isinstance(text, str)
            or not text.startswith(PREFIX)
            or len(text) > MAX_SEALED_CHARS
        ):
            raise SealError("Enveloppe invalide.")
        try:
            raw = _b64decode(text[len(PREFIX):])
        except (ValueError, TypeError) as exc:
            raise SealError("Enveloppe invalide.") from exc
        if len(raw) <= KEY_ID_BYTES + NONCE_BYTES:
            raise SealError("Enveloppe invalide.")
        key_id = raw[:KEY_ID_BYTES]
        nonce = raw[KEY_ID_BYTES:KEY_ID_BYTES + NONCE_BYTES]
        aead = self._readers.get(key_id)
        if aead is None:
            raise SealError("Enveloppe invalide.")
        try:
            plaintext = aead.decrypt(
                nonce, raw[KEY_ID_BYTES + NONCE_BYTES:], self._aad(purpose)
            )
            claims = json.loads(plaintext)
        except (InvalidTag, ValueError) as exc:
            raise SealError("Enveloppe invalide.") from exc
        if not isinstance(claims, dict):
            raise SealError("Enveloppe invalide.")
        exp = claims.get("exp")
        if not isinstance(exp, int) or exp <= int(self._clock()):
            raise SealError("Enveloppe invalide.")
        return claims

    @staticmethod
    def _aad(purpose: str) -> bytes:
        return f"pandecte/{PREFIX}{purpose}".encode("ascii")

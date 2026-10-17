"""Accès validé d'une requête et clé personnelle ``pk1``.

Toute requête authentifiée porte les identifiants PISTE **de l'utilisateur** :

* jeton scellé émis après la page « Connexion PISTE »
  (``mcp_server.piste_oauth``) — claude.ai, ChatGPT, tout client OAuth ;
* ``pk1.<id>.<secret>[.<keyid>]`` en en-tête ``Authorization: Bearer`` —
  clients qui acceptent un en-tête fixe (Claude Code, Cursor…). Les
  identifiants y sont encodés en base64url sans remplissage ; la chaîne est
  assemblée dans le navigateur de l'utilisateur (page « Clé personnelle »).

Dans les deux cas, les identifiants ne servent que le temps de la requête :
jamais stockés, jamais journalisés, jamais renvoyés. Le champ ``token`` de
l'objet rendu au SDK porte une étiquette, pour qu'aucune représentation de
l'objet ne puisse exposer une clé.
"""

from __future__ import annotations

import base64
import re
from typing import Literal

from mcp.server.auth.provider import AccessToken
from pydantic import ConfigDict, Field

from pandecte.credentials import PisteCredentials

PERSONAL_KEY_PREFIX = "pk1."

#: Segment base64url d'une clé personnelle, sans remplissage.
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]{1,700}$")
#: Valeur décodée : ASCII visible, sans espace ni caractère de contrôle.
_CREDENTIAL_VALUE_RE = re.compile(r"^[\x21-\x7e]{4,256}$")
MAX_BEARER_LENGTH = 4096

Mode = Literal["keys"]


class AccessGrant(AccessToken):
    """Accès validé : sujet pseudonyme et identifiants PISTE de l'utilisateur."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    mode: Mode = "keys"
    credentials: PisteCredentials | None = Field(default=None, exclude=True, repr=False)


def _b64encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("ascii")).decode("ascii").rstrip("=")


def encode_personal_key(credentials: PisteCredentials) -> str:
    """Forme canonique ``pk1.…`` ; la page web applique le même algorithme."""
    parts = [credentials.client_id, credentials.client_secret]
    if credentials.key_id:
        parts.append(credentials.key_id)
    return PERSONAL_KEY_PREFIX + ".".join(_b64encode(part) for part in parts)


def parse_personal_key(raw: str) -> PisteCredentials | None:
    """Décode une clé personnelle, ou ``None`` si elle n'est pas strictement valide.

    Refuse toute forme non canonique (remplissage, caractères hors alphabet,
    valeurs hors ASCII visible) : une seule écriture possible par jeu
    d'identifiants.
    """
    if len(raw) > MAX_BEARER_LENGTH or not raw.startswith(PERSONAL_KEY_PREFIX):
        return None
    segments = raw[len(PERSONAL_KEY_PREFIX):].split(".")
    if len(segments) not in (2, 3):
        return None
    values: list[str] = []
    for segment in segments:
        if not _B64URL_RE.match(segment):
            return None
        try:
            value = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)).decode("ascii")
        except (ValueError, UnicodeDecodeError):
            return None
        if not _CREDENTIAL_VALUE_RE.match(value) or _b64encode(value) != segment:
            return None
        values.append(value)
    return PisteCredentials(values[0], values[1], values[2] if len(values) == 3 else None)

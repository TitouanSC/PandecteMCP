"""Reconnaissance des moyens d'accès et choix du mode.

Le serveur accepte trois formes de jeton porteur (``Authorization: Bearer …``) :

``pk1.<id>.<secret>[.<keyid>]`` — **mode « clés personnelles »**
    Les identifiants PISTE de l'utilisateur, encodés en base64url sans
    remplissage. Ils ne servent que le temps de la requête : jamais stockés,
    jamais journalisés, jamais renvoyés. La chaîne est assemblée dans le
    navigateur de l'utilisateur (page « Clé personnelle »), pas par le serveur.

``pdt_<43 caractères>`` — **mode « serveur partagé »**, jeton personnel
    Délivré sur la page « Mon compte » après connexion WorkOS, pour les
    clients qui acceptent un jeton fixe (Claude Code, Cursor, Le Chat…).
    Seule son empreinte HMAC-SHA256, avec un poivre secret, est stockée.

Jeton d'accès OAuth (JWT) émis par WorkOS AuthKit — **mode « serveur partagé »**
    Pour claude.ai, ChatGPT et tout client OAuth. Vérifié localement contre le
    JWKS de l'émetteur (``mcp_server.auth.JwksTokenVerifier``).

Le jeton brut n'est jamais conservé dans l'objet rendu au SDK : son champ
``token`` porte une étiquette, pour qu'aucune représentation de l'objet ne
puisse exposer une clé PISTE ou un jeton personnel.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
from typing import Iterable, Literal

import anyio
from mcp.server.auth.provider import AccessToken
from pydantic import ConfigDict, Field

from pandecte.credentials import PisteCredentials

from mcp_server.store import Store

LOGGER = logging.getLogger("pandecte.mcp.auth")

PERSONAL_KEY_PREFIX = "pk1."
PERSONAL_TOKEN_PREFIX = "pdt_"

#: Jeton personnel : préfixe puis 32 octets aléatoires en base64url.
PERSONAL_TOKEN_RE = re.compile(r"^pdt_[A-Za-z0-9_-]{43}$")
#: Segment base64url d'une clé personnelle, sans remplissage.
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]{1,700}$")
#: Valeur décodée : ASCII visible, sans espace ni caractère de contrôle.
_CREDENTIAL_VALUE_RE = re.compile(r"^[\x21-\x7e]{4,256}$")
MAX_BEARER_LENGTH = 4096

Mode = Literal["shared", "keys"]


class AccessGrant(AccessToken):
    """Accès validé : mode, sujet de quota et, en mode clés, identifiants."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    mode: Mode
    credentials: PisteCredentials | None = Field(default=None, exclude=True, repr=False)


# -- Clé personnelle (identifiants PISTE de l'utilisateur) -------------------


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


# -- Jeton personnel du mode partagé -----------------------------------------


def new_personal_token() -> str:
    return PERSONAL_TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_personal_token(token: str, pepper: bytes) -> str:
    """Empreinte stockée. La recherche se fait sur l'empreinte : aucune
    comparaison n'est jamais faite sur le jeton lui-même, ce qui ôte toute prise
    à une attaque par mesure de temps."""
    return hmac.new(pepper, token.encode("ascii"), hashlib.sha256).hexdigest()


# -- Vérificateur composite --------------------------------------------------


class AccessVerifier:
    """Implémente ``TokenVerifier`` du SDK MCP pour les trois formes de jeton."""

    def __init__(
        self,
        *,
        store: Store,
        pepper: bytes,
        resource: str,
        scopes: Iterable[str],
        oauth_verifier=None,
        personal_keys_enabled: bool = True,
    ) -> None:
        self._store = store
        self._pepper = pepper
        self._resource = resource
        self._scopes = list(scopes)
        self._oauth = oauth_verifier
        self._personal_keys_enabled = personal_keys_enabled

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token or len(token) > MAX_BEARER_LENGTH:
            LOGGER.info("auth_rejected reason=Malformed")
            return None
        if token.startswith(PERSONAL_KEY_PREFIX):
            return self._personal_key(token)
        if token.startswith(PERSONAL_TOKEN_PREFIX):
            return await self._personal_token(token)
        return await self._oauth_token(token)

    def _personal_key(self, token: str) -> AccessGrant | None:
        if not self._personal_keys_enabled:
            LOGGER.info("auth_rejected reason=PersonalKeysDisabled")
            return None
        credentials = parse_personal_key(token)
        if credentials is None:
            LOGGER.info("auth_rejected reason=MalformedPersonalKey")
            return None
        return AccessGrant(
            token="[clé personnelle]",
            client_id="pandecte-cle-personnelle",
            scopes=self._scopes,
            resource=self._resource,
            subject="cle:" + credentials.fingerprint[:24],
            mode="keys",
            credentials=credentials,
        )

    async def _personal_token(self, token: str) -> AccessGrant | None:
        if not PERSONAL_TOKEN_RE.match(token):
            LOGGER.info("auth_rejected reason=MalformedPersonalToken")
            return None
        digest = hash_personal_token(token, self._pepper)
        subject = await anyio.to_thread.run_sync(self._store.subject_for, digest)
        if subject is None:
            LOGGER.info("auth_rejected reason=UnknownPersonalToken")
            return None
        return AccessGrant(
            token="[jeton personnel]",
            client_id="pandecte-jeton-personnel",
            scopes=self._scopes,
            resource=self._resource,
            subject=subject,
            mode="shared",
        )

    async def _oauth_token(self, token: str) -> AccessGrant | None:
        if self._oauth is None:
            LOGGER.info("auth_rejected reason=OAuthDisabled")
            return None
        validated = await self._oauth.verify_token(token)
        if validated is None or not validated.subject:
            return None
        return AccessGrant(
            token="[jeton OAuth]",
            client_id=validated.client_id,
            scopes=validated.scopes,
            expires_at=validated.expires_at,
            resource=validated.resource,
            subject=validated.subject,
            claims=validated.claims,
            mode="shared",
        )

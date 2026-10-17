"""Serveur d'autorisation OAuth 2.1 sans stockage, adossé aux clés PISTE.

claude.ai, ChatGPT et les autres clients MCP n'envoient pas d'en-tête choisi
par l'utilisateur : ils suivent OAuth. Ce module fait du serveur MCP son
propre serveur d'autorisation, dont la page de connexion demande les
identifiants PISTE **de l'utilisateur** (``mcp_server.connexion``).

Le SDK MCP porte le protocole — PKCE, correspondance de ``redirect_uri``,
expiration des codes, authentification du client, renouvellement. Ce
fournisseur n'en remplace que la mémoire : chaque élément est une enveloppe
chiffrée (``mcp_server.sealed``) que le client transporte sans la lire.

=========================  ======================================  =========
Élément                    Contenu scellé                          Durée
=========================  ======================================  =========
identifiant de client      métadonnées enregistrées, secret        5 ans
demande de connexion       paramètres validés de /authorize         15 min
code d'autorisation        demande + identifiants PISTE             5 min
jeton d'accès              identifiants PISTE, ressource            1 h
jeton de renouvellement    idem                                     90 jours
=========================  ======================================  =========

Le jeton de renouvellement est **reconduit** à chaque usage : un utilisateur
actif ne ressaisit jamais ses clés. Sans stockage, un jeton émis ne peut pas
être révoqué un par un : l'utilisateur coupe l'accès en déconnectant son
client ou en régénérant son secret PISTE ; l'exploitant, en changeant la clé
de scellement. Un code n'est accepté qu'une fois par instance (mémoire
courte) ; PKCE le rend de toute façon inutilisable sans le vérificateur.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from typing import Any, Callable
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl, ValidationError

from pandecte.credentials import PisteCredentials

from mcp_server.access import (
    MAX_BEARER_LENGTH,
    PERSONAL_KEY_PREFIX,
    AccessGrant,
    parse_personal_key,
)
from mcp_server.sealed import SealError, Sealer

LOGGER = logging.getLogger("pandecte.mcp.auth")

CLIENT_TTL = 5 * 365 * 24 * 3600
AUTHREQ_TTL = 15 * 60
CODE_TTL = 5 * 60
ACCESS_TTL = 3600
REFRESH_TTL = 90 * 24 * 3600

#: Chemin de la page qui recueille les identifiants PISTE.
LOGIN_PATH = "/connexion"

#: Métadonnées de client conservées dans l'identifiant scellé : celles dont
#: le SDK a besoin pour valider /authorize et /token, rien d'autre.
_CLIENT_FIELDS = (
    "redirect_uris",
    "token_endpoint_auth_method",
    "grant_types",
    "response_types",
    "scope",
    "client_name",
)


def _client_tag(client_id: str) -> str:
    """Empreinte courte de l'identifiant de client, pour les jetons."""
    return hashlib.sha256(client_id.encode("ascii", "replace")).hexdigest()[:24]


def _credentials_claims(credentials: PisteCredentials) -> list[str]:
    claims = [credentials.client_id, credentials.client_secret]
    if credentials.key_id:
        claims.append(credentials.key_id)
    return claims


def _credentials_from(claims: Any) -> PisteCredentials | None:
    if (
        not isinstance(claims, list)
        or len(claims) not in (2, 3)
        or not all(isinstance(item, str) and item for item in claims)
    ):
        return None
    return PisteCredentials(*claims)


class _UsedCodes:
    """Mémoire courte des codes déjà échangés (par instance)."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def first_use(self, code: str) -> bool:
        digest = hashlib.sha256(code.encode("ascii", "replace")).hexdigest()
        now = self._clock()
        with self._lock:
            for key in [key for key, until in self._seen.items() if until <= now]:
                del self._seen[key]
            if digest in self._seen:
                return False
            self._seen[digest] = now + CODE_TTL + 60
            return True


class PisteAuthProvider:
    """Implémente ``OAuthAuthorizationServerProvider`` du SDK MCP, sans état."""

    def __init__(
        self,
        sealer: Sealer,
        *,
        public_url: str,
        resource: str,
        personal_keys_enabled: bool = True,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._sealer = sealer
        self._public_url = public_url.rstrip("/")
        self._resource = resource
        self._personal_keys_enabled = personal_keys_enabled
        self._clock = clock
        self._used_codes = _UsedCodes(clock)

    # -- Clients -------------------------------------------------------------

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Remplace l'identifiant aléatoire du SDK par un identifiant scellé.

        Le gestionnaire d'enregistrement du SDK rend **l'objet même** passé
        ici : modifier ``client_id`` et ``client_secret`` en place suffit à
        ce que le client reçoive l'identifiant scellé. Le test
        ``test_registration_returns_a_sealed_client_id`` garde ce contrat si
        le SDK évolue.
        """
        metadata = client_info.model_dump(mode="json", include=set(_CLIENT_FIELDS))
        secret = secrets.token_urlsafe(32) if client_info.client_secret else None
        claims = {"m": metadata}
        if secret:
            claims["s"] = secret
        client_info.client_id = self._sealer.seal("client", claims, CLIENT_TTL)
        client_info.client_secret = secret
        if secret:
            client_info.client_secret_expires_at = 0

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        try:
            claims = self._sealer.open("client", client_id)
            return OAuthClientInformationFull.model_validate(
                {
                    **claims["m"],
                    "client_id": client_id,
                    "client_secret": claims.get("s"),
                    "client_secret_expires_at": 0 if claims.get("s") else None,
                }
            )
        except (SealError, KeyError, TypeError, ValidationError):
            return None

    # -- Autorisation --------------------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Renvoie vers la page de connexion, avec la demande scellée."""
        if params.resource is not None and params.resource.rstrip("/") != self._resource:
            raise AuthorizeError(
                error="invalid_request",
                error_description="Ressource inconnue de ce serveur.",
            )
        request = {
            "c": client.client_id,
            "r": str(params.redirect_uri),
            "x": params.redirect_uri_provided_explicitly,
            "p": params.code_challenge,
            "t": params.state,
            "s": params.scopes or [],
            "n": client.client_name or "",
        }
        sealed = self._sealer.seal("authreq", request, AUTHREQ_TTL)
        return f"{self._public_url}{LOGIN_PATH}?{urlencode({'demande': sealed})}"

    def read_request(self, sealed: str) -> dict[str, Any] | None:
        """Demande de connexion encore valide, pour la page de connexion."""
        try:
            request = self._sealer.open("authreq", sealed)
        except SealError:
            return None
        if not isinstance(request.get("c"), str) or not isinstance(request.get("r"), str):
            return None
        return request

    def issue_code(self, request: dict[str, Any], credentials: PisteCredentials) -> str:
        """URL de retour vers le client, portant le code scellé."""
        code = self._sealer.seal(
            "code",
            {
                "c": request["c"],
                "r": request["r"],
                "x": request["x"],
                "p": request["p"],
                "s": request["s"],
                "k": _credentials_claims(credentials),
            },
            CODE_TTL,
        )
        return construct_redirect_uri(request["r"], code=code, state=request.get("t"))

    @staticmethod
    def denial_url(request: dict[str, Any]) -> str:
        """URL de retour quand l'utilisateur renonce."""
        return construct_redirect_uri(
            request["r"],
            error="access_denied",
            error_description="Connexion annulée par l'utilisateur.",
            state=request.get("t"),
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        try:
            claims = self._sealer.open("code", authorization_code)
        except SealError:
            return None
        if claims.get("c") != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=list(claims.get("s") or []),
            expires_at=float(claims["exp"]),
            client_id=claims["c"],
            code_challenge=claims["p"],
            redirect_uri=AnyUrl(claims["r"]),
            redirect_uri_provided_explicitly=bool(claims["x"]),
            resource=self._resource,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if not self._used_codes.first_use(authorization_code.code):
            raise TokenError("invalid_grant", "Code d'autorisation déjà utilisé.")
        try:
            claims = self._sealer.open("code", authorization_code.code)
        except SealError as exc:
            raise TokenError("invalid_grant", "Code d'autorisation invalide.") from exc
        credentials = _credentials_from(claims.get("k"))
        if credentials is None:
            raise TokenError("invalid_grant", "Code d'autorisation invalide.")
        LOGGER.info("oauth_token_issued grant=authorization_code")
        return self._tokens(client.client_id, credentials, authorization_code.scopes)

    # -- Renouvellement ------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        try:
            claims = self._sealer.open("refresh", refresh_token)
        except SealError:
            return None
        if claims.get("ct") != _client_tag(client.client_id):
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=list(claims.get("s") or []),
            expires_at=claims["exp"],
            resource=self._resource,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        try:
            claims = self._sealer.open("refresh", refresh_token.token)
        except SealError as exc:
            raise TokenError("invalid_grant", "Jeton de renouvellement invalide.") from exc
        credentials = _credentials_from(claims.get("k"))
        if credentials is None:
            raise TokenError("invalid_grant", "Jeton de renouvellement invalide.")
        LOGGER.info("oauth_token_issued grant=refresh_token")
        return self._tokens(client.client_id, credentials, scopes)

    def _tokens(
        self, client_id: str, credentials: PisteCredentials, scopes: list[str]
    ) -> OAuthToken:
        claims = {"ct": _client_tag(client_id), "k": _credentials_claims(credentials), "s": scopes}
        return OAuthToken(
            access_token=self._sealer.seal("access", claims, ACCESS_TTL),
            token_type="Bearer",
            expires_in=ACCESS_TTL,
            refresh_token=self._sealer.seal("refresh", claims, REFRESH_TTL),
            scope=" ".join(scopes) or None,
        )

    # -- Jetons d'accès ------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        if not token or len(token) > MAX_BEARER_LENGTH:
            LOGGER.info("auth_rejected reason=Malformed")
            return None
        if token.startswith(PERSONAL_KEY_PREFIX):
            return self._personal_key(token)
        try:
            claims = self._sealer.open("access", token)
        except SealError:
            LOGGER.info("auth_rejected reason=InvalidSealedToken")
            return None
        credentials = _credentials_from(claims.get("k"))
        if credentials is None:
            LOGGER.info("auth_rejected reason=InvalidSealedToken")
            return None
        return AccessGrant(
            token="[jeton de connexion PISTE]",
            client_id="client:" + str(claims.get("ct", ""))[:24],
            scopes=list(claims.get("s") or []),
            expires_at=claims["exp"],
            resource=self._resource,
            subject="cle:" + credentials.fingerprint[:24],
            mode="keys",
            credentials=credentials,
        )

    def _personal_key(self, token: str) -> AccessGrant | None:
        """Clé ``pk1`` en en-tête : clients qui n'ont pas OAuth (Claude Code…)."""
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
            scopes=[],
            resource=self._resource,
            subject="cle:" + credentials.fingerprint[:24],
            mode="keys",
            credentials=credentials,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """Sans stockage, rien à révoquer côté serveur (voir l'en-tête)."""
        return None

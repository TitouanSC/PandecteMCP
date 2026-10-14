"""Configuration et garde-fous du serveur MCP public."""

from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Mapping

#: Portées exigées par défaut : aucune. Les jetons WorkOS AuthKit ne portent
#: que des portées OpenID (openid, profile, email, offline_access) ; le droit
#: d'accès repose sur l'authentification et sur le quota du sujet. Une portée
#: peut toujours être exigée via MCP_OAUTH_REQUIRED_SCOPES.
DEFAULT_SCOPES: tuple[str, ...] = ()

#: Longueur minimale du poivre des jetons personnels (PANDECTE_TOKEN_PEPPER).
MIN_PEPPER_LENGTH = 32

#: Forme d'un Client ID WorkOS.
WORKOS_CLIENT_ID_RE = re.compile(r"^client_[A-Za-z0-9]{10,64}$")

#: URL publique de développement acceptée hors production.
LOOPBACK_URL_RE = re.compile(r"^http://(localhost|127\.0\.0\.1)(:[0-9]{1,5})?$")

#: Modes d'authentification acceptés à l'entrée du transport HTTP.
AUTH_MODES: frozenset[str] = frozenset({"disabled", "oauth"})


class RuntimeConfigurationError(ValueError):
    """Configuration invalide, formulée sans recopier les secrets."""


class RuntimeCapacityError(RuntimeError):
    """Capacité temporairement épuisée."""


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeConfigurationError(f"{name} doit être un entier.") from exc
    if value <= 0:
        raise RuntimeConfigurationError(f"{name} doit être strictement positif.")
    return value


def _positive_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeConfigurationError(f"{name} doit être un nombre.") from exc
    if value <= 0:
        raise RuntimeConfigurationError(f"{name} doit être strictement positif.")
    return value


def _non_negative_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeConfigurationError(f"{name} doit être un entier.") from exc
    if value < 0:
        raise RuntimeConfigurationError(f"{name} doit être positif ou nul.")
    return value


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "oui", "yes", "on"}:
        return True
    if value in {"0", "false", "non", "no", "off"}:
        return False
    raise RuntimeConfigurationError(f"{name} doit valoir true ou false.")


def _https_url(
    env: Mapping[str, str], name: str, *, strip_trailing_slash: bool = True
) -> str:
    """Lit une URL publique et refuse tout schéma non chiffré.

    ``strip_trailing_slash`` vaut ``False`` pour l'émetteur OAuth : sa forme
    canonique doit rester celle que publie le serveur d'autorisation, barre
    oblique finale comprise. Voir ``RuntimeSettings.oauth_issuer``.
    """
    raw = env.get(name, "").strip()
    if strip_trailing_slash:
        raw = raw.rstrip("/")
    if not raw:
        raise RuntimeConfigurationError(f"{name} est obligatoire avec MCP_AUTH_MODE=oauth.")
    if not raw.startswith("https://"):
        raise RuntimeConfigurationError(f"{name} doit commencer par https://.")
    return raw


#: Valeurs signifiant « aucune portée exigée », écrites explicitement.
NO_SCOPE_TOKENS: frozenset[str] = frozenset({"-", "none", "aucune"})


def _split_scopes(raw: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    """Découpe la liste des portées exigées, opt-out explicite compris.

    Une variable absente garde la valeur par défaut. Une variable valant ``-``,
    ``none`` ou ``aucune`` désactive volontairement le contrôle de portée : le
    transport exige alors un jeton valide, mais aucune portée particulière.
    Cas d'usage réel : un client qui n'annonce pas la portée personnalisée dans
    sa requête d'autorisation, alors que l'authentification, elle, aboutit.
    L'imputabilité repose sur le sujet du jeton, pas sur la portée.
    """
    if raw is None or not raw.strip():
        return default
    if raw.strip().lower() in NO_SCOPE_TOKENS:
        return ()
    separator = "," if "," in raw else " "
    values = tuple(item.strip() for item in raw.split(separator) if item.strip())
    return values or default


@dataclass(frozen=True)
class RuntimeSettings:
    environment: str
    host: str
    port: int
    log_level: str
    max_concurrent_requests: int
    tool_calls_per_minute: int
    queue_timeout_seconds: float
    max_request_body_bytes: int
    auth_mode: str = "disabled"
    public_url: str = ""
    #: Émetteur OAuth dans sa forme canonique, recopiée telle quelle depuis le
    #: champ « issuer » du document de découverte. OpenAI compare cette chaîne
    #: caractère pour caractère à celle que publient les métadonnées RFC 9728 :
    #: une barre oblique finale ajoutée ou retirée fait échouer le connecteur.
    oauth_issuer: str = ""
    oauth_jwks_url: str = ""
    oauth_audience: str = ""
    oauth_required_scopes: tuple[str, ...] = field(default_factory=lambda: DEFAULT_SCOPES)
    user_calls_per_minute: int = 10
    user_calls_per_day: int = 100
    global_calls_per_day: int = 2000
    keys_calls_per_minute: int = 30
    personal_keys_enabled: bool = True
    #: Dossier de la base SQLite ; sur Render, le point de montage du disque.
    data_dir: str = "data"
    #: Nombre de proxys de confiance devant le serveur (1 sur Render) : l'IP
    #: cliente est lue à cette position, depuis la droite, dans X-Forwarded-For.
    trusted_proxy_hops: int = 0
    #: En-tête portant l'IP cliente, posé et réécrit par le proxy de
    #: l'hébergeur (prioritaire sur X-Forwarded-For) ; vide par défaut.
    client_ip_header: str = ""
    #: Page /diagnostic-ip, pour vérifier la lecture de l'IP au déploiement.
    ip_diagnostic: bool = False
    #: Client ID WorkOS (public) : active la page « Mon compte ». La connexion
    #: passe par PKCE ; aucune clé API WorkOS n'est nécessaire au serveur.
    workos_client_id: str = ""
    workos_api_base: str = "https://api.workos.com"
    #: Durées du cache des réponses, en secondes (0 désactive) ; plafond en Mo.
    cache_text_ttl: int = 6 * 3600
    cache_decision_ttl: int = 24 * 3600
    cache_max_mb: int = 200

    @property
    def auth_enabled(self) -> bool:
        return self.auth_mode == "oauth"

    @property
    def account_enabled(self) -> bool:
        return self.auth_enabled and bool(self.workos_client_id)

    @property
    def resource_url(self) -> str:
        """URL canonique de la ressource protégée, au sens de la RFC 8707."""
        return f"{self.public_url}/mcp" if self.public_url else ""

    @property
    def oauth_issuer_base(self) -> str:
        """Émetteur tronqué de sa barre finale, réservé aux concaténations d'URL.

        ``oauth_issuer`` porte la forme canonique publiée telle quelle dans les
        métadonnées ; elle ne doit jamais servir à construire un chemin, sous
        peine de produire une double barre qu'Auth0 renvoie en « Not found ».
        """
        return self.oauth_issuer.rstrip("/")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RuntimeSettings":
        values = os.environ if env is None else env
        port_name = "PORT" if values.get("PORT") else "MCP_PORT"
        port = _positive_int(values, port_name, 8000)
        if port > 65535:
            raise RuntimeConfigurationError(
                f"{port_name} doit être compris entre 1 et 65535."
            )
        log_level = values.get("MCP_LOG_LEVEL", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise RuntimeConfigurationError("MCP_LOG_LEVEL est invalide.")
        environment = values.get("MCP_ENV", "development").strip().lower()
        if environment not in {"development", "test", "production"}:
            raise RuntimeConfigurationError(
                "MCP_ENV doit valoir development, test ou production."
            )

        auth_mode = values.get("MCP_AUTH_MODE", "disabled").strip().lower()
        if auth_mode not in AUTH_MODES:
            raise RuntimeConfigurationError(
                "MCP_AUTH_MODE doit valoir disabled ou oauth."
            )

        public_url = ""
        issuer = ""
        jwks_url = ""
        audience = ""
        scopes = _split_scopes(values.get("MCP_OAUTH_REQUIRED_SCOPES"), DEFAULT_SCOPES)
        if auth_mode == "oauth":
            raw_public = values.get("MCP_PUBLIC_URL", "").strip().rstrip("/")
            if environment != "production" and LOOPBACK_URL_RE.match(raw_public):
                # Développement : http://localhost:PORT, pour tester la page
                # de compte contre un environnement WorkOS de test.
                public_url = raw_public
            else:
                public_url = _https_url(values, "MCP_PUBLIC_URL")
            issuer = _https_url(
                values, "MCP_OAUTH_ISSUER", strip_trailing_slash=False
            )
            jwks_url = values.get("MCP_OAUTH_JWKS_URL", "").strip()
            if not jwks_url:
                # Emplacement publié par WorkOS AuthKit.
                jwks_url = f"{issuer.rstrip('/')}/oauth2/jwks"
            if not jwks_url.startswith("https://"):
                raise RuntimeConfigurationError(
                    "MCP_OAUTH_JWKS_URL doit commencer par https://."
                )
            audience = values.get("MCP_OAUTH_AUDIENCE", "").strip()
            if not audience:
                audience = f"{public_url}/mcp"

        client_ip_header = values.get("MCP_CLIENT_IP_HEADER", "").strip().lower()
        if client_ip_header and not re.match(r"^[a-z0-9-]{1,64}$", client_ip_header):
            raise RuntimeConfigurationError("MCP_CLIENT_IP_HEADER est un nom d'en-tête invalide.")
        workos_client_id = values.get("WORKOS_CLIENT_ID", "").strip()
        if workos_client_id and not WORKOS_CLIENT_ID_RE.match(workos_client_id):
            raise RuntimeConfigurationError(
                "WORKOS_CLIENT_ID doit avoir la forme client_… ."
            )
        workos_api_base = (
            values.get("WORKOS_API_BASE", "").strip().rstrip("/") or "https://api.workos.com"
        )
        if not workos_api_base.startswith("https://"):
            raise RuntimeConfigurationError("WORKOS_API_BASE doit commencer par https://.")

        return cls(
            environment=environment,
            host=values.get("MCP_HOST", "127.0.0.1"),
            port=port,
            log_level=log_level,
            max_concurrent_requests=_positive_int(
                values, "MCP_MAX_CONCURRENT_REQUESTS", 8
            ),
            tool_calls_per_minute=_positive_int(
                values, "MCP_TOOL_CALLS_PER_MINUTE", 120
            ),
            queue_timeout_seconds=_positive_float(
                values, "MCP_QUEUE_TIMEOUT_SECONDS", 2.0
            ),
            max_request_body_bytes=_positive_int(
                values, "MCP_MAX_REQUEST_BODY_BYTES", 1_048_576
            ),
            auth_mode=auth_mode,
            public_url=public_url,
            oauth_issuer=issuer,
            oauth_jwks_url=jwks_url,
            oauth_audience=audience,
            oauth_required_scopes=scopes,
            user_calls_per_minute=_positive_int(
                values, "MCP_USER_CALLS_PER_MINUTE", 10
            ),
            user_calls_per_day=_positive_int(values, "MCP_USER_CALLS_PER_DAY", 100),
            global_calls_per_day=_positive_int(
                values, "MCP_GLOBAL_CALLS_PER_DAY", 2000
            ),
            keys_calls_per_minute=_positive_int(
                values, "MCP_KEYS_CALLS_PER_MINUTE", 30
            ),
            personal_keys_enabled=_boolean(values, "MCP_PERSONAL_KEYS_ENABLED", True),
            data_dir=values.get("PANDECTE_DATA_DIR", "data").strip() or "data",
            trusted_proxy_hops=_non_negative_int(values, "MCP_TRUSTED_PROXY_HOPS", 0),
            client_ip_header=client_ip_header,
            ip_diagnostic=_boolean(values, "MCP_IP_DIAGNOSTIC", False),
            workos_client_id=workos_client_id,
            workos_api_base=workos_api_base,
            cache_text_ttl=_non_negative_int(values, "PANDECTE_CACHE_TEXT_TTL", 6 * 3600),
            cache_decision_ttl=_non_negative_int(
                values, "PANDECTE_CACHE_DECISION_TTL", 24 * 3600
            ),
            cache_max_mb=_positive_int(values, "PANDECTE_CACHE_MAX_MB", 200),
        )

    def validate_public(self, env: Mapping[str, str] | None = None) -> None:
        """Refuse un démarrage public mal configuré sans afficher de valeur."""
        values = os.environ if env is None else env
        if self.environment != "production":
            return

        missing = [
            name
            for name in ("LEGIFRANCE_CLIENT_ID", "LEGIFRANCE_CLIENT_SECRET")
            if not values.get(name, "").strip()
        ]
        if not (
            values.get("JUDILIBRE_KEY_ID", "").strip()
            or values.get("PISTE_KEY_ID", "").strip()
        ):
            missing.append("JUDILIBRE_KEY_ID (ou PISTE_KEY_ID)")
        if missing:
            raise RuntimeConfigurationError(
                "Variables obligatoires absentes en production : " + ", ".join(missing)
            )
        if values.get("LEGIFRANCE_ENV", "prod").lower() != "prod":
            raise RuntimeConfigurationError(
                "LEGIFRANCE_ENV doit valoir prod en production."
            )
        if values.get("JUDILIBRE_ENV", "prod").lower() != "prod":
            raise RuntimeConfigurationError(
                "JUDILIBRE_ENV doit valoir prod en production."
            )
        if not self.auth_enabled:
            # Sans authentification, l'URL publique consommerait les quotas
            # PISTE sous la seule responsabilité du titulaire des clés.
            raise RuntimeConfigurationError(
                "MCP_AUTH_MODE doit valoir oauth en production : une passerelle "
                "MCP publique anonyme engage les identifiants PISTE du titulaire."
            )
        if len(values.get("PANDECTE_TOKEN_PEPPER", "").strip()) < MIN_PEPPER_LENGTH:
            raise RuntimeConfigurationError(
                "PANDECTE_TOKEN_PEPPER doit contenir au moins "
                f"{MIN_PEPPER_LENGTH} caractères aléatoires en production."
            )


class RequestGovernor:
    """Limite la concurrence et le débit des outils par instance."""

    def __init__(
        self,
        max_concurrent: int,
        requests_per_minute: int,
        queue_timeout_seconds: float,
    ) -> None:
        self._semaphore = threading.BoundedSemaphore(max_concurrent)
        self._requests_per_minute = requests_per_minute
        self._queue_timeout_seconds = queue_timeout_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    @contextmanager
    def slot(self) -> Iterator[None]:
        acquired = self._semaphore.acquire(timeout=self._queue_timeout_seconds)
        if not acquired:
            raise RuntimeCapacityError("Serveur temporairement occupé ; réessayer.")
        try:
            now = time.monotonic()
            with self._lock:
                while self._timestamps and self._timestamps[0] <= now - 60:
                    self._timestamps.popleft()
                if len(self._timestamps) >= self._requests_per_minute:
                    raise RuntimeCapacityError(
                        "Quota temporaire de consultation atteint ; réessayer plus tard."
                    )
                self._timestamps.append(now)
            yield
        finally:
            self._semaphore.release()

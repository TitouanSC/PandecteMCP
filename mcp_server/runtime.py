"""Configuration et garde-fous du serveur MCP public."""

from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Mapping

#: URL publique de développement acceptée hors production.
LOOPBACK_URL_RE = re.compile(r"^http://(localhost|127\.0\.0\.1)(:[0-9]{1,5})?$")

#: Identifiants PISTE du titulaire : jamais lus par le serveur hébergé.
OWNER_CREDENTIAL_VARIABLES = (
    "LEGIFRANCE_CLIENT_ID",
    "LEGIFRANCE_CLIENT_SECRET",
    "JUDILIBRE_KEY_ID",
    "PISTE_KEY_ID",
)

#: Modes d'authentification du transport HTTP.
#: ``disabled`` : aucun contrôle, identifiants de l'environnement — usage
#: local uniquement (stdio, essai sur son poste), refusé en production.
#: ``piste`` : le serveur est son propre serveur d'autorisation et n'utilise
#: que les identifiants PISTE de chaque utilisateur (``mcp_server.piste_oauth``).
AUTH_MODES: frozenset[str] = frozenset({"disabled", "piste"})


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


def _https_url(env: Mapping[str, str], name: str) -> str:
    """Lit une URL publique et refuse tout schéma non chiffré."""
    raw = env.get(name, "").strip().rstrip("/")
    if not raw:
        raise RuntimeConfigurationError(f"{name} est obligatoire avec MCP_AUTH_MODE=piste.")
    if not raw.startswith("https://"):
        raise RuntimeConfigurationError(f"{name} doit commencer par https://.")
    return raw


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
    #: Appels d'outils par minute et par adresse IP (protection de l'instance).
    calls_per_minute_per_ip: int = 30
    personal_keys_enabled: bool = True
    #: Nombre de proxys de confiance devant le serveur : l'IP cliente est lue
    #: à cette position, depuis la droite, dans X-Forwarded-For.
    trusted_proxy_hops: int = 0
    #: En-tête portant l'IP cliente, posé et réécrit par le proxy de
    #: l'hébergeur (prioritaire sur X-Forwarded-For) ; vide par défaut.
    client_ip_header: str = ""
    #: Page /diagnostic-ip, pour vérifier la lecture de l'IP au déploiement.
    ip_diagnostic: bool = False
    #: Durées du cache des réponses, en secondes (0 désactive) ; plafond en Mo.
    cache_text_ttl: int = 6 * 3600
    cache_decision_ttl: int = 24 * 3600
    cache_max_mb: int = 50

    @property
    def auth_enabled(self) -> bool:
        return self.auth_mode == "piste"

    @property
    def resource_url(self) -> str:
        """URL canonique de la ressource protégée, au sens de la RFC 8707."""
        return f"{self.public_url}/mcp" if self.public_url else ""

    @property
    def oauth_issuer(self) -> str:
        """Le serveur est son propre émetteur OAuth."""
        return self.public_url

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
                "MCP_AUTH_MODE doit valoir disabled ou piste."
            )

        public_url = ""
        if auth_mode == "piste":
            raw_public = values.get("MCP_PUBLIC_URL", "").strip().rstrip("/")
            if environment != "production" and LOOPBACK_URL_RE.match(raw_public):
                # Développement : http://localhost:PORT, sans certificat.
                public_url = raw_public
            else:
                public_url = _https_url(values, "MCP_PUBLIC_URL")

        client_ip_header = values.get("MCP_CLIENT_IP_HEADER", "").strip().lower()
        if client_ip_header and not re.match(r"^[a-z0-9-]{1,64}$", client_ip_header):
            raise RuntimeConfigurationError("MCP_CLIENT_IP_HEADER est un nom d'en-tête invalide.")

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
            calls_per_minute_per_ip=_positive_int(
                values, "MCP_CALLS_PER_MINUTE_PER_IP", 30
            ),
            personal_keys_enabled=_boolean(values, "MCP_PERSONAL_KEYS_ENABLED", True),
            trusted_proxy_hops=_non_negative_int(values, "MCP_TRUSTED_PROXY_HOPS", 0),
            client_ip_header=client_ip_header,
            ip_diagnostic=_boolean(values, "MCP_IP_DIAGNOSTIC", False),
            cache_text_ttl=_non_negative_int(values, "PANDECTE_CACHE_TEXT_TTL", 6 * 3600),
            cache_decision_ttl=_non_negative_int(
                values, "PANDECTE_CACHE_DECISION_TTL", 24 * 3600
            ),
            # Cache en mémoire vive : plafond modeste.
            cache_max_mb=_positive_int(values, "PANDECTE_CACHE_MAX_MB", 50),
        )

    def validate_public(self, env: Mapping[str, str] | None = None) -> None:
        """Refuse un démarrage public mal configuré sans afficher de valeur."""
        values = os.environ if env is None else env
        if self.environment != "production":
            return
        if self.auth_mode != "piste":
            # Sans authentification, l'URL publique serait une passerelle
            # anonyme vers PISTE.
            raise RuntimeConfigurationError(
                "MCP_AUTH_MODE doit valoir piste en production."
            )
        from mcp_server.sealed import parse_key

        for name in ("PANDECTE_SEAL_KEY", "PANDECTE_SEAL_KEY_PREVIOUS"):
            raw = values.get(name, "").strip()
            if name == "PANDECTE_SEAL_KEY" and not raw:
                raise RuntimeConfigurationError(
                    "PANDECTE_SEAL_KEY est obligatoire en production."
                )
            if raw:
                try:
                    parse_key(raw)
                except ValueError as exc:
                    raise RuntimeConfigurationError(f"{name} : {exc}") from exc
        present = [
            name for name in OWNER_CREDENTIAL_VARIABLES if values.get(name, "").strip()
        ]
        if present:
            # Le serveur n'utilise que les identifiants des utilisateurs :
            # ceux du titulaire n'ont rien à y faire.
            raise RuntimeConfigurationError(
                "Retirer de l'environnement de production : " + ", ".join(present) + "."
            )
        for name in ("LEGIFRANCE_ENV", "JUDILIBRE_ENV"):
            if values.get(name, "prod").lower() != "prod":
                raise RuntimeConfigurationError(f"{name} doit valoir prod en production.")


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

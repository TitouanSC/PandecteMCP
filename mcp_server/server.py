#!/usr/bin/env python3
"""Expose les sources officielles du skill via le protocole MCP."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import secrets
import sys
import time
import uuid
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skill" / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

try:  # SDK MCP v2
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    MCP_V2 = True
except ImportError:  # SDK MCP v1.27, encore largement installé
    from mcp.server.fastmcp import FastMCP as MCPServer
    from mcp.server.fastmcp.exceptions import ToolError
    MCP_V2 = False
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from pandecte.config import load_dotenv
from pandecte.credentials import mask_secrets, use_credentials
from pandecte.errors import LegifranceError
from pandecte import tools as legal_tools
from mcp_server.access import AccessGrant, AccessVerifier
from mcp_server.cache import ResponseCache
from mcp_server.http_guard import HttpGuard, client_ip
from mcp_server.quotas import QuotaExceeded, QuotaPolicy
from mcp_server.store import Store
from mcp_server.runtime import (
    OWNER_CREDENTIAL_VARIABLES,
    RequestGovernor,
    RuntimeCapacityError,
    RuntimeConfigurationError,
    RuntimeSettings,
)

load_dotenv(script_dir=SCRIPTS)
SETTINGS = RuntimeSettings.from_env()
#: Mode piste : les identifiants PISTE du titulaire sont retirés du processus
#: dès le démarrage, pour qu'aucun chemin de code ne puisse s'en servir. Seule
#: leur présence est retenue, pour que la validation de production la refuse.
_OWNER_CREDENTIALS_SEEN: dict[str, str] = {}
if SETTINGS.auth_mode == "piste":
    for _name in OWNER_CREDENTIAL_VARIABLES:
        if os.environ.pop(_name, "").strip():
            _OWNER_CREDENTIALS_SEEN[_name] = "présent"
logging.basicConfig(
    level=getattr(logging, SETTINGS.log_level),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("pandecte.mcp")
# L'image de production tourne en WARNING pour faire taire le SDK MCP et le
# serveur HTTP. Le journal métier, lui, est la seule trace d'imputabilité des
# appels d'outils : il doit survivre à ce réglage. Le niveau du logger
# d'origine décide seul de l'émission, indépendamment du logger racine.
if LOGGER.level in (logging.NOTSET,) or LOGGER.getEffectiveLevel() > logging.INFO:
    LOGGER.setLevel(logging.INFO)
logging.getLogger("pandecte.mcp.auth").setLevel(logging.INFO)
GOVERNOR = RequestGovernor(
    SETTINGS.max_concurrent_requests,
    SETTINGS.tool_calls_per_minute,
    SETTINGS.queue_timeout_seconds,
)

#: Base SQLite (jetons personnels hachés, compteurs journaliers) et quotas :
#: n'existent qu'avec l'authentification. En stdio local, seul le
#: gouverneur d'instance s'applique.
STORE: Store | None = None
QUOTAS: QuotaPolicy | None = None
CACHE: ResponseCache | None = None
if SETTINGS.auth_enabled:
    # Mode piste : rien à conserver d'un redémarrage à l'autre (ni jeton, ni
    # quota partagé) ; la base ne sert qu'au cache, en mémoire vive.
    STORE = Store(
        ":memory:"
        if SETTINGS.auth_mode == "piste"
        else Path(SETTINGS.data_dir) / "pandecte.sqlite3"
    )
    QUOTAS = QuotaPolicy(
        STORE,
        user_per_minute=SETTINGS.user_calls_per_minute,
        user_per_day=SETTINGS.user_calls_per_day,
        global_per_day=SETTINGS.global_calls_per_day,
        keys_per_minute_per_ip=SETTINGS.keys_calls_per_minute,
    )
    CACHE = ResponseCache(
        STORE,
        text_ttl=SETTINGS.cache_text_ttl,
        decision_ttl=SETTINGS.cache_decision_ttl,
        max_bytes=SETTINGS.cache_max_mb * 1024 * 1024,
        suppressed=legal_tools._suppressed_decision_ids,
    )


def token_pepper() -> bytes:
    """Poivre des jetons personnels.

    Exigé en production (``validate_public``). Hors production, un poivre
    aléatoire par processus est tiré : les jetons émis ne survivent alors pas
    à un redémarrage, ce qui suffit au développement.
    """
    configured = os.environ.get("PANDECTE_TOKEN_PEPPER", "").strip()
    if configured:
        return configured.encode("utf-8")
    return _EPHEMERAL_PEPPER


_EPHEMERAL_PEPPER = secrets.token_bytes(32)


def seal_keys() -> tuple[bytes, tuple[bytes, ...]]:
    """Clé de scellement courante et éventuelle clé précédente (rotation).

    Exigée en production (``validate_public``). Hors production, une clé
    aléatoire par processus : les connexions ne survivent pas au redémarrage.
    """
    from mcp_server.sealed import parse_key

    raw = os.environ.get("PANDECTE_SEAL_KEY", "").strip()
    current = parse_key(raw) if raw else _EPHEMERAL_SEAL_KEY
    previous = os.environ.get("PANDECTE_SEAL_KEY_PREVIOUS", "").strip()
    return current, ((parse_key(previous),) if previous else ())


_EPHEMERAL_SEAL_KEY = secrets.token_bytes(32)

SERVER_VERSION = "0.1.0"


def _load_suppression_list() -> int:
    """Charge la liste de retrait d'urgence Judilibre et en rend le nombre.

    Le mécanisme est une mesure conservatoire jouée sous pression : un
    identifiant mal recopié ne doit pas être accepté en silence. La liste est
    donc analysée au démarrage — une entrée malformée empêche le service de
    partir, avec un message qui nomme la position fautive — et son **nombre**
    d'entrées est journalisé. Jamais les identifiants eux-mêmes, qui restent
    des données de configuration non publiques.
    """
    try:
        loaded = legal_tools.parse_suppressed_ids(
            os.environ.get(legal_tools.JUDILIBRE_SUPPRESSION_ENV)
        )
    except LegifranceError as exc:
        raise RuntimeConfigurationError(str(exc)) from exc
    LOGGER.info("judilibre_suppression_list count=%d", len(loaded))
    return len(loaded)


def _build_auth_options() -> dict[str, Any]:
    """Configure le serveur en Resource Server OAuth 2.1, si demandé.

    L'import du vérificateur reste local : le transport stdio, utilisé pour
    un usage personnel, n'a alors besoin ni de PyJWT ni d'un émetteur.
    """
    if not SETTINGS.auth_enabled:
        return {}
    if SETTINGS.auth_mode == "piste":
        return _build_piste_auth_options()

    from mcp.server.auth.settings import AuthSettings

    from mcp_server.auth import JwksTokenVerifier

    oauth_verifier = JwksTokenVerifier(
        issuer=SETTINGS.oauth_issuer,
        jwks_url=SETTINGS.oauth_jwks_url,
        audience=SETTINGS.oauth_audience,
    )
    verifier = AccessVerifier(
        store=STORE,
        pepper=token_pepper(),
        resource=SETTINGS.resource_url,
        scopes=SETTINGS.oauth_required_scopes,
        oauth_verifier=oauth_verifier,
        personal_keys_enabled=SETTINGS.personal_keys_enabled,
    )
    auth_settings: dict[str, Any] = {
        "issuer_url": SETTINGS.oauth_issuer,
        "resource_server_url": SETTINGS.resource_url,
        "required_scopes": list(SETTINGS.oauth_required_scopes),
    }
    # SDK >= 2.2.0 : laissé vide, ce champ lève un MCPDeprecationWarning et
    # passera à True en 3.0 (refus de tout jeton dont `resource` diffère de
    # `resource_server_url`). Le vérificateur contrôle déjà `aud` contre
    # l'audience configurée — un identifiant d'API Auth0 qui n'est pas
    # forcément l'URL de ressource —, comme le recommande la documentation du
    # SDK dans ce cas : False, explicitement. Champ absent des SDK antérieurs.
    if "validate_token_resource" in AuthSettings.model_fields:
        auth_settings["validate_token_resource"] = False
    return {
        "token_verifier": verifier,
        "auth": AuthSettings(**auth_settings),
    }

PISTE_PROVIDER = None


def _build_piste_auth_options() -> dict[str, Any]:
    """Serveur d'autorisation intégré : connexion par identifiants PISTE."""
    global PISTE_PROVIDER
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions

    from mcp_server.piste_oauth import PisteAuthProvider
    from mcp_server.sealed import Sealer

    current, previous = seal_keys()
    PISTE_PROVIDER = PisteAuthProvider(
        Sealer(current, previous),
        public_url=SETTINGS.public_url,
        resource=SETTINGS.resource_url,
        personal_keys_enabled=SETTINGS.personal_keys_enabled,
    )
    return {
        "auth_server_provider": PISTE_PROVIDER,
        "auth": AuthSettings(
            issuer_url=SETTINGS.public_url,
            resource_server_url=SETTINGS.resource_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
            # Les jetons portent toujours la ressource de ce serveur.
            validate_token_resource=True,
        ),
    }


#: Instructions lues par le client à chaque connexion, « alongside tool
#: metadata » selon OpenAI. C'est le seul canal qui porte de la méthode à un
#: utilisateur ChatGPT sans rien lui demander. OpenAI demande de tenir
#: l'essentiel dans les 512 premiers caractères, de ne pas répéter les
#: descriptions d'outils et de ne pas chercher à modifier la personnalité du
#: modèle. Trois règles porteuses, et rien d'autre : pas de mémoire, vigueur
#: vérifiée, refus explicite. La lecture seule est déjà portée par les
#: annotations ; le paramètre de date, par les descriptions de get_article et
#: search_articles, là où le modèle en a besoin au moment de décider.
INSTRUCTIONS = (
    "Aucune référence juridique — article, décision, identifiant, date — ne se "
    "produit de mémoire : toutes viennent des outils. Vérifiez la version en "
    "vigueur et son champ applicable_at_as_of_date : une source officielle peut "
    "être historique. Si une source n'est pas confirmée, dites-le et ne concluez pas."
)
INSTRUCTIONS_MAX_CHARS = 512

server_options: dict[str, Any] = {
    "log_level": SETTINGS.log_level,
    "instructions": INSTRUCTIONS,
}
if MCP_V2:
    server_options["version"] = SERVER_VERSION
else:
    server_options.update(host=SETTINGS.host, port=SETTINGS.port)
server_options.update(_build_auth_options())
server = MCPServer("PandecteMCP", **server_options)

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    # OpenAI réserve openWorldHint aux outils d'écriture susceptibles de
    # modifier l'état publiquement visible d'internet. Une consultation en
    # lecture seule n'en modifie aucun, même si elle appelle une API externe
    # et consomme un quota.
    openWorldHint=False,
)


def _pseudonym(principal: str) -> str:
    """Empreinte courte et stable : les journaux ne portent aucun identifiant brut."""
    if principal == "anonyme":
        return principal
    return hashlib.sha256(principal.encode("utf-8")).hexdigest()[:12]


def _current_grant() -> AccessGrant | None:
    """Accès validé de la requête courante, sans jamais lire le jeton brut."""
    if not SETTINGS.auth_enabled:
        return None
    from mcp.server.auth.middleware.auth_context import get_access_token

    grant = get_access_token()
    return grant if isinstance(grant, AccessGrant) else None


def _current_principal() -> str:
    """Sujet de quota de la requête courante."""
    grant = _current_grant()
    if grant is None or not grant.subject:
        return "anonyme"
    return grant.subject


def _current_scopes() -> str:
    """Portées effectivement portées par le jeton courant.

    Journalisées parce qu'elles tranchent une question ouverte : le contrôle de
    portée est désactivé faute de savoir si le client demande bien la portée
    personnalisée. Le SDK couple annonce et exigence — ``scopes_supported`` vaut
    ``required_scopes`` — donc réactiver le contrôle sans savoir ce que portent
    les jetons reviendrait à parier sur un `403` généralisé. Une portée n'est
    pas une donnée personnelle : la journaliser ne coûte rien à la vie privée
    et rend la décision mesurable au lieu d'être spéculative.
    """
    if not SETTINGS.auth_enabled:
        return "-"
    from mcp.server.auth.middleware.auth_context import get_access_token

    access_token = get_access_token()
    if access_token is None:
        return "-"
    return ",".join(access_token.scopes) if access_token.scopes else "aucune"


#: Masquage des identifiants PISTE — ceux du titulaire comme ceux transmis par
#: la requête en mode « clés personnelles » — avant toute réponse ou journal.
_mask_secrets = mask_secrets


def _safe_call(operation: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Applique le mode d'accès, les quotas et le masquage autour d'un outil.

    Le client reçoit un message public — code, phrase actionnable, hôte amont
    — et un identifiant de corrélation. Le détail technique (URL amont
    complète, fragment de corps) va dans le journal sous le même identifiant :
    c'est là, et seulement là, qu'on dépanne.

    En mode « clés personnelles », les identifiants de la requête sont posés
    pour TOUTE la durée du traitement, gestion d'erreur comprise : le masquage
    des messages doit encore les connaître au moment où il s'applique.
    """
    grant = _current_grant()
    if SETTINGS.auth_enabled and grant is None:
        raise ToolError("Authentification requise.")
    if grant is not None and grant.mode == "keys":
        credentials = use_credentials(grant.credentials)
    else:
        # Mode partagé ou stdio local : identifiants de l'environnement.
        credentials = nullcontext()
    with credentials:
        return _guarded_call(grant, operation, *args, **kwargs)


def _check_quota(grant: AccessGrant | None) -> None:
    if grant is None:
        return
    if grant.mode == "keys":
        QUOTAS.check_personal_keys(client_ip())
    else:
        QUOTAS.check_shared(grant.subject)


def _guarded_call(
    grant: AccessGrant | None,
    operation: Callable[..., dict[str, Any]],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    started = time.monotonic()
    operation_name = getattr(operation, "__name__", "legal_operation")
    principal = _current_principal()
    mode = grant.mode if grant is not None else "local"
    try:
        _check_quota(grant)
        plan = CACHE.plan(operation_name, args, kwargs) if CACHE is not None else None
        result = CACHE.get(plan) if plan is not None else None
        cache_state = "hit" if result is not None else ("miss" if plan else "-")
        if result is None:
            with GOVERNOR.slot():
                result = operation(*args, **kwargs)
            if plan is not None:
                # Atteint seulement après un succès : une erreur n'est jamais
                # mise en cache.
                CACHE.put(plan, result)
        LOGGER.info(
            "tool_call tool=%s mode=%s principal=%s scopes=%s outcome=success "
            "cache=%s duration_ms=%d",
            operation_name,
            mode,
            _pseudonym(principal),
            _current_scopes(),
            cache_state,
            int((time.monotonic() - started) * 1000),
        )
        return result
    except QuotaExceeded as exc:
        LOGGER.warning(
            "tool_call tool=%s mode=%s principal=%s outcome=quota retry_after=%d",
            operation_name,
            mode,
            _pseudonym(principal),
            exc.retry_after,
        )
        raise ToolError(f"{exc} [retry_after={exc.retry_after}]") from exc
    except RuntimeCapacityError as exc:
        LOGGER.warning("tool_call tool=%s outcome=throttled", operation_name)
        raise ToolError(str(exc)) from exc
    except LegifranceError as exc:
        reference = uuid.uuid4().hex[:8]
        LOGGER.warning(
            "tool_call tool=%s mode=%s outcome=upstream_error ref=%s code=%d "
            "status=%s duration_ms=%d detail=%s",
            operation_name,
            mode,
            reference,
            exc.exit_code,
            exc.http_status if exc.http_status is not None else "-",
            int((time.monotonic() - started) * 1000),
            _mask_secrets(" ".join((exc.detail or str(exc)).split())),
        )
        raise ToolError(
            f"Source officielle non vérifiée (code {exc.exit_code}) : "
            f"{_mask_secrets(str(exc))} [réf. {reference}]"
        ) from exc
    except ToolError:
        raise
    except Exception as exc:
        # Filet : le message d'une exception imprévue n'est jamais renvoyé tel
        # quel au client — il pourrait citer une valeur sensible.
        reference = uuid.uuid4().hex[:8]
        LOGGER.error(
            "tool_call tool=%s mode=%s outcome=internal_error ref=%s type=%s",
            operation_name,
            mode,
            reference,
            type(exc).__name__,
        )
        raise ToolError(f"Erreur interne du serveur [réf. {reference}].") from exc


if hasattr(server, "custom_route"):
    from starlette.requests import Request
    from starlette.responses import JSONResponse, PlainTextResponse, Response

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> Response:
        """Sonde publique sans donnée interne ni vérification consommatrice d'API."""
        return JSONResponse(
            {
                "status": "ok",
                "version": SERVER_VERSION,
                "auth": SETTINGS.auth_mode,
                "personal_keys": SETTINGS.auth_enabled and SETTINGS.personal_keys_enabled,
                "account": SETTINGS.account_enabled,
            }
        )

    _AUTH_SERVER_METADATA: dict[str, Any] = {}

    @server.custom_route(
        "/.well-known/oauth-authorization-server",
        methods=["GET"],
        include_in_schema=False,
    )
    async def authorization_server_metadata(_request: Request) -> Response:
        """Relais des métadonnées du serveur d'autorisation (WorkOS AuthKit).

        Certains clients ignorent les métadonnées RFC 9728 et cherchent celles
        du serveur d'autorisation sur l'hôte du serveur MCP ; WorkOS recommande
        de les relayer. Le document est mis en cache une heure ; une panne de
        l'émetteur rend 502, sans détail. En mode piste, ce document est
        celui du serveur lui-même, servi par la route du SDK enregistrée avant
        celle-ci.
        """
        if not SETTINGS.shared_mode:
            return PlainTextResponse("Not configured", status_code=404)
        cached = _AUTH_SERVER_METADATA.get("document")
        if cached is None or time.monotonic() >= _AUTH_SERVER_METADATA["expires_at"]:
            import anyio

            try:
                cached = await anyio.to_thread.run_sync(_fetch_authorization_metadata)
            except Exception as exc:  # panne réseau ou document invalide
                LOGGER.warning("auth_metadata_unavailable reason=%s", type(exc).__name__)
                return JSONResponse({"error": "issuer_unavailable"}, status_code=502)
            _AUTH_SERVER_METADATA.update(document=cached, expires_at=time.monotonic() + 3600)
        return JSONResponse(cached)

    @server.custom_route(
        "/.well-known/oauth-protected-resource",
        methods=["GET"],
        include_in_schema=False,
    )
    async def protected_resource_root(_request: Request) -> Response:
        """Alias racine : certains clients ignorent le suffixe de chemin RFC 9728.

        L'émetteur est recopié verbatim depuis la configuration, sans
        normalisation : c'est la seule façon d'être identique, caractère pour
        caractère, à ce que sert la route ``/mcp`` du SDK — laquelle préserve
        elle aussi la chaîne configurée (``url_preserve_empty_path``).
        """
        if not SETTINGS.auth_enabled:
            return PlainTextResponse("Not configured", status_code=404)
        return JSONResponse(
            {
                "resource": SETTINGS.resource_url,
                "authorization_servers": [SETTINGS.oauth_issuer],
                "scopes_supported": list(SETTINGS.oauth_required_scopes),
                "bearer_methods_supported": ["header"],
            }
        )

    if SETTINGS.auth_enabled:
        from mcp_server.account import AccountPages

        #: Pages « Mon compte » (si WORKOS_CLIENT_ID) et « Clé personnelle ».
        #: La base et les quotas sont relus à chaque requête.
        ACCOUNT_PAGES = AccountPages(
            settings=SETTINGS,
            store=lambda: STORE,
            quotas=lambda: QUOTAS,
            pepper=token_pepper,
        )
        ACCOUNT_PAGES.register(server)

    if PISTE_PROVIDER is not None:
        from mcp_server.connexion import ConnexionPage

        #: Page « Connexion PISTE » du serveur d'autorisation intégré.
        CONNEXION_PAGE = ConnexionPage(PISTE_PROVIDER, public_url=SETTINGS.public_url)
        CONNEXION_PAGE.register(server)

    @server.custom_route(
        "/.well-known/openai-apps-challenge",
        methods=["GET"],
        include_in_schema=False,
    )
    async def openai_apps_challenge(_request: Request) -> Response:
        """Répond exactement au jeton temporaire fourni lors de la soumission.

        La route doit rendre **le jeton seul** : ni JSON, ni liste, ni plusieurs
        jetons. Les espaces et retours à la ligne sont retirés, parce qu'un
        jeton collé depuis le portail en emporte souvent un — et que la
        vérification compare la réponse au jeton exact.
        """
        token = os.environ.get("OPENAI_APPS_CHALLENGE", "").strip()
        if not token:
            return PlainTextResponse("Not configured", status_code=404)
        return PlainTextResponse(token)


@server.tool(
    name="search",
    title="Rechercher dans les sources juridiques",
    description=(
        "Recherche standard en lecture seule. Une référence d'article, avec ou "
        "sans le mot « article », interroge Légifrance en conservant le code et "
        "la date reconnus ; les autres requêtes interrogent Judilibre. Un "
        "identifiant LEGIARTI fourni est vérifié avant d'être retourné."
    ),
    annotations=READ_ONLY,
)
def search(query: str) -> dict[str, Any]:
    """Search French official legal sources with one plain-text query."""
    return _safe_call(legal_tools.search, query)


@server.tool(
    name="fetch",
    title="Lire une source juridique",
    description=(
        "Récupère le texte et les métadonnées officiels d'un identifiant renvoyé "
        "par search. LEGIARTI et LEGITEXT utilisent Légifrance ; les décisions "
        "utilisent Judilibre. Pour une section CODE, utiliser get_section avec "
        "son LEGITEXT parent. Les textes JORF ne sont pas couverts."
    ),
    annotations=READ_ONLY,
)
def fetch(id: str) -> dict[str, Any]:
    """Fetch one source by the exact identifier returned by search."""
    return _safe_call(legal_tools.fetch, id)


@server.tool(
    name="search_articles",
    title="Rechercher un article de code",
    description=(
        "Recherche dans Légifrance un numéro d'article applicable à une date. "
        "Le code, s'il est fourni, doit être son libellé officiel complet. "
        "Ne renseigner date QUE si l'utilisateur demande une date précise, "
        "passée ou future. Laisser ce paramètre vide pour le droit en vigueur "
        "aujourd'hui : le serveur utilise sa propre horloge, plus fiable que "
        "la date supposée par le modèle."
    ),
    annotations=READ_ONLY,
)
def search_articles(
    number: str,
    code: str | None = None,
    date: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search legislation by article number, optional code title and ISO date."""
    return _safe_call(legal_tools.search_articles, number, code, date, limit)


@server.tool(
    name="get_article",
    title="Lire un article Légifrance",
    description=(
        "Récupère la version désignée par un identifiant LEGIARTI, puis indique "
        "si sa période de validité couvre la date évaluée. Ne renseigner date "
        "QUE si l'utilisateur demande une date précise ; sinon le serveur évalue "
        "l'applicabilité à sa date du jour. Pour trouver la version applicable, "
        "utiliser d'abord search_articles avec la date recherchée."
    ),
    annotations=READ_ONLY,
)
def get_article(id: str, date: str | None = None) -> dict[str, Any]:
    """Fetch one Légifrance article and its legal-status metadata."""
    return _safe_call(legal_tools.get_article, id, date)


@server.tool(
    name="search_case_law",
    title="Rechercher une décision judiciaire",
    description=(
        "Recherche la jurisprudence judiciaire officielle dans Judilibre, avec "
        "filtres facultatifs de juridiction et de dates ISO. jurisdiction "
        "attend un code : cc (Cour de cassation), ca (Cour d'appel), tj "
        "(Tribunal judiciaire) ou tcom (Tribunal de commerce). Omettre ce "
        "paramètre ne recherche pas dans toutes les juridictions : Judilibre "
        "retombe alors sur la Cour de cassation. sort choisit le classement : "
        "relevance pour la pertinence (défaut), date pour les décisions les "
        "plus récentes d'abord."
    ),
    annotations=READ_ONLY,
)
def search_case_law(
    query: str,
    jurisdiction: Literal["cc", "ca", "tj", "tcom"] | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    limit: int = 10,
    sort: Literal["relevance", "date"] = "relevance",
) -> dict[str, Any]:
    """Search Judilibre decisions with optional filters and sort order."""
    return _safe_call(
        legal_tools.search_case_law,
        query,
        jurisdiction,
        date_start,
        date_end,
        limit,
        sort,
    )


@server.tool(
    name="get_decision",
    title="Lire une décision Judilibre",
    description=(
        "Récupère le texte intégral et les métadonnées officielles d'une décision "
        "à partir de son identifiant Judilibre."
    ),
    annotations=READ_ONLY,
)
def get_decision(id: str) -> dict[str, Any]:
    """Fetch one full Judilibre decision by identifier."""
    return _safe_call(legal_tools.get_decision, id)


@server.tool(
    name="get_section",
    title="Lire une section de code Légifrance",
    description=(
        "Lit le sous-arbre d'une section CODE LEGISCTA dans son texte LEGITEXT "
        "parent explicitement fourni, via l'API officielle. Conserve les articles, "
        "notes et bornes de version. date : AAAA-MM-JJ uniquement si une date "
        "précise est demandée ; sinon horloge du serveur. verified atteste la "
        "source, pas la vigueur : vérifier applicable_at_as_of_date. Refuse un "
        "sommaire ou contenu partiel ; ne couvre pas les sections LODA ou JORF. "
        "cid optionnel : CID de localisation établi à la source, distinct de "
        "l'ID de version demandé. Si fourni, la version retournée doit égaler "
        "exactement id ; un CID seul ne prouve ni cette identité ni la vigueur."
    ),
    annotations=READ_ONLY,
)
def get_section(id: str, text_id: str, date: str | None = None,
                cid: str | None = None) -> dict[str, Any]:
    """Lit une section CODE datée avec son parent explicite."""
    if cid is None:
        return _safe_call(legal_tools.get_section, id, text_id, date)
    return _safe_call(legal_tools.get_section, id, text_id, date, cid=cid)


@server.tool(
    name="get_text",
    title="Lire un texte consolidé Légifrance",
    description=(
        "Lit un texte consolidé LEGI par son LEGITEXT, via legiPart : articles, "
        "sections et notes présents dans la réponse API, hors documents liés. "
        "Ne couvre pas un texte JORFTEXT initial ni un sommaire de code. date : "
        "AAAA-MM-JJ seulement si une date précise est demandée ; sinon date du "
        "serveur. verified atteste la source et non la vigueur ; contrôler "
        "applicable_at_as_of_date. Refuse un contenu incomplet ou trop volumineux."
    ),
    annotations=READ_ONLY,
)
def get_text(id: str, date: str | None = None) -> dict[str, Any]:
    """Lit un texte LEGI consolidé, daté et sans troncature."""
    return _safe_call(legal_tools.get_text, id, date)


def _fetch_authorization_metadata() -> dict[str, Any]:
    import json
    import urllib.request

    url = f"{SETTINGS.oauth_issuer_base}/.well-known/oauth-authorization-server"
    with urllib.request.urlopen(url, timeout=5) as response:
        document = json.load(response)
    if not isinstance(document, dict) or document.get("issuer") != SETTINGS.oauth_issuer:
        raise ValueError("métadonnées d'émetteur inattendues")
    return document


LOOPBACK_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
LOOPBACK_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def transport_security_for(public_url: str) -> TransportSecuritySettings:
    """Protection contre le DNS rebinding, ouverte au nom public du service.

    Sans réglage explicite, le SDK suppose un serveur purement local et
    n'accepte que ``localhost`` : derrière Render ou un tunnel, chaque
    requête MCP échouerait en 421 « Invalid Host header ».
    """
    hosts = list(LOOPBACK_HOSTS)
    origins = list(LOOPBACK_ORIGINS)
    if public_url:
        parsed = urlsplit(public_url)
        hosts += [parsed.netloc, f"{parsed.hostname}:*"]
        origins.append(f"{parsed.scheme}://{parsed.netloc}")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


def build_http_app(**transport_options: Any):
    """Application HTTP complète : transport MCP du SDK derrière le garde HTTP."""
    transport_options.setdefault(
        "transport_security", transport_security_for(SETTINGS.public_url)
    )
    app = server.streamable_http_app(**transport_options)
    return HttpGuard(
        app,
        trusted_hops=SETTINGS.trusted_proxy_hops,
        ip_header=SETTINGS.client_ip_header,
        diagnostic=SETTINGS.ip_diagnostic,
    )


def check_issuer() -> None:
    """Compare l'émetteur configuré à celui que publie le serveur d'autorisation.

    OpenAI rapproche textuellement l'``issuer`` du document de découverte et la
    valeur annoncée par les métadonnées RFC 9728 du serveur MCP : une barre
    oblique finale de différence suffit à faire échouer le connecteur. Ce
    contrôle est un appel réseau explicite, jamais joué au démarrage, pour que
    le service ne dépende pas de la disponibilité de l'émetteur pour démarrer.
    """
    import json
    import urllib.request

    if not SETTINGS.auth_enabled:
        raise RuntimeConfigurationError(
            "--check-issuer exige MCP_AUTH_MODE=oauth."
        )
    url = f"{SETTINGS.oauth_issuer_base}/.well-known/oauth-authorization-server"
    with urllib.request.urlopen(url, timeout=10) as response:
        published = json.load(response).get("issuer")
    if published != SETTINGS.oauth_issuer:
        raise RuntimeConfigurationError(
            "MCP_OAUTH_ISSUER ne correspond pas au document de découverte : "
            f"configuré {SETTINGS.oauth_issuer!r}, publié {published!r}. "
            "Recopier le champ « issuer » à l'identique, barre finale comprise."
        )
    print(f"Émetteur conforme au document de découverte : {published}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serveur MCP PandecteMCP")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="stdio pour le plugin local ; streamable-http pour /mcp.",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Valide la configuration de production puis quitte.",
    )
    parser.add_argument(
        "--check-issuer",
        action="store_true",
        help=(
            "Interroge le document de découverte de l'émetteur et exige "
            "l'égalité stricte avec MCP_OAUTH_ISSUER, puis quitte."
        ),
    )
    args = parser.parse_args()
    try:
        SETTINGS.validate_public({**os.environ, **_OWNER_CREDENTIALS_SEEN})
        suppressed = _load_suppression_list()
    except RuntimeConfigurationError as exc:
        parser.error(str(exc))
    if args.check_issuer:
        try:
            check_issuer()
        except RuntimeConfigurationError as exc:
            parser.error(str(exc))
        return
    if args.check_config:
        print("Configuration MCP valide.")
        print(f"Retrait d'urgence Judilibre : {suppressed} identifiant(s) chargé(s).")
        return
    if args.transport == "streamable-http" and MCP_V2:
        import uvicorn

        uvicorn.run(
            build_http_app(max_request_body_size=SETTINGS.max_request_body_bytes),
            host=SETTINGS.host,
            port=SETTINGS.port,
            log_level=SETTINGS.log_level.lower(),
            # L'adresse cliente est résolue par HttpGuard, selon
            # MCP_TRUSTED_PROXY_HOPS ; uvicorn ne doit pas la réécrire.
            proxy_headers=False,
        )
    else:
        server.run(transport=args.transport)

if __name__ == "__main__":
    main()

"""Client Légifrance : authentification OAuth2 et appels API JSON."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from collections import OrderedDict

from .config import legifrance_environment
from .credentials import PisteCredentials, active_credentials
from .errors import LegifranceError
from .transport import http_post_json

#: Cache des jetons PISTE, commun à Légifrance et au mode OAuth de Judilibre :
#: un seul émetteur, un jeton par jeu d'identifiants. Indexé par l'empreinte
#: HMAC de l'identifiant ET du secret (``PisteCredentials.fingerprint``) : en
#: mode « clés personnelles », un appelant ne peut jamais recevoir le jeton
#: obtenu avec les identifiants d'un autre, même en connaissant son
#: ``client_id``. Garde son nom historique parce que le CLI l'importe.
_TOKEN_CACHE: OrderedDict[str, tuple[str, float]] = OrderedDict()
_TOKEN_CACHE_LOCK = threading.Lock()
#: Plafond du cache : borne la mémoire face à une rafale d'identifiants
#: distincts ; l'entrée la moins récemment utilisée est évincée.
MAX_CACHED_TOKENS = 512
#: Marge retirée à ``expires_in`` : un jeton est renouvelé avant son terme,
#: jamais présenté à la limite, où l'horloge de l'émetteur peut différer.
TOKEN_SAFETY_MARGIN_SECONDS = 60
#: Durée retenue quand l'émetteur omet ``expires_in`` — volontairement courte.
DEFAULT_TOKEN_LIFETIME_SECONDS = 600


def clear_token_cache() -> None:
    """Vide le cache de jetons de l'exécution courante."""
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE.clear()


def _cached_token(key: str) -> str | None:
    with _TOKEN_CACHE_LOCK:
        entry = _TOKEN_CACHE.get(key)
        if entry is None:
            return None
        token, expires_at = entry
        if time.monotonic() >= expires_at:
            del _TOKEN_CACHE[key]
            return None
        _TOKEN_CACHE.move_to_end(key)
        return token


def _remember_token(key: str, token: str, lifetime: object) -> None:
    try:
        seconds = int(lifetime)
    except (TypeError, ValueError):
        seconds = DEFAULT_TOKEN_LIFETIME_SECONDS
    ttl = seconds - TOKEN_SAFETY_MARGIN_SECONDS
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE.pop(key, None)
        if ttl <= 0:
            return
        _TOKEN_CACHE[key] = (token, time.monotonic() + ttl)
        while len(_TOKEN_CACHE) > MAX_CACHED_TOKENS:
            _TOKEN_CACHE.popitem(last=False)


def get_token(*, force_refresh: bool = False) -> str:
    """Récupère un jeton OAuth2 ``client_credentials`` PISTE.

    Les identifiants sont ceux de la requête courante, sinon ceux de
    l'environnement (voir ``credentials.active_credentials``). Le jeton est mis
    en cache, par jeu d'identifiants, jusqu'à ``expires_in`` moins une marge de
    sécurité : une opération n'en redemande pas un à chaque appel, et une
    indisponibilité passagère du serveur d'authentification ne casse plus une
    session dont le jeton est encore valide. ``force_refresh`` sert au seul
    renouvellement tenté après un ``401`` amont.
    """
    credentials = active_credentials()
    if credentials is not None and not force_refresh:
        cached = _cached_token(credentials.fingerprint)
        if cached:
            return cached
    if credentials is None:
        raise LegifranceError(
            "Identifiants PISTE absents : voie outillée indisponible.\n"
            "→ Bascule attendue : voie de repli web (gabarits web_search / "
            "web_fetch sur domaine officiel — references/gabarits-requetes.md, "
            "échelle de récupération à l'étape 2 du SKILL.md). Ne pas demander "
            "de clé à l'utilisateur : basculer. La règle de provenance "
            "s'applique à l'identique sur la voie web.\n"
            "Pour activer la voie outillée (gratuit, identifiants PISTE "
            "personnels) :\n"
            "  • sans installation : ajouter à l'assistant le connecteur "
            "PandecteMCP https://pandecte-mcp.onrender.com/mcp, puis s'y "
            "connecter avec ses identifiants PISTE ;\n"
            "  • en local : renseigner LEGIFRANCE_CLIENT_ID et "
            "LEGIFRANCE_CLIENT_SECRET dans skill/scripts/.env (modèle : "
            "skill/scripts/.env.example).\n"
            "Détail pas-à-pas : skill/scripts/README.md",
            exit_code=2,
        )
    return _request_token(credentials)


def _request_token(credentials: PisteCredentials) -> str:
    """Échange les identifiants contre un jeton, puis le met en cache."""
    payload = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scope": "openid",
        }
    ).encode("utf-8")
    try:
        data = http_post_json(
            legifrance_environment()["token"],
            payload,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
    except LegifranceError as exc:
        raise LegifranceError(
            f"Authentification PISTE échouée : {exc}",
            exit_code=3,
            http_status=exc.http_status,
            detail=exc.detail,
        ) from exc
    token = data.get("access_token")
    if not token:
        raise LegifranceError(
            "Réponse OAuth sans access_token : authentification PISTE à vérifier.",
            exit_code=3,
            detail=f"Réponse du serveur de jetons : {str(data)[:300]}",
        )
    _remember_token(credentials.fingerprint, token, data.get("expires_in"))
    return token


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def api_call(path: str, body: dict, token: str) -> dict:
    """Exécute un appel authentifié sur l'API Légifrance.

    Un ``401`` déclenche **un seul** renouvellement du jeton, puis une seconde
    tentative ; l'erreur suivante est propagée telle quelle. Pas de boucle :
    un jeton frais refusé n'est pas un jeton périmé, mais une configuration
    ou un abonnement à corriger.
    """
    url = legifrance_environment()["api"] + path
    payload = json.dumps(body).encode("utf-8")
    try:
        return http_post_json(url, payload, _headers(token))
    except LegifranceError as exc:
        if exc.http_status != 401:
            raise
    return http_post_json(url, payload, _headers(get_token(force_refresh=True)))

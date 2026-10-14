"""Pages web du serveur : « Mon compte » et « Clé personnelle ».

``/compte`` — mode « serveur partagé »
    Connexion par WorkOS AuthKit (e-mail et mot de passe, lien magique,
    Google, Microsoft…), puis génération ou révocation du jeton personnel
    ``pdt_…``. Le jeton est affiché une seule fois ; seule son empreinte est
    stockée. La connexion utilise le flux « authorization code » avec PKCE :
    aucune clé API WorkOS n'est nécessaire au serveur. Les jetons WorkOS reçus
    à l'échange du code sont aussitôt oubliés : seul l'identifiant de
    l'utilisateur (``user_…``, le même que le ``sub`` des jetons OAuth) sert.

``/cle`` — mode « clés personnelles »
    Page statique : la clé ``pk1.…`` est assemblée **dans le navigateur**. Les
    champs n'ont pas d'attribut ``name`` et la politique de sécurité du contenu
    interdit toute connexion sortante : les identifiants PISTE ne quittent
    pas la page.

Sécurité : cookies signés (HMAC-SHA256, clé dérivée du poivre), préfixe
``__Host-``, ``HttpOnly``, ``Secure`` et ``SameSite=Lax`` ; jeton anti-CSRF lié
à la session sur chaque formulaire et contrôle de l'origine ; CSP stricte avec
nonce ; aucune page mise en cache. Les journaux ne portent qu'une empreinte du
sujet, jamais d'adresse e-mail ni de jeton.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from html import escape
from typing import Any, Callable

import anyio
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp_server.access import hash_personal_token, new_personal_token
from mcp_server.quotas import QuotaPolicy
from mcp_server.runtime import RuntimeSettings
from mcp_server.store import Store

LOGGER = logging.getLogger("pandecte.mcp.account")

SESSION_COOKIE = "__Host-pandecte_session"
LOGIN_COOKIE = "__Host-pandecte_login"
SESSION_TTL_SECONDS = 30 * 60
LOGIN_TTL_SECONDS = 10 * 60
MAX_COOKIE_LENGTH = 2048
MAX_FORM_BYTES = 2048

USER_ID_RE = re.compile(r"^user_[A-Za-z0-9]{10,64}$")
_CODE_RE = re.compile(r"^[A-Za-z0-9._~-]{1,512}$")
_STATE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

REPOSITORY_URL = "https://github.com/TitouanSC/PandecteMCP"
TERMS_URL = f"{REPOSITORY_URL}/blob/main/docs/terms-of-use.md"
PRIVACY_URL = f"{REPOSITORY_URL}/blob/main/docs/privacy-policy.md"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _pseudonym(subject: str) -> str:
    return hashlib.sha256(subject.encode("utf-8")).hexdigest()[:12]


# -- Cookies signés ------------------------------------------------------------


class SignedCookies:
    """Valeurs signées et datées, liées à un usage (« session », « login »)."""

    def __init__(self, key: bytes, clock: Callable[[], float] = time.time) -> None:
        self._key = key
        self._clock = clock

    def _sign(self, body: str) -> str:
        return _b64url(hmac.new(self._key, body.encode("ascii"), hashlib.sha256).digest())

    def dump(self, purpose: str, payload: dict[str, Any], ttl: int) -> str:
        data = dict(payload, p=purpose, exp=int(self._clock()) + ttl)
        body = _b64url(json.dumps(data, separators=(",", ":")).encode("utf-8"))
        return f"{body}.{self._sign(body)}"

    def load(self, purpose: str, raw: str | None) -> dict[str, Any] | None:
        if not raw or len(raw) > MAX_COOKIE_LENGTH or raw.count(".") != 1:
            return None
        body, signature = raw.split(".")
        if not hmac.compare_digest(signature, self._sign(body)):
            return None
        try:
            data = json.loads(_b64url_decode(body))
        except ValueError:
            return None
        if (
            not isinstance(data, dict)
            or data.get("p") != purpose
            or not isinstance(data.get("exp"), int)
            or data["exp"] < self._clock()
        ):
            return None
        return data


# -- Échange du code WorkOS ------------------------------------------------------


class WorkOSError(Exception):
    """Échec de l'échange du code ; le message ne contient qu'une catégorie."""


def exchange_code(api_base: str, client_id: str, code: str, verifier: str) -> dict[str, str]:
    """Échange le code d'autorisation (PKCE) et rend ``{"id", "email"}``.

    Les jetons WorkOS de la réponse ne sont ni conservés ni journalisés.
    """
    body = json.dumps(
        {
            "client_id": client_id,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{api_base}/user_management/authenticate",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "PandecteMCP",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            document = json.load(response)
    except urllib.error.HTTPError as exc:
        raise WorkOSError(f"http_{exc.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise WorkOSError(type(exc).__name__) from None
    user = document.get("user") if isinstance(document, dict) else None
    if not isinstance(user, dict) or not USER_ID_RE.match(str(user.get("id", ""))):
        raise WorkOSError("invalid_user")
    email = user.get("email")
    return {"id": user["id"], "email": email[:254] if isinstance(email, str) else ""}


# -- Pages -------------------------------------------------------------------------


_STYLE = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:46rem;
margin:2rem auto;padding:0 1rem;line-height:1.55;color:#1d1d1f;background:#fff}
h1{font-size:1.6rem;margin-bottom:.2rem}h2{font-size:1.15rem;margin-top:2rem}
.sub{color:#555;margin-top:0}
.box{border:1px solid #ddd;border-radius:8px;padding:1rem 1.2rem;margin:1rem 0}
.warn{border-color:#d9a300;background:#fffbea}.ok{border-color:#2e7d32;background:#f1f8f1}
.err{border-color:#c62828;background:#fdf1f1}
code,textarea,input[type=text],input[type=password]{font-family:ui-monospace,Menlo,Consolas,monospace}
textarea,input[type=text],input[type=password]{width:100%;box-sizing:border-box;padding:.5rem;
border:1px solid #bbb;border-radius:6px;font-size:.95rem}
textarea{min-height:4.5rem;word-break:break-all}
label{display:block;margin:.8rem 0 .3rem;font-weight:600}
.check{font-weight:400;display:flex;gap:.5rem;align-items:flex-start}
.check input{margin-top:.35rem}
button,.button{display:inline-block;padding:.55rem 1rem;border-radius:6px;border:1px solid #1d4ed8;
background:#1d4ed8;color:#fff;font-size:1rem;cursor:pointer;text-decoration:none}
button.secondary{background:#fff;color:#1d4ed8}button.danger{background:#fff;color:#c62828;border-color:#c62828}
form.inline{display:inline-block;margin:0 .5rem .5rem 0}
pre{background:#f5f5f7;padding:.8rem;border-radius:6px;overflow-x:auto;white-space:pre-wrap;word-break:break-all}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid #eee;color:#666;font-size:.85rem}
nav a{margin-right:1rem}
"""


class AccountPages:
    """Gestionnaires HTTP des pages ; la base et les quotas sont lus à l'appel."""

    def __init__(
        self,
        *,
        settings: RuntimeSettings,
        store: Callable[[], Store | None],
        quotas: Callable[[], QuotaPolicy | None],
        pepper: Callable[[], bytes],
        exchange: Callable[[str, str, str, str], dict[str, str]] = exchange_code,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._store = store
        self._quotas = quotas
        self._pepper = pepper
        self._exchange = exchange
        self._clock = clock
        parsed = urllib.parse.urlsplit(settings.public_url)
        self._origin = f"{parsed.scheme}://{parsed.netloc}"

    # -- Outils ---------------------------------------------------------------

    def _cookies(self) -> SignedCookies:
        key = hmac.new(self._pepper(), b"pandecte-account-cookies-v1", hashlib.sha256).digest()
        return SignedCookies(key, self._clock)

    def _csrf(self, session: dict[str, Any]) -> str:
        key = hmac.new(self._pepper(), b"pandecte-account-csrf-v1", hashlib.sha256).digest()
        return hmac.new(key, str(session.get("n", "")).encode("ascii"), hashlib.sha256).hexdigest()

    def _verifier(self, state: str) -> str:
        """Vérificateur PKCE dérivé de l'état : il n'est jamais écrit dans un cookie."""
        key = hmac.new(self._pepper(), b"pandecte-account-pkce-v1", hashlib.sha256).digest()
        return _b64url(hmac.new(key, state.encode("ascii"), hashlib.sha256).digest())

    @property
    def redirect_uri(self) -> str:
        return f"{self._settings.public_url}/compte/callback"

    @property
    def mcp_url(self) -> str:
        return self._settings.resource_url

    def _session(self, request: Request) -> dict[str, Any] | None:
        session = self._cookies().load("session", request.cookies.get(SESSION_COOKIE))
        if session is None or not USER_ID_RE.match(str(session.get("sub", ""))):
            return None
        return session

    @staticmethod
    def _set_cookie(response: Response, name: str, value: str, max_age: int) -> None:
        response.set_cookie(
            name, value, max_age=max_age, path="/", secure=True, httponly=True, samesite="lax"
        )

    def _page(
        self, title: str, body: str, *, script: str = "", status: int = 200
    ) -> HTMLResponse:
        nonce = secrets.token_urlsafe(16)
        script_tag = f'<script nonce="{nonce}">{script}</script>' if script else ""
        nav = '<nav><a href="/compte">Mon compte</a><a href="/cle">Clé personnelle</a></nav>'
        if not self._settings.account_enabled:
            nav = '<nav><a href="/cle">Clé personnelle</a></nav>'
        html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>{escape(title)} · PandecteMCP</title>
<style nonce="{nonce}">{_STYLE}</style></head>
<body>{nav}
{body}
<footer>
<p><strong>PandecteMCP</strong> est un projet indépendant et open source (CC BY-SA 4.0),
sans lien avec l'auteur du projet d'origine, avec une personnalité ou une institution,
ni avec l'État, la DILA ou la Cour de cassation. Il ne remplace pas un avocat.
Les données proviennent de Légifrance et de la base Open Data de la Cour de cassation
(Judilibre), consultées via PISTE dans le respect de leurs conditions générales.</p>
<p><a href="{TERMS_URL}">Conditions d'utilisation</a> ·
<a href="{PRIVACY_URL}">Confidentialité</a> ·
<a href="{REPOSITORY_URL}">Code source</a></p>
</footer>{script_tag}</body></html>"""
        response = HTMLResponse(html, status_code=status)
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            f"style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
            "img-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def _error(self, message: str, status: int) -> HTMLResponse:
        body = (
            "<h1>Mon compte</h1>"
            f'<div class="box err"><p>{escape(message)}</p></div>'
            '<p><a href="/compte">Revenir à la page du compte</a></p>'
        )
        return self._page("Erreur", body, status=status)

    async def _post_fields(
        self, request: Request
    ) -> tuple[dict[str, Any] | None, dict[str, str] | Response]:
        """Session et champs d'un formulaire, ou la réponse de refus."""
        origin = request.headers.get("origin")
        if origin is not None and origin != self._origin:
            LOGGER.warning("account_refused reason=origin")
            return None, self._error("Requête refusée (origine inattendue).", 403)
        if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
            LOGGER.warning("account_refused reason=fetch_site")
            return None, self._error("Requête refusée (origine inattendue).", 403)
        session = self._session(request)
        if session is None:
            return None, self._error("Session expirée : reconnectez-vous.", 401)
        body = await request.body()
        if len(body) > MAX_FORM_BYTES:
            return None, self._error("Formulaire trop volumineux.", 413)
        try:
            parsed = urllib.parse.parse_qs(body.decode("ascii"), strict_parsing=False)
        except (UnicodeDecodeError, ValueError):
            return None, self._error("Formulaire invalide.", 400)
        fields = {key: values[0] for key, values in parsed.items() if values}
        if not hmac.compare_digest(fields.get("csrf", ""), self._csrf(session)):
            LOGGER.warning("account_refused reason=csrf")
            return None, self._error("Formulaire expiré : rechargez la page.", 403)
        return session, fields

    # -- Routes ---------------------------------------------------------------

    def register(self, server: Any) -> None:
        routes = [("/cle", ["GET"], self.personal_key)]
        if self._settings.account_enabled:
            routes += [
                ("/compte", ["GET"], self.account),
                ("/compte/connexion", ["GET"], self.login),
                ("/compte/callback", ["GET"], self.callback),
                ("/compte/jeton", ["POST"], self.create_token),
                ("/compte/revoquer", ["POST"], self.revoke_token),
                ("/compte/deconnexion", ["POST"], self.logout),
            ]
        for path, methods, handler in routes:
            server.custom_route(path, methods=methods, include_in_schema=False)(handler)

    async def account(self, request: Request) -> Response:
        session = self._session(request)
        if session is None:
            return self._page("Mon compte", self._anonymous_body())
        store, quotas = self._store(), self._quotas()
        subject = session["sub"]
        has_token = await anyio.to_thread.run_sync(store.has_token, subject)
        used, limit = await anyio.to_thread.run_sync(quotas.usage_today, subject)
        return self._page(
            "Mon compte", self._account_body(session, has_token=has_token, used=used, limit=limit)
        )

    async def login(self, request: Request) -> Response:
        state = secrets.token_urlsafe(24)
        verifier = self._verifier(state)
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        query = urllib.parse.urlencode(
            {
                "client_id": self._settings.workos_client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "provider": "authkit",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        response = RedirectResponse(
            f"{self._settings.workos_api_base}/user_management/authorize?{query}", status_code=302
        )
        response.headers["Cache-Control"] = "no-store"
        self._set_cookie(
            response,
            LOGIN_COOKIE,
            self._cookies().dump("login", {"s": state}, LOGIN_TTL_SECONDS),
            LOGIN_TTL_SECONDS,
        )
        return response

    async def callback(self, request: Request) -> Response:
        params = request.query_params
        if params.get("error"):
            LOGGER.info("account_login outcome=denied")
            return self._error("Connexion annulée ou refusée. Vous pouvez réessayer.", 400)
        login = self._cookies().load("login", request.cookies.get(LOGIN_COOKIE))
        state, code = params.get("state", ""), params.get("code", "")
        if (
            login is None
            or not _STATE_RE.match(state)
            or not hmac.compare_digest(state, str(login.get("s", "")))
            or not _CODE_RE.match(code)
        ):
            LOGGER.warning("account_login outcome=invalid_state")
            return self._error(
                "La tentative de connexion a expiré ou n'est pas valide. Recommencez.", 400
            )
        try:
            user = await anyio.to_thread.run_sync(
                self._exchange,
                self._settings.workos_api_base,
                self._settings.workos_client_id,
                code,
                self._verifier(state),
            )
        except WorkOSError as exc:
            LOGGER.warning("account_login outcome=exchange_failed reason=%s", exc)
            return self._error(
                "Le service de connexion n'a pas pu confirmer votre identité. Réessayez.", 502
            )
        session = {"sub": user["id"], "email": user["email"], "n": secrets.token_urlsafe(16)}
        response = RedirectResponse("/compte", status_code=303)
        self._set_cookie(
            response,
            SESSION_COOKIE,
            self._cookies().dump("session", session, SESSION_TTL_SECONDS),
            SESSION_TTL_SECONDS,
        )
        response.delete_cookie(LOGIN_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        LOGGER.info("account_login outcome=success principal=%s", _pseudonym(user["id"]))
        return response

    async def create_token(self, request: Request) -> Response:
        session, fields = await self._post_fields(request)
        if session is None:
            return fields  # type: ignore[return-value]
        token = new_personal_token()
        digest = hash_personal_token(token, self._pepper())
        await anyio.to_thread.run_sync(self._store().replace_token, session["sub"], digest)
        LOGGER.info("account_token outcome=created principal=%s", _pseudonym(session["sub"]))
        return self._page("Votre jeton", self._token_body(token))

    async def revoke_token(self, request: Request) -> Response:
        session, fields = await self._post_fields(request)
        if session is None:
            return fields  # type: ignore[return-value]
        await anyio.to_thread.run_sync(self._store().revoke, session["sub"])
        LOGGER.info("account_token outcome=revoked principal=%s", _pseudonym(session["sub"]))
        return RedirectResponse("/compte", status_code=303)

    async def logout(self, request: Request) -> Response:
        session, fields = await self._post_fields(request)
        if session is None:
            return fields  # type: ignore[return-value]
        response = RedirectResponse("/compte", status_code=303)
        response.delete_cookie(
            SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax"
        )
        return response

    async def personal_key(self, request: Request) -> Response:
        if not self._settings.personal_keys_enabled:
            return self._page(
                "Clé personnelle",
                "<h1>Clé personnelle</h1><p>Le mode « clés personnelles » est désactivé "
                "sur ce serveur.</p>",
                status=404,
            )
        return self._page("Clé personnelle", self._personal_key_body(), script=_PERSONAL_KEY_JS)

    # -- Contenus -------------------------------------------------------------

    def _anonymous_body(self) -> str:
        settings = self._settings
        return f"""<h1>Mon compte</h1>
<p class="sub">Serveur partagé PandecteMCP : recherche dans Légifrance et Judilibre pour votre IA.</p>
<div class="box">
<p><strong>claude.ai, ChatGPT et les clients compatibles OAuth</strong> n'ont pas besoin de
cette page : ajoutez simplement l'adresse <code>{escape(self.mcp_url)}</code> comme connecteur,
la connexion se fait dans une fenêtre de votre IA.</p>
<p><strong>Claude Code, Cursor, VS Code, Gemini CLI, Le Chat…</strong> : connectez-vous ici pour
obtenir un <em>jeton personnel</em> à coller dans la configuration de votre client.</p>
</div>
<p><a class="button" href="/compte/connexion">Se connecter ou créer un compte</a></p>
<p>E-mail et mot de passe, lien de connexion par e-mail, ou un compte Google, Microsoft,
Apple, GitHub… selon les options proposées.</p>
<h2>Limites du serveur partagé</h2>
<ul>
<li>{settings.user_calls_per_minute} appels par minute et {settings.user_calls_per_day} appels par
jour par personne (remise à zéro à 00:00 UTC) ;</li>
<li>une limite globale protège le quota PISTE commun : le service peut être saturé certains jours.</li>
</ul>
<p>Pour ne dépendre d'aucune limite partagée, utilisez vos propres identifiants PISTE
(gratuits) : voir <a href="/cle">Clé personnelle</a>.</p>"""

    def _account_body(
        self, session: dict[str, Any], *, has_token: bool, used: int, limit: int
    ) -> str:
        csrf = self._csrf(session)
        who = escape(session.get("email") or "compte WorkOS")
        if has_token:
            status = (
                "<p>Vous avez <strong>un jeton personnel actif</strong>. Il n'est plus affichable : "
                "si vous l'avez perdu, générez-en un nouveau (l'ancien cessera aussitôt de "
                "fonctionner).</p>"
            )
            generate_label = "Remplacer mon jeton"
            revoke = (
                '<form class="inline" method="post" action="/compte/revoquer">'
                f'<input type="hidden" name="csrf" value="{csrf}">'
                '<button class="danger" type="submit">Révoquer mon jeton</button></form>'
            )
        else:
            status = "<p>Vous n'avez <strong>aucun jeton personnel</strong> actif.</p>"
            generate_label = "Générer mon jeton"
            revoke = ""
        return f"""<h1>Mon compte</h1>
<p class="sub">Connecté : <strong>{who}</strong></p>
<div class="box">
<p>Utilisation aujourd'hui : <strong>{used} / {limit}</strong> appels
(remise à zéro à 00:00 UTC). Ce compteur est commun à toutes vos connexions
(OAuth et jeton personnel).</p>
</div>
<h2>Jeton personnel</h2>
{status}
<form class="inline" method="post" action="/compte/jeton">
<input type="hidden" name="csrf" value="{csrf}">
<button type="submit">{generate_label}</button></form>
{revoke}
<p>Le jeton donne accès au serveur partagé <em>en votre nom</em> : ne le publiez pas,
ne le partagez pas. Seule son empreinte est conservée par le serveur.</p>
<h2>Session</h2>
<form class="inline" method="post" action="/compte/deconnexion">
<input type="hidden" name="csrf" value="{csrf}">
<button class="secondary" type="submit">Se déconnecter</button></form>"""

    def _token_body(self, token: str) -> str:
        url = escape(self.mcp_url)
        return f"""<h1>Votre jeton personnel</h1>
<div class="box ok">
<p><strong>Copiez-le maintenant : il ne sera plus jamais affiché.</strong>
Tout jeton précédent est révoqué.</p>
<textarea readonly aria-label="Jeton personnel">{token}</textarea>
</div>
<h2>Claude Code</h2>
<pre>claude mcp add --transport http pandecte {url} \\
  --header "Authorization: Bearer {token}"</pre>
<h2>Autres clients (Cursor, VS Code, Gemini CLI…)</h2>
<p>Déclarez un serveur MCP « HTTP » à l'adresse <code>{url}</code> avec l'en-tête :</p>
<pre>Authorization: Bearer {token}</pre>
<p>Le format exact du fichier de configuration dépend du client ; voir la documentation du
projet.</p>
<p><a href="/compte">Revenir à mon compte</a></p>"""

    def _personal_key_body(self) -> str:
        url = escape(self.mcp_url)
        return f"""<h1>Clé personnelle</h1>
<p class="sub">Utiliser PandecteMCP avec <strong>vos propres identifiants PISTE</strong> :
aucune limite partagée, votre propre quota PISTE.</p>
<div class="box warn">
<p><strong>À lire avant de continuer.</strong> Les conditions générales d'utilisation de
l'API Légifrance (§ III.3) et de l'API Judilibre (§ XI) indiquent que vos clés sont
réservées à votre application et ne doivent pas être divulguées à un tiers.</p>
<p>Avec ce mode, votre client d'IA transmet vos identifiants à ce serveur à chaque requête.
Le serveur s'en sert uniquement le temps de l'appel, en votre nom, comme intermédiaire
technique : il ne les stocke pas, ne les journalise pas et ne les renvoie jamais. Vous
restez seul responsable de l'usage de vos clés auprès de PISTE (voir les
<a href="{TERMS_URL}">conditions d'utilisation</a>, clause de mandat).</p>
<p>Pour ne transmettre vos clés à personne, <strong>hébergez votre propre serveur</strong>
ou utilisez le mode local : voir le <a href="{REPOSITORY_URL}">dépôt du projet</a>.</p>
</div>
<h2>Assembler la clé</h2>
<p>La clé est assemblée <strong>dans votre navigateur</strong> : cette page n'envoie rien au
serveur (sa politique de sécurité interdit toute connexion sortante). Vos identifiants se
trouvent sur <a href="https://piste.gouv.fr/">piste.gouv.fr</a>, rubrique Applications.</p>
<label for="client-id">Client ID</label>
<input type="text" id="client-id" autocomplete="off" spellcheck="false">
<label for="client-secret">Client secret</label>
<input type="password" id="client-secret" autocomplete="off" spellcheck="false">
<label for="key-id">KeyId (facultatif)</label>
<input type="text" id="key-id" autocomplete="off" spellcheck="false">
<label class="check"><input type="checkbox" id="accept">
<span>J'ai lu l'avertissement ci-dessus et j'accepte que mes identifiants soient transmis à ce
serveur, à chaque requête, pour être utilisés en mon nom.</span></label>
<p><button type="button" id="assemble">Assembler ma clé</button></p>
<div id="message" role="status"></div>
<div id="result" hidden>
<div class="box ok">
<p><strong>Votre clé personnelle</strong> (à garder secrète, comme vos identifiants) :</p>
<textarea id="key" readonly aria-label="Clé personnelle"></textarea>
</div>
<h2>Claude Code</h2>
<pre id="claude-code"></pre>
<h2>Autres clients (Cursor, VS Code, Gemini CLI…)</h2>
<p>Serveur MCP « HTTP » à l'adresse <code>{url}</code>, avec l'en-tête :</p>
<pre id="header"></pre>
<p>claude.ai et ChatGPT ne permettent pas encore de transmettre une telle clé :
utilisez-y le serveur partagé (connexion OAuth).</p>
</div>
<span id="mcp-url" data-url="{url}" hidden></span>"""


#: Même algorithme que ``mcp_server.access.encode_personal_key`` ; la valeur de
#: référence (« identifiant », « secret-123 ») → ``pk1.aWRlbnRpZmlhbnQ.c2VjcmV0LTEyMw``
#: est vérifiée par les tests.
_PERSONAL_KEY_JS = r"""
(function () {
  "use strict";
  var VALUE = /^[\x21-\x7e]{4,256}$/;
  function b64url(value) {
    return btoa(value).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function encodeKey(clientId, secret, keyId) {
    var parts = [clientId, secret];
    if (keyId) { parts.push(keyId); }
    return "pk1." + parts.map(b64url).join(".");
  }
  window.pandecteEncodeKey = encodeKey;
  var button = document.getElementById("assemble");
  if (!button) { return; }
  button.addEventListener("click", function () {
    var message = document.getElementById("message");
    var result = document.getElementById("result");
    var clientId = document.getElementById("client-id").value.trim();
    var secret = document.getElementById("client-secret").value.trim();
    var keyId = document.getElementById("key-id").value.trim();
    result.hidden = true;
    message.className = "";
    message.textContent = "";
    function fail(text) { message.className = "box err"; message.textContent = text; }
    if (!document.getElementById("accept").checked) {
      return fail("Cochez la case pour confirmer avoir lu l'avertissement.");
    }
    if (!VALUE.test(clientId) || !VALUE.test(secret) || (keyId && !VALUE.test(keyId))) {
      return fail("Identifiants invalides : 4 à 256 caractères ASCII visibles, sans espace.");
    }
    var key = encodeKey(clientId, secret, keyId);
    var url = document.getElementById("mcp-url").getAttribute("data-url");
    document.getElementById("key").value = key;
    document.getElementById("claude-code").textContent =
      "claude mcp add --transport http pandecte " + url +
      " \\\n  --header \"Authorization: Bearer " + key + "\"";
    document.getElementById("header").textContent = "Authorization: Bearer " + key;
    result.hidden = false;
  });
})();
"""

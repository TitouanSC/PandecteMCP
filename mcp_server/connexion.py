"""Page « Connexion PISTE » : l'utilisateur confie ses identifiants à son IA.

Étape interactive du serveur d'autorisation (``mcp_server.piste_oauth``).
Le client MCP (claude.ai, ChatGPT…) y envoie l'utilisateur ; celui-ci saisit
son Client ID et son Client Secret PISTE ; le serveur les vérifie auprès de
PISTE, les scelle dans le code d'autorisation, puis renvoie vers le client.
Rien n'est stocké, rien n'est journalisé hormis l'issue.

Protections :

* **origine** — le formulaire n'est accepté que s'il vient de cette page
  (``Origin`` et ``Sec-Fetch-Site``) : un autre site ne peut pas le soumettre ;
* **destinataire visible** — le nom du client et le domaine de retour sont
  affichés, avec un avertissement si ce domaine n'est pas celui d'un client
  connu : c'est la parade à l'hameçonnage par un client enregistré à cette
  fin (n'importe qui peut en enregistrer un) ;
* **demande scellée** — le formulaire porte la demande validée par /authorize,
  infalsifiable et valable 15 minutes ;
* **page** — CSP stricte à nonce, aucun cache, aucun cadre.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from html import escape
from typing import Any, Callable

import anyio
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from pandecte.credentials import PisteCredentials
from pandecte.errors import LegifranceError

from mcp_server.pages import PISTE_URL, TERMS_URL, render_page
from mcp_server.piste_oauth import LOGIN_PATH, PisteAuthProvider

LOGGER = logging.getLogger("pandecte.mcp.connexion")

MAX_FORM_BYTES = 16 * 1024
#: Valeur d'un identifiant PISTE : ASCII visible, sans espace.
_CREDENTIAL_RE = re.compile(r"^[\x21-\x7e]{4,256}$")
#: Domaines de retour des clients MCP connus. Les autres restent admis, mais
#: la page avertit l'utilisateur avant qu'il ne confie ses clés.
KNOWN_REDIRECT_HOSTS = frozenset({
    "claude.ai",
    "claude.com",
    "chatgpt.com",
    "chat.openai.com",
    "localhost",
    "127.0.0.1",
    "[::1]",
})


class PisteRejected(Exception):
    """PISTE refuse ces identifiants."""


class PisteUnavailable(Exception):
    """PISTE ne répond pas : rien ne peut être conclu sur les identifiants."""


def verify_with_piste(credentials: PisteCredentials) -> None:
    """Obtient un jeton PISTE avec ces identifiants, ou lève une exception."""
    from pandecte.credentials import use_credentials
    from pandecte.legifrance import get_token

    try:
        with use_credentials(credentials):
            get_token(force_refresh=True)
    except LegifranceError as exc:
        if exc.http_status in (400, 401, 403):
            raise PisteRejected() from exc
        raise PisteUnavailable() from exc


def _redirect_parts(redirect_uri: str) -> tuple[str, str]:
    """(domaine affiché, source CSP ``form-action``) de l'adresse de retour."""
    parsed = urllib.parse.urlsplit(redirect_uri)
    if parsed.scheme in ("http", "https"):
        return parsed.hostname or "", f"{parsed.scheme}://{parsed.netloc}"
    # Schéma d'application (cursor://, vscode://…) : autorisé par son schéma.
    return f"{parsed.scheme}://", f"{parsed.scheme}:"


class ConnexionPage:
    def __init__(
        self,
        provider: PisteAuthProvider,
        *,
        public_url: str,
        verify: Callable[[PisteCredentials], None] = verify_with_piste,
    ) -> None:
        self._provider = provider
        self._verify = verify
        parsed = urllib.parse.urlsplit(public_url)
        self._origin = f"{parsed.scheme}://{parsed.netloc}"

    def register(self, server: Any) -> None:
        server.custom_route(LOGIN_PATH, methods=["GET", "POST"], include_in_schema=False)(
            self.handle
        )

    async def handle(self, request: Request) -> Response:
        if request.method == "POST":
            return await self._submit(request)
        request_data = self._provider.read_request(request.query_params.get("demande", ""))
        if request_data is None:
            return self._expired()
        return self._form(request.query_params["demande"], request_data)

    # -- Affichage -----------------------------------------------------------

    def _expired(self, status: int = 400) -> Response:
        body = (
            "<h1>Connexion PISTE</h1>"
            '<div class="box err"><p>Cette demande de connexion est expirée ou invalide. '
            "Relancez la connexion depuis votre assistant (bouton « Se connecter » "
            "du connecteur PandecteMCP).</p></div>"
        )
        return render_page("Connexion", body, status=status, narrow=True)

    def _form(
        self, sealed: str, request_data: dict[str, Any], *, error: str = "", status: int = 200
    ) -> Response:
        host, form_target = _redirect_parts(request_data["r"])
        client_name = str(request_data.get("n") or "Application sans nom")[:80]
        known = host in KNOWN_REDIRECT_HOSTS
        warning = "" if known else (
            '<div class="box warn"><p><strong>Attention :</strong> cette application '
            f"renvoie vers <code>{escape(host)}</code>, qui n'est pas un assistant connu. "
            "Ne continuez que si vous êtes à l'origine de cette connexion : sinon, "
            "quelqu'un pourrait tenter d'obtenir vos identifiants PISTE.</p></div>"
        )
        error_box = f'<div class="box err"><p>{escape(error)}</p></div>' if error else ""
        body = f"""<h1>Connexion PISTE</h1>
<p class="sub">Autoriser <strong>{escape(client_name)}</strong>
(<code>{escape(host)}</code>) à consulter Légifrance et Judilibre
avec <strong>vos propres</strong> identifiants PISTE.</p>
{warning}{error_box}
<form class="card" method="post" action="{LOGIN_PATH}" autocomplete="off">
<input type="hidden" name="demande" value="{escape(sealed)}">
<label for="cid">Client ID</label>
<input type="text" id="cid" name="client_id" required spellcheck="false" autocapitalize="off">
<label for="csec">Client Secret</label>
<input type="password" id="csec" name="client_secret" required spellcheck="false">
<p class="hint">Sur <a href="{PISTE_URL}" target="_blank" rel="noopener">piste.gouv.fr</a> :
Applications → votre application (environnement Production) → bloc OAuth.
L'application doit être abonnée aux API Légifrance et JUDILIBRE.</p>
<label class="check"><input type="checkbox" name="consentement" value="oui" required>
<span>Je confie mes identifiants PISTE à PandecteMCP pour qu'il interroge Légifrance
et Judilibre <strong>en mon nom</strong>, dans le respect des
<a href="{TERMS_URL}" target="_blank" rel="noopener">conditions d'utilisation</a>
et des CGU de PISTE, que j'ai acceptées.</span></label>
<div class="actions">
<button type="submit" name="action" value="autoriser">Autoriser</button>
<button type="submit" name="action" value="annuler" class="secondary" formnovalidate>Annuler</button>
</div>
</form>
<div class="box"><p><strong>Ce que deviennent vos identifiants.</strong>
Ils sont vérifiés auprès de PISTE, puis chiffrés dans le jeton que garde votre assistant.
Le serveur PandecteMCP ne les enregistre nulle part et ne les journalise jamais ; seul
lui sait déchiffrer ce jeton, le temps de chaque consultation. Pour retirer l'accès :
déconnectez le connecteur, ou régénérez votre Client Secret sur PISTE.</p></div>"""
        return render_page(
            "Connexion PISTE", body, status=status, form_targets=(form_target,), narrow=True
        )

    # -- Envoi ---------------------------------------------------------------

    async def _submit(self, request: Request) -> Response:
        origin = request.headers.get("origin")
        if (origin is not None and origin != self._origin) or request.headers.get(
            "sec-fetch-site", "same-origin"
        ) not in ("same-origin", "none"):
            LOGGER.warning("connexion_refused reason=origin")
            return render_page(
                "Connexion",
                '<h1>Connexion PISTE</h1><div class="box err"><p>Requête refusée '
                "(origine inattendue).</p></div>",
                status=403,
                narrow=True,
            )
        body = await request.body()
        if len(body) > MAX_FORM_BYTES:
            return self._expired(413)
        try:
            parsed = urllib.parse.parse_qs(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return self._expired()
        fields = {key: values[0] for key, values in parsed.items() if values}
        sealed = fields.get("demande", "")
        request_data = self._provider.read_request(sealed)
        if request_data is None:
            return self._expired()

        if fields.get("action") == "annuler":
            LOGGER.info("connexion outcome=cancelled")
            return RedirectResponse(self._provider.denial_url(request_data), status_code=303)

        client_id = fields.get("client_id", "").strip()
        client_secret = fields.get("client_secret", "").strip()
        if fields.get("consentement") != "oui":
            return self._form(sealed, request_data, status=400,
                              error="Cochez la case d'accord pour continuer.")
        if not (_CREDENTIAL_RE.match(client_id) and _CREDENTIAL_RE.match(client_secret)):
            return self._form(sealed, request_data, status=400,
                              error="Client ID ou Client Secret invalide (format).")
        credentials = PisteCredentials(client_id, client_secret)
        try:
            await anyio.to_thread.run_sync(self._verify, credentials)
        except PisteRejected:
            LOGGER.info("connexion outcome=rejected")
            return self._form(
                sealed, request_data, status=400,
                error="PISTE refuse ces identifiants. Vérifiez le Client ID et le Client "
                "Secret de votre application en environnement Production.",
            )
        except PisteUnavailable:
            LOGGER.warning("connexion outcome=piste_unavailable")
            return self._form(
                sealed, request_data, status=503,
                error="PISTE ne répond pas pour le moment. Réessayez dans quelques minutes.",
            )
        LOGGER.info("connexion outcome=success")
        return RedirectResponse(
            self._provider.issue_code(request_data, credentials), status_code=303
        )

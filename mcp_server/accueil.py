"""Page d'accueil ``/`` : un seul lien à partager, une marche à suivre par IA.

Le connecteur MCP est le dénominateur commun : chaque assistant l'ajoute à sa
façon. La page donne, pour chacun, les clics à faire et, quand l'assistant en
propose, un lien d'installation directe (Cursor, VS Code). Elle ne contient
aucun formulaire ; son seul script copie l'adresse du connecteur.
"""

from __future__ import annotations

import base64
import json
from html import escape
from typing import Any
from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import Response

from mcp_server.pages import PISTE_URL, PRIVACY_URL, REPOSITORY_URL, render_page
from mcp_server.statique import image_theme

PATH = "/"
SERVER_NAME = "pandecte"
MARKETPLACE = "TitouanSC/PandecteMCP"
PISTE_GUIDE_URL = f"{REPOSITORY_URL}/blob/main/skill/scripts/README.md"

#: Assistants dont la connexion a été qualifiée de bout en bout. Les autres
#: sont présentés d'après leur documentation, avec la mention « non testé ».
TESTED = frozenset({"claude", "chatgpt", "claude-code"})


def cursor_install_link(mcp_url: str) -> str:
    config = json.dumps({"url": mcp_url}, separators=(",", ":"))
    encoded = base64.b64encode(config.encode()).decode()
    return f"cursor://anysphere.cursor-deeplink/mcp/install?name={SERVER_NAME}&config={quote(encoded)}"


def vscode_install_link(mcp_url: str) -> str:
    config = json.dumps({"name": SERVER_NAME, "type": "http", "url": mcp_url}, separators=(",", ":"))
    return "vscode:mcp/install?" + quote(config, safe="")


class HomePage:
    def __init__(self, *, mcp_url: str, personal_keys_enabled: bool = True) -> None:
        self._mcp_url = mcp_url
        self._personal_keys = personal_keys_enabled

    def register(self, server: Any) -> None:
        server.custom_route(PATH, methods=["GET"], include_in_schema=False)(self.handle)

    async def handle(self, _request: Request) -> Response:
        return render_page("Recherche en droit français", self._body(), script=COPY_JS)

    def _section(self, key: str, title: str, body: str) -> str:
        tag = (
            '<span class="tag ok">testé</span>' if key in TESTED
            else '<span class="tag">non testé</span>'
        )
        return (
            f'<details id="{key}"><summary><span class="titre">{title}</span> {tag}</summary>'
            f"{body}</details>"
        )

    def _body(self) -> str:
        url = escape(self._mcp_url)
        cursor = escape(cursor_install_link(self._mcp_url))
        vscode = escape(vscode_install_link(self._mcp_url))
        autres = (
            f'<p>Ajoutez un serveur MCP « HTTP » (Streamable HTTP) à l\'adresse <code>{url}</code>, '
            "avec l'authentification <strong>OAuth</strong> : la page « Connexion PISTE » "
            "s'ouvre à la première utilisation."
        )
        if self._personal_keys:
            autres += (
                ' Si votre client n\'accepte qu\'un en-tête fixe, utilisez une '
                '<a href="/cle">clé personnelle</a>.'
            )
        autres += "</p>"
        sections = "\n".join((
            self._section("claude", "Claude — claude.ai, application, mobile", f"""
<ol>
<li><strong>Ajouter le plugin</strong> : <em>Personnaliser</em> → <em>Plugins</em> →
<em>Ajouter</em> → <em>Ajouter une marketplace</em>, saisir
<code>{MARKETPLACE}</code>, puis ajouter le plugin <strong>PandecteMCP</strong>.</li>
<li><strong>Connecter le connecteur (obligatoire)</strong> : onglet
<em>Connecteurs</em> du plugin → <em>Connecter</em>, puis vos identifiants sur la page
« Connexion PISTE ».</li>
</ol>
<p class="hint">Le plugin apporte la méthode de recherche et le connecteur ; il suit votre
compte (bureau, mobile, Cowork, Claude Code). Sans plugin : <em>Paramètres</em> →
<em>Connecteurs</em> → <em>Ajouter un connecteur personnalisé</em>, URL <code>{url}</code>.</p>"""),
            self._section("chatgpt", "ChatGPT", f"""
<ol>
<li><em>Paramètres</em> → <em>Applications et connecteurs</em> → <em>Paramètres avancés</em> :
activer le <strong>mode développeur</strong> (selon votre offre).</li>
<li><em>Créer</em> : URL <code>{url}</code>, authentification <strong>OAuth</strong>.</li>
<li>ChatGPT ouvre la page « Connexion PISTE » : saisissez vos identifiants.</li>
</ol>"""),
            self._section("lechat", "Le Chat — Mistral", f"""
<ol>
<li><em>Connecteurs</em> → <em>Ajouter un connecteur</em> → onglet
<em>Connecteur MCP personnalisé</em> (réservé à l'administrateur du compte ; sur les offres
gratuite et Pro, c'est vous).</li>
<li>Nom <code>PandecteMCP</code> (sans espace), URL <code>{url}</code>, puis
<em>Connecter</em> : la page « Connexion PISTE » s'ouvre.</li>
</ol>"""),
            self._section("claude-code", "Claude Code", f"""
<pre>/plugin marketplace add {MARKETPLACE}
/plugin install pandecte@pandecte</pre>
<p>Puis <code>/mcp</code> → <code>pandecte</code> → <em>Authenticate</em>. Connecteur seul :</p>
<pre>claude mcp add --transport http {SERVER_NAME} {url}</pre>"""),
            self._section("cursor", "Cursor", f"""
<p><a class="button" href="{cursor}">Ajouter à Cursor</a></p>
<p class="hint">Le lien ouvre Cursor et ajoute le serveur <code>{SERVER_NAME}</code> ; Cursor
demande ensuite la connexion. À défaut : <em>Settings</em> → <em>MCP</em> →
<em>Add new MCP server</em>, URL <code>{url}</code>.</p>"""),
            self._section("vscode", "VS Code", f"""
<p><a class="button" href="{vscode}">Installer dans VS Code</a></p>
<p class="hint">Le lien ouvre VS Code et ajoute le serveur ; la connexion se fait au premier
démarrage du serveur. À défaut : palette de commandes → <em>MCP: Add Server</em> →
<em>HTTP</em>, URL <code>{url}</code>.</p>"""),
            self._section("gemini", "Gemini CLI", f"""
<pre>gemini mcp add --transport http {SERVER_NAME} {url}</pre>
<p class="hint">Puis <code>/mcp auth {SERVER_NAME}</code> dans Gemini CLI pour ouvrir la page
« Connexion PISTE ».</p>"""),
            self._section("autres", "Autres assistants compatibles MCP", autres),
        ))
        logo = image_theme("logo", "La Justice, glaive et balance", 152, "hero-logo")
        return f"""<div class="hero"><div>
<h1>La recherche en droit français, sourcée, dans votre IA.</h1>
<p class="sub">Recherche fondée sur les sources officielles — textes de
Légifrance, décisions de la Cour de cassation — pour votre assistant d'IA, sans rien
installer.</p></div>
{logo}</div>

<h2><span class="num">1</span>Vos identifiants PISTE (gratuits)</h2>
<p>Chacun se connecte avec <strong>ses propres</strong> identifiants. Créez un compte sur
<a href="{PISTE_URL}">piste.gouv.fr</a>, acceptez les CGU des API Légifrance et JUDILIBRE en
production, créez une application qui les coche, puis relevez son <strong>Client ID</strong>
et son <strong>Client Secret</strong> (bloc OAuth). <a href="{PISTE_GUIDE_URL}">Pas à pas
détaillé</a>.</p>
<p class="hint">Le serveur ne stocke pas vos identifiants : ils voyagent chiffrés dans le
jeton que garde votre assistant (<a href="{PRIVACY_URL}">confidentialité</a>).</p>

<h2><span class="num">2</span>L'adresse du connecteur</h2>
<div class="card"><div class="url"><code id="mcp-url">{url}</code>
<button type="button" id="copy" class="secondary">Copier</button></div>
<p id="copied" role="status" class="hint"></p></div>

<h2><span class="num">3</span>Votre assistant</h2>
<p>Choisissez le vôtre ; chaque marche à suivre tient en quelques clics.</p>
<div class="assistants">
{sections}
</div>

<h2>Ensuite</h2>
<p>Posez votre question juridique. L'assistant lit d'abord la méthode de recherche, puis
cite des textes et décisions récupérés en direct, avec leur version en vigueur. Le service
gratuit se met en veille la nuit : la première requête peut prendre 30 secondes.</p>"""


COPY_JS = r"""
(function () {
  "use strict";
  var button = document.getElementById("copy");
  if (!button || !navigator.clipboard) { if (button) { button.hidden = true; } return; }
  button.addEventListener("click", function () {
    var status = document.getElementById("copied");
    navigator.clipboard.writeText(document.getElementById("mcp-url").textContent).then(
      function () { status.textContent = "Adresse copiée."; },
      function () { status.textContent = "Copie impossible : sélectionnez l'adresse."; }
    );
  });
})();
"""

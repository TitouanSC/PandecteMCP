"""Page « Clé personnelle » : la clé ``pk1`` des clients sans OAuth.

claude.ai et ChatGPT se connectent par la page « Connexion PISTE »
(``mcp_server.connexion``). Les clients qui acceptent un en-tête fixe
(Claude Code, Cursor, VS Code, Gemini CLI…) peuvent aussi recevoir
``Authorization: Bearer pk1.…`` : les identifiants PISTE de l'utilisateur,
encodés en base64url. La clé est assemblée **dans le navigateur** : la page
n'a ni formulaire ni champ nommé, et sa CSP interdit toute connexion sortante.
"""

from __future__ import annotations

from html import escape
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from mcp_server.pages import PISTE_URL, REPOSITORY_URL, TERMS_URL, render_page

PATH = "/cle"


class PersonalKeyPage:
    def __init__(self, *, mcp_url: str) -> None:
        self._mcp_url = mcp_url

    def register(self, server: Any) -> None:
        server.custom_route(PATH, methods=["GET"], include_in_schema=False)(self.handle)

    async def handle(self, _request: Request) -> Response:
        return render_page("Clé personnelle", self._body(), script=PERSONAL_KEY_JS)

    def _body(self) -> str:
        url = escape(self._mcp_url)
        return f"""<h1>Clé personnelle</h1>
<p class="sub">Pour les clients qui acceptent un en-tête HTTP fixe : Claude Code, Cursor,
VS Code, Gemini CLI… Avec claude.ai ou ChatGPT, ajoutez simplement le connecteur
<code>{url}</code> : la connexion vous demandera vos identifiants PISTE.</p>
<div class="box warn">
<p><strong>À lire avant de continuer.</strong> Les conditions générales d'utilisation de
l'API Légifrance (§ III.3) et de l'API Judilibre (§ XI) indiquent que vos clés sont
réservées à votre application et ne doivent pas être divulguées à un tiers.</p>
<p>Avec cette clé, votre client d'IA transmet vos identifiants à ce serveur à chaque requête.
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
trouvent sur <a href="{PISTE_URL}">piste.gouv.fr</a>, rubrique Applications.</p>
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
</div>
<span id="mcp-url" data-url="{url}" hidden></span>"""


#: Même algorithme que ``mcp_server.access.encode_personal_key`` ; la valeur de
#: référence (« identifiant », « secret-123 ») → ``pk1.aWRlbnRpZmlhbnQ.c2VjcmV0LTEyMw``
#: est vérifiée par les tests.
PERSONAL_KEY_JS = r"""
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

"""Gabarit commun des pages HTML du serveur : style, pied de page, en-têtes.

Chaque page reçoit un nonce neuf ; la CSP n'autorise que ce nonce pour les
styles et scripts, n'admet aucune ressource externe ni aucun envoi de
formulaire hors du serveur, et interdit l'affichage dans un cadre.
"""

from __future__ import annotations

import secrets
from html import escape

from starlette.responses import HTMLResponse

REPOSITORY_URL = "https://github.com/TitouanSC/PandecteMCP"
TERMS_URL = f"{REPOSITORY_URL}/blob/main/docs/terms-of-use.md"
PRIVACY_URL = f"{REPOSITORY_URL}/blob/main/docs/privacy-policy.md"
PISTE_URL = "https://piste.gouv.fr"

STYLE = """
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
.hint{color:#555;font-size:.9rem;margin:.2rem 0 0}
.check{font-weight:400;display:flex;gap:.5rem;align-items:flex-start}
.check input{margin-top:.35rem}
.actions{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:1.2rem}
button,.button{display:inline-block;padding:.55rem 1rem;border-radius:6px;border:1px solid #1d4ed8;
background:#1d4ed8;color:#fff;font-size:1rem;cursor:pointer;text-decoration:none}
button.secondary{background:#fff;color:#1d4ed8}button.danger{background:#fff;color:#c62828;border-color:#c62828}
form.inline{display:inline-block;margin:0 .5rem .5rem 0}
pre{background:#f5f5f7;padding:.8rem;border-radius:6px;overflow-x:auto;white-space:pre-wrap;word-break:break-all}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid #eee;color:#666;font-size:.85rem}
nav a{margin-right:1rem}
"""

FOOTER = f"""<footer>
<p><strong>PandecteMCP</strong> est un projet indépendant et open source (CC BY-SA 4.0),
sans lien avec l'auteur du projet d'origine, avec une personnalité ou une institution,
ni avec l'État, la DILA ou la Cour de cassation. Il ne remplace pas un avocat.
Les données proviennent de Légifrance et de la base Open Data de la Cour de cassation
(Judilibre), consultées via PISTE dans le respect de leurs conditions générales.</p>
<p><a href="{TERMS_URL}">Conditions d'utilisation</a> ·
<a href="{PRIVACY_URL}">Confidentialité</a> ·
<a href="{REPOSITORY_URL}">Code source</a></p>
</footer>"""


def render_page(
    title: str,
    body: str,
    *,
    script: str = "",
    status: int = 200,
    nav: str = "",
    form_targets: tuple[str, ...] = (),
) -> HTMLResponse:
    """Page complète. ``form_targets`` : sources CSP ajoutées à ``form-action``,
    nécessaires quand l'envoi du formulaire redirige vers un autre site
    (Chrome applique ``form-action`` jusqu'au bout des redirections)."""
    nonce = secrets.token_urlsafe(16)
    script_tag = f'<script nonce="{nonce}">{script}</script>' if script else ""
    form_action = " ".join(("'self'", *form_targets))
    html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="same-origin">
<title>{escape(title)} · PandecteMCP</title>
<style nonce="{nonce}">{STYLE}</style></head>
<body>{nav}
{body}
{FOOTER}{script_tag}</body></html>"""
    response = HTMLResponse(html, status_code=status)
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        f"style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
        "img-src 'self'; "
        f"form-action {form_action}; "
        "frame-ancestors 'none'; base-uri 'none'"
    )
    response.headers["Cache-Control"] = "no-store"
    # « same-origin » et non « no-referrer » : avec ce dernier, Safari et
    # Chrome envoient « Origin: null » sur les formulaires, que le contrôle
    # d'origine refuserait. Aucun référent ne part vers un autre site.
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

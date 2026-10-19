"""Gabarit commun des pages HTML du serveur : style, pied de page, en-têtes.

Le style reprend le preset shadcn/ui « sera » (base taupe, accent orange) :
mêmes variables de couleur et même allure de composants, écrits en CSS pur
pour garder la CSP stricte. Chaque page reçoit un nonce neuf ; la CSP n'autorise que ce nonce pour les
styles et scripts, n'admet aucune ressource externe ni aucun envoi de
formulaire hors du serveur, et interdit l'affichage dans un cadre.
"""

from __future__ import annotations

import secrets
from html import escape

from starlette.responses import HTMLResponse

from mcp_server.statique import FONT_FACES, ICON_URL, image_theme

REPOSITORY_URL = "https://github.com/TitouanSC/PandecteMCP"
TERMS_URL = f"{REPOSITORY_URL}/blob/main/docs/terms-of-use.md"
PRIVACY_URL = f"{REPOSITORY_URL}/blob/main/docs/privacy-policy.md"
PISTE_URL = "https://piste.gouv.fr"

STYLE = """
:root{color-scheme:light dark;
--font-sans:"Stack Sans Text",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--font-heading:"Stack Sans Notch","Stack Sans Text",system-ui,sans-serif;
--font-mono:ui-monospace,Menlo,Consolas,monospace;
--brand:#DD3B18;
--background:oklch(1 0 0);--foreground:oklch(0.147 0.004 49.3);
--card:oklch(1 0 0);--card-foreground:oklch(0.147 0.004 49.3);
--primary:#C2340F;--primary-foreground:#FFFFFF;--link:#B5300D;
--secondary:oklch(0.96 0.002 17.2);--secondary-foreground:oklch(0.214 0.009 43.1);
--muted:oklch(0.96 0.002 17.2);--muted-foreground:oklch(0.5 0.021 43.1);
--destructive:oklch(0.577 0.245 27.325);--warning:oklch(0.666 0.179 58.318);
--success:oklch(0.527 0.154 150.069);
--border:oklch(0.922 0.005 34.3);--input:oklch(0.82 0.008 34.3);
--ring:oklch(0.714 0.014 41.2)}
@media (prefers-color-scheme:dark){:root{
--background:#0C0200;--foreground:oklch(0.986 0.002 67.8);
--card:#1A110E;--card-foreground:oklch(0.986 0.002 67.8);
--link:#F28B6A;
--secondary:oklch(0.268 0.011 36.5);--secondary-foreground:oklch(0.986 0.002 67.8);
--muted:#231815;--muted-foreground:#C2C2C2;
--destructive:oklch(0.704 0.191 22.216);--warning:oklch(0.828 0.189 84.429);
--success:oklch(0.723 0.219 149.579);
--border:oklch(1 0 0 / 10%);--input:oklch(1 0 0 / 25%);
--ring:oklch(0.547 0.021 43.1)}}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--background);color:var(--foreground);
font-family:var(--font-sans);font-size:1rem;line-height:1.6;
-webkit-font-smoothing:antialiased}
.page{max-width:46rem;margin:0 auto;padding:0 1.25rem 3rem}
.narrow{max-width:30rem}
header.site{display:flex;align-items:center;justify-content:space-between;gap:1rem;
padding:1.25rem 0;margin-bottom:2rem;border-bottom:1px solid var(--border)}
.brand{display:inline-flex;align-items:center;gap:.6rem;color:var(--foreground);
text-decoration:none;font-family:var(--font-heading);font-weight:700;
letter-spacing:-.02em;font-size:1.25rem}
.brand picture,.brand img{width:2rem;height:2rem;display:block}
.hero{display:flex;align-items:center;gap:2.5rem}.hero > div{flex:1}
.hero-logo,.hero-logo img{width:9.5rem;height:9.5rem;display:block;flex:none}
@media (max-width:40rem){.hero-logo{display:none}}
header.site nav{display:flex;gap:1.25rem}
header.site nav a{color:var(--muted-foreground);text-decoration:none;font-size:.7rem;
font-weight:600;letter-spacing:.1em;text-transform:uppercase}
header.site nav a:hover{color:var(--foreground)}
h1,h2,h3{font-family:var(--font-heading);line-height:1.2;margin:0}
h1{font-size:2.25rem;font-weight:700;letter-spacing:-.02em;margin-bottom:.75rem}
h2{font-family:var(--font-sans);font-size:.8rem;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
margin:2.75rem 0 1rem;display:flex;align-items:center;gap:.75rem}
h2 .num{display:inline-flex;align-items:center;justify-content:center;width:1.75rem;
height:1.75rem;background:var(--brand);color:#fff;font-size:.75rem;letter-spacing:0}
p{margin:0 0 1rem}
.sub{color:var(--muted-foreground);font-size:1.05rem;margin-bottom:1.5rem}
.hint{color:var(--muted-foreground);font-size:.875rem}
a{color:var(--link);text-underline-offset:3px}
a:hover{text-decoration-thickness:2px}
code{font-family:var(--font-mono);font-size:.875em;background:var(--muted);
padding:.1rem .35rem;word-break:break-all}
pre{font-family:var(--font-mono);font-size:.85rem;background:var(--muted);
padding:.9rem 1rem;margin:0 0 1rem;overflow-x:auto;white-space:pre-wrap;word-break:break-all}
ol,ul{padding-left:1.25rem;margin:0 0 1rem}li{margin:.35rem 0}
.card{background:var(--card);color:var(--card-foreground);padding:2rem;margin:1.25rem 0;
box-shadow:0 1px 2px rgb(0 0 0 / 5%);outline:1px solid color-mix(in oklch,var(--foreground) 6%,transparent)}
.card > :last-child{margin-bottom:0}
.card > label:first-child,.card > input[type=hidden] + label{margin-top:0}
.box{position:relative;background:var(--card);border:1px solid var(--border);
padding:.85rem 1rem .85rem 1.25rem;margin:1rem 0;font-size:.9rem}
.box::before{content:"";position:absolute;inset:-1px auto -1px -1px;width:3px;
background:var(--foreground)}
.box > :last-child{margin-bottom:0}
.box.warn::before{background:var(--warning)}.box.ok::before{background:var(--success)}
.box.err{color:var(--destructive)}.box.err::before{background:var(--destructive)}
.url{display:flex;align-items:center;gap:.75rem;flex-wrap:wrap}
.url code{font-size:.95rem;background:none;padding:0;flex:1 1 16rem}
label{display:block;margin:1.4rem 0 .25rem;font-size:.7rem;font-weight:600;
letter-spacing:.08em;text-transform:uppercase}
input[type=text],input[type=password],textarea{display:block;width:100%;height:2.5rem;
padding:.25rem 0;border:0;border-bottom:1px solid var(--input);border-radius:0;
background:transparent;color:inherit;font-family:var(--font-mono);font-size:1rem;
outline:none;transition:border-color .15s}
textarea{height:auto;min-height:5rem;word-break:break-all;resize:vertical}
input:focus-visible,textarea:focus-visible{border-bottom-color:var(--brand);
box-shadow:0 1px 0 var(--brand)}
label.check{display:flex;gap:.75rem;align-items:flex-start;margin-top:1.5rem;
font-size:.875rem;font-weight:400;letter-spacing:0;text-transform:none}
.check input{width:1.1rem;height:1.1rem;margin:.2rem 0 0;flex:none;accent-color:var(--primary)}
.actions{display:flex;gap:.75rem;flex-wrap:wrap;align-items:center;margin:1.75rem 0 0}
button,.button{display:inline-flex;align-items:center;justify-content:center;height:2.5rem;
padding:0 1.5rem;border:1px solid transparent;border-radius:0;background:var(--primary);
color:var(--primary-foreground);font-family:var(--font-sans);font-size:.75rem;font-weight:600;
letter-spacing:.1em;text-transform:uppercase;text-decoration:none;white-space:nowrap;
cursor:pointer;transition:background-color .15s,color .15s}
button:hover,.button:hover{background:color-mix(in oklch,var(--primary) 85%,black)}
button:active,.button:active{transform:translateY(1px)}
button:focus-visible,.button:focus-visible,summary:focus-visible,a:focus-visible{
outline:2px solid var(--ring);outline-offset:2px}
button.secondary,.button.secondary{background:transparent;color:var(--foreground);
border-color:var(--border)}
button.secondary:hover,.button.secondary:hover{background:var(--muted)}
button.danger{background:transparent;color:var(--destructive);border-color:var(--destructive)}
form.inline{display:inline-block;margin:0 .5rem .5rem 0}
.assistants{border-top:1px solid var(--border)}
details{border-bottom:1px solid var(--border)}
summary{display:flex;align-items:center;gap:.75rem;padding:1rem 0;cursor:pointer;
font-size:.95rem;font-weight:600;list-style:none}
summary::-webkit-details-marker{display:none}
summary::after{content:"+";margin-left:auto;font-weight:400;font-size:1.25rem;
line-height:1;color:var(--muted-foreground)}
details[open] summary::after{content:"\\2212"}
summary:hover .titre{text-decoration:underline;text-underline-offset:3px}
details > :not(summary){font-size:.925rem}
details > :last-child{margin-bottom:1.25rem}
.tag{font-size:.625rem;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
color:var(--muted-foreground)}
.tag.ok{color:var(--success)}
footer{margin-top:4rem;padding-top:1.5rem;border-top:1px solid var(--border);
color:var(--muted-foreground);font-size:.8rem;line-height:1.6}
footer a{color:inherit}
"""

DEFAULT_NAV = f'''<nav><a href="/">Installer</a><a href="{REPOSITORY_URL}">Code source</a></nav>'''

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
    narrow: bool = False,
) -> HTMLResponse:
    """Page complète. ``form_targets`` : sources CSP ajoutées à ``form-action``,
    nécessaires quand l'envoi du formulaire redirige vers un autre site
    (Chrome applique ``form-action`` jusqu'au bout des redirections).
    ``narrow`` : colonne étroite, pour les pages de formulaire."""
    nonce = secrets.token_urlsafe(16)
    nav = nav or DEFAULT_NAV
    script_tag = f'<script nonce="{nonce}">{script}</script>' if script else ""
    form_action = " ".join(("'self'", *form_targets))
    html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="same-origin">
<title>{escape(title)} · PandecteMCP</title>
<link rel="icon" type="image/svg+xml" href="{ICON_URL}">
<style nonce="{nonce}">{FONT_FACES}{STYLE}</style></head>
<body><div class="page{' narrow' if narrow else ''}">
<header class="site"><a class="brand" href="/">{image_theme("embleme", "", 32)}PandecteMCP</a>{nav}</header>
<main>
{body}
</main>
{FOOTER}</div>{script_tag}</body></html>"""
    response = HTMLResponse(html, status_code=status)
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        f"style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
        "img-src 'self'; font-src 'self'; "
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

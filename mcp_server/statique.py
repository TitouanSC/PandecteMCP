"""Fichiers statiques des pages : logo, icône et polices, servis par le serveur.

Rien n'est chargé d'un autre site : la CSP des pages n'admet que ``'self'``
pour les images et les polices. La liste des fichiers est fermée — aucun
chemin venu de la requête n'atteint le disque.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "/static"
FONTS = Path(__file__).resolve().parent / "static" / "fonts"

#: Nom public → (fichier, type MIME). Le logo vient de ``assets/``, source
#: unique des visuels du projet (plugin OpenAI compris).
FILES: dict[str, tuple[Path, str]] = {
    "icone.svg": (ROOT / "assets" / "icone.svg", "image/svg+xml"),
    "logo.svg": (ROOT / "assets" / "logo.svg", "image/svg+xml"),
}
FILES.update({
    police.name: (police, "font/woff2") for police in sorted(FONTS.glob("*.woff2"))
})

ICON_URL = f"{PREFIX}/icone.svg"

#: Polices de la charte (Figma « PandecteMCP ») : Stack Sans Notch pour les
#: titres, Stack Sans Text pour le texte. Licence SIL OFL 1.1 (static/fonts/OFL.txt),
#: sous-ensemble « latin » de Google Fonts, qui couvre le français (œ, €, «»).
FONT_FACES = "".join(
    f"@font-face{{font-family:'{famille}';src:url({PREFIX}/{fichier}) format('woff2');"
    "font-weight:200 700;font-style:normal;font-display:swap}"
    for famille, fichier in (
        ("Stack Sans Notch", "stack-sans-notch.woff2"),
        ("Stack Sans Text", "stack-sans-text.woff2"),
    )
)


class StaticFiles:
    def register(self, server: Any) -> None:
        server.custom_route(f"{PREFIX}/{{nom}}", methods=["GET"], include_in_schema=False)(
            self.handle
        )

    async def handle(self, request: Request) -> Response:
        entree = FILES.get(request.path_params.get("nom", ""))
        if entree is None or not entree[0].is_file():
            return PlainTextResponse("Not found", status_code=404)
        chemin, media_type = entree
        response = Response(chemin.read_bytes(), media_type=media_type)
        response.headers["Cache-Control"] = "public, max-age=86400"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Un SVG ouvert directement reste un document : il n'exécute rien.
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        return response

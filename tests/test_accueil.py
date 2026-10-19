#!/usr/bin/env python3
"""Page d'accueil : une marche à suivre par IA, liens d'installation exacts."""
from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))

from mcp_server.accueil import (  # noqa: E402
    TESTED,
    HomePage,
    cursor_install_link,
    vscode_install_link,
)
from mcp_server.statique import ICON_URL, StaticFiles  # noqa: E402

MCP_URL = "https://pandecte.example.org/mcp"


class HomePageTests(unittest.TestCase):
    def page(self, **kwargs):
        return asyncio.run(HomePage(mcp_url=MCP_URL, **kwargs).handle(None))

    def test_page_lists_every_assistant_with_its_test_status(self):
        text = self.page().body.decode()
        for key in ("claude", "chatgpt", "lechat", "claude-code", "cursor", "vscode", "gemini", "autres"):
            with self.subTest(assistant=key):
                bloc = re.search(rf'<details id="{key}">(.*?)</details>', text, re.S)
                self.assertIsNotNone(bloc)
                attendu = "testé</span>" if key in TESTED else "non testé</span>"
                self.assertIn(attendu, bloc.group(1))

    def test_page_is_static_and_locked_down(self):
        page = self.page()
        text = page.body.decode()
        self.assertEqual(200, page.status_code)
        self.assertNotIn("<form", text)
        self.assertNotIn("<input", text)
        csp = page.headers["content-security-policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertNotIn("connect-src", csp)
        self.assertIn(MCP_URL, text)
        self.assertIn("TitouanSC/PandecteMCP", text)
        self.assertIn("Connecter le connecteur (obligatoire)", text)

    def test_personal_key_link_follows_the_setting(self):
        self.assertIn('href="/cle"', self.page().body.decode())
        self.assertNotIn('href="/cle"', self.page(personal_keys_enabled=False).body.decode())

    def test_cursor_link_carries_the_connector_url(self):
        lien = urlsplit(cursor_install_link(MCP_URL))
        self.assertEqual("cursor", lien.scheme)
        query = parse_qs(lien.query)
        self.assertEqual(["pandecte"], query["name"])
        self.assertEqual({"url": MCP_URL}, json.loads(base64.b64decode(query["config"][0])))

    def test_vscode_link_carries_the_connector_url(self):
        lien = vscode_install_link(MCP_URL)
        self.assertTrue(lien.startswith("vscode:mcp/install?"))
        config = json.loads(unquote(lien.split("?", 1)[1]))
        self.assertEqual({"name": "pandecte", "type": "http", "url": MCP_URL}, config)


class StaticFilesTests(unittest.TestCase):
    """Logo et polices viennent du serveur lui-même, jamais d'un autre site."""

    def get(self, nom):
        from types import SimpleNamespace

        return asyncio.run(StaticFiles().handle(SimpleNamespace(path_params={"nom": nom})))

    def test_every_image_of_the_pages_is_served(self):
        page = asyncio.run(HomePage(mcp_url=MCP_URL).handle(None)).body.decode()
        noms = set(re.findall(r'(?:src|srcset)="/static/([\w.-]+)\?v=[0-9a-f]{12}"', page))
        self.assertTrue({"logo.svg", "logo-sombre.svg"} <= noms)
        for nom in noms:
            with self.subTest(image=nom):
                self.assertEqual(200, self.get(nom).status_code)

    def test_icon_is_served_and_sandboxed(self):
        reponse = self.get("icone.svg")
        self.assertEqual(200, reponse.status_code)
        self.assertEqual("image/svg+xml", reponse.media_type)
        self.assertIn(b"<svg", reponse.body)
        self.assertIn("sandbox", reponse.headers["content-security-policy"])

    def test_declared_fonts_are_served_with_their_licence(self):
        import re as _re

        from mcp_server.statique import FONT_FACES, FONTS

        fichiers = _re.findall(r"/static/([\w.-]+\.woff2)\?v=[0-9a-f]{12}", FONT_FACES)
        self.assertEqual(2, len(fichiers))
        for nom in fichiers:
            with self.subTest(police=nom):
                reponse = self.get(nom)
                self.assertEqual(200, reponse.status_code)
                self.assertEqual("font/woff2", reponse.media_type)
                self.assertEqual(b"wOF2", reponse.body[:4])
        self.assertIn("SIL Open Font License", (FONTS / "OFL.txt").read_text(encoding="utf-8"))

    def test_image_address_changes_with_its_content(self):
        import tempfile
        from unittest import mock

        from mcp_server import statique

        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / "logo.svg"
            chemin.write_bytes(b"<svg>v1</svg>")
            with mock.patch.dict(statique.FILES, {"logo.svg": (chemin, "image/svg+xml")}):
                avant = statique.url("logo.svg")
                chemin.write_bytes(b"<svg>v2</svg>")
                self.assertNotEqual(avant, statique.url("logo.svg"))

    def test_unknown_or_traversing_names_are_refused(self):
        for nom in ("absent.svg", "../server.py", "..%2Fserver.py", ""):
            with self.subTest(nom=nom):
                self.assertEqual(404, self.get(nom).status_code)

    def test_pages_only_load_local_images_and_fonts(self):
        page = asyncio.run(HomePage(mcp_url=MCP_URL).handle(None))
        csp = page.headers["content-security-policy"]
        self.assertIn("img-src 'self'", csp)
        self.assertIn("font-src 'self'", csp)
        texte = page.body.decode()
        self.assertIn(f'href="{ICON_URL}"', texte)
        self.assertNotRegex(texte, r'(src|href)="https?://[^"]*\.(svg|png|woff2?|css)"')


if __name__ == "__main__":
    unittest.main()

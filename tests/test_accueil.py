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


if __name__ == "__main__":
    unittest.main()

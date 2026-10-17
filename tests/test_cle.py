#!/usr/bin/env python3
"""Page « Clé personnelle » : rien ne part du navigateur, encodage identique."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))

from mcp_server.access import encode_personal_key  # noqa: E402
from mcp_server.cle import PERSONAL_KEY_JS, PersonalKeyPage  # noqa: E402
from pandecte.credentials import PisteCredentials  # noqa: E402

MCP_URL = "https://pandecte.example.org/mcp"


class PersonalKeyPageTests(unittest.TestCase):
    def page(self):
        return asyncio.run(PersonalKeyPage(mcp_url=MCP_URL).handle(None))

    def test_page_never_sends_the_credentials(self):
        page = self.page()
        text = page.body.decode()
        self.assertEqual(200, page.status_code)
        csp = page.headers["content-security-policy"]
        self.assertIn("default-src 'none'", csp)  # donc aucune connexion sortante
        self.assertNotIn("connect-src", csp)
        # Aucun champ nommé, aucun formulaire : rien ne peut partir même sans JS.
        self.assertNotRegex(text, r"<input[^>]*\bname=")
        self.assertNotIn("<form", text)
        nonce = re.search(r"script-src 'nonce-([^']+)'", csp).group(1)
        self.assertIn(f'<script nonce="{nonce}">', text)
        self.assertIn("III.3", text)
        self.assertIn("mandat", text)
        self.assertIn(MCP_URL, text)

    @unittest.skipUnless(shutil.which("node"), "Node.js absent")
    def test_browser_encoding_matches_the_server(self):
        script = (
            "global.window = {}; global.document = {getElementById: () => null};"
            "global.btoa = s => Buffer.from(s, 'latin1').toString('base64');"
            + PERSONAL_KEY_JS
            + "console.log(JSON.stringify(["
            "window.pandecteEncodeKey('identifiant', 'secret-123'),"
            "window.pandecteEncodeKey('0f8c2a54-1b7e', 'c9e1~b7a2?55d0', 'cle-judilibre-01')]));"
        )
        sortie = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        first, second = json.loads(sortie.stdout)
        self.assertEqual("pk1.aWRlbnRpZmlhbnQ.c2VjcmV0LTEyMw", first)
        self.assertEqual(
            encode_personal_key(
                PisteCredentials("0f8c2a54-1b7e", "c9e1~b7a2?55d0", "cle-judilibre-01")
            ),
            second,
        )


if __name__ == "__main__":
    unittest.main()

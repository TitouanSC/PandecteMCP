#!/usr/bin/env python3
"""Outil get_method : la méthode arrive avec le connecteur, sans rien installer."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "declinaisons"))

import generer  # noqa: E402
from mcp_server import methode  # noqa: E402
from mcp_server import server as mcp_app  # noqa: E402


class MethodContentTests(unittest.TestCase):
    def test_default_is_the_generated_condensed_method(self):
        result = methode.read_method(None, "0.1.0")
        self.assertEqual("methode", result["id"])
        self.assertEqual(generer.methode_serveur(), result["text"])
        for marque in ("**P1 —", "**P7 —", "Règle de provenance", "### Étape 7 —"):
            self.assertIn(marque, result["text"])

    def test_generated_method_is_up_to_date(self):
        self.assertEqual(
            generer.methode_serveur(), methode.METHODE.read_text(encoding="utf-8"),
            "lancer python declinaisons/generer.py",
        )

    def test_every_section_is_served_from_the_full_skill(self):
        for section, chemin in methode.SECTIONS.items():
            with self.subTest(section=section):
                result = methode.read_method(section, "0.1.0")
                self.assertEqual(
                    (ROOT / "skill" / chemin).read_text(encoding="utf-8"), result["text"]
                )

    def test_sections_match_the_published_schema(self):
        from typing import get_args

        self.assertEqual(set(methode.SECTIONS), set(get_args(methode.Section)))

    def test_unknown_or_path_like_sections_are_refused(self):
        for section in ("inconnue", "../server.py", "references/modules.md", "/etc/passwd"):
            with self.subTest(section=section), self.assertRaises(ValueError):
                methode.read_method(section, "0.1.0")

    def test_method_is_marked_as_instructions_not_legal_source(self):
        result = methode.read_method(None, "0.1.0")
        self.assertIn("ne vaut pas source de droit", result["metadata"]["usage"])


class ServerIntegrationTests(unittest.TestCase):
    def test_instructions_send_the_assistant_to_get_method_first(self):
        texte = mcp_app.INSTRUCTIONS
        self.assertTrue(texte.startswith("Avant toute analyse juridique, lisez la méthode avec get_method."))
        self.assertLessEqual(len(texte), mcp_app.INSTRUCTIONS_MAX_CHARS)

    def test_tool_needs_no_piste_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch.object(mcp_app.legal_tools, "get_article", side_effect=AssertionError):
            result = mcp_app.get_method("modes-erreur")
        self.assertEqual("modes-erreur", result["id"])

    def test_condensed_method_lists_every_tool_of_the_catalog(self):
        from mcp_server.catalog import TOOL_NAMES

        texte = methode.read_method(None, "0.1.0")["text"]
        for outil in TOOL_NAMES:
            with self.subTest(outil=outil):
                self.assertIn(f"`{outil}`", texte)


if __name__ == "__main__":
    unittest.main()

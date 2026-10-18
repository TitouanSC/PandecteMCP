#!/usr/bin/env python3
"""Déclinaisons par plateforme : générées, à jour, autonomes et fidèles au noyau."""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "declinaisons"))

import generer  # noqa: E402

PLATEFORMES = generer.plateformes()
VERSION = generer.version()


class GenerationTests(unittest.TestCase):
    def test_four_platforms_are_declared(self):
        self.assertEqual(
            {"gemini", "grok", "manus", "vibe"}, {p.cle for p in PLATEFORMES}
        )

    def test_published_folders_are_up_to_date(self):
        # Un dossier modifié à la main, ou un noyau modifié sans régénération,
        # ferait diverger les paquets : c'est ce que l'unification empêche.
        for plateforme in PLATEFORMES:
            with self.subTest(plateforme=plateforme.cle):
                self.assertEqual(
                    [], generer.ecarts(plateforme, generer.contenu(plateforme, VERSION)),
                    "lancer python declinaisons/generer.py",
                )

    def test_every_template_marker_is_filled(self):
        for plateforme in PLATEFORMES:
            for chemin, texte in generer.contenu(plateforme, VERSION).items():
                with self.subTest(plateforme=plateforme.cle, fichier=chemin):
                    self.assertNotRegex(texte, r"\{\{[A-Z_]+\}\}")


class PackageContentTests(unittest.TestCase):
    def setUp(self):
        self.paquets = {p.cle: generer.contenu(p, VERSION) for p in PLATEFORMES}

    def test_frontmatter_names_the_skill_and_its_version(self):
        for cle, fichiers in self.paquets.items():
            with self.subTest(plateforme=cle):
                entete = fichiers["SKILL.md"].split("---", 2)[1]
                self.assertIn("name: pandecte-recherche", entete)
                self.assertIn(f"version: {VERSION}-{cle}", entete)
                self.assertIn("license: CC-BY-SA-4.0", entete)

    def test_method_core_is_complete(self):
        for cle, fichiers in self.paquets.items():
            texte = fichiers["SKILL.md"]
            with self.subTest(plateforme=cle):
                for principe in ("P1", "P2", "P3", "P4", "P5", "P6", "P7"):
                    self.assertRegex(texte, rf"\*\*{principe} —")
                for module in ("PÉNAL", "ACTE-ADMIN", "PA-PJ", "FOND", "CONTENTIEUX", "DOC-AUDIT"):
                    self.assertIn(module, texte)
                for etape in range(8):
                    self.assertIn(f"### Étape {etape} —", texte)
                self.assertIn("Source non\nconfirmée — abstention sur ce point.", texte)

    def test_connector_tools_match_the_server_catalog(self):
        sys.path.insert(0, str(ROOT))
        from mcp_server.catalog import TOOL_NAMES

        for cle, fichiers in self.paquets.items():
            with self.subTest(plateforme=cle):
                for outil in TOOL_NAMES:
                    self.assertIn(f"| `{outil}` |", fichiers["SKILL.md"])

    def test_relative_links_resolve_inside_the_package(self):
        for cle, fichiers in self.paquets.items():
            for chemin, texte in fichiers.items():
                for cible in re.findall(r"\]\(([^)#\s]+)\)", texte):
                    if re.match(r"\w+://", cible):
                        continue
                    resolu = (Path(chemin).parent / cible).as_posix()
                    resolu = str(Path(resolu)).replace("\\", "/")
                    with self.subTest(plateforme=cle, fichier=chemin, lien=cible):
                        self.assertIn(resolu, fichiers, "lien hors du paquet")

    def test_no_legacy_names_or_removed_components(self):
        interdits = ("recherche-juridique", "gemini_agent", "droit-francais-skill.onrender",
                     "legifrance_vibe", "../skill/")
        for cle, fichiers in self.paquets.items():
            for chemin, texte in fichiers.items():
                for terme in interdits:
                    with self.subTest(plateforme=cle, fichier=chemin, terme=terme):
                        self.assertNotIn(terme, texte)

    def test_original_author_appears_only_in_the_credits(self):
        for cle, fichiers in self.paquets.items():
            for chemin, texte in fichiers.items():
                if "brissonjo" not in texte:
                    continue
                with self.subTest(plateforme=cle, fichier=chemin):
                    self.assertEqual("README.md", chemin)
                    credits = texte.split("## Origine et licence", 1)
                    self.assertEqual(2, len(credits))
                    self.assertNotIn("brissonjo", credits[0])

    def test_references_are_the_full_skill_references(self):
        for cle, fichiers in self.paquets.items():
            for nom in generer.REFERENCES:
                with self.subTest(plateforme=cle, reference=nom):
                    self.assertEqual(
                        (ROOT / "skill" / "references" / nom).read_text(encoding="utf-8"),
                        fichiers[f"references/{nom}"],
                    )


class ZipTests(unittest.TestCase):
    def test_zip_is_installable_and_reproducible(self):
        plateforme = PLATEFORMES[0]
        fichiers = generer.contenu(plateforme, VERSION)
        with tempfile.TemporaryDirectory() as tmp:
            premier = generer.zipper(plateforme, fichiers, Path(tmp) / "a", VERSION)
            second = generer.zipper(plateforme, fichiers, Path(tmp) / "b", VERSION)
            self.assertEqual(premier.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(premier) as zf:
                noms = set(zf.namelist())
            self.assertEqual({f"pandecte-recherche/{c}" for c in fichiers}, noms)


class FullSkillZipTests(unittest.TestCase):
    def test_full_skill_zip_holds_only_tracked_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = generer.zipper_skill_complet(Path(tmp), VERSION)
            with zipfile.ZipFile(archive) as zf:
                noms = zf.namelist()
        self.assertIn("pandecte-recherche/SKILL.md", noms)
        self.assertIn("pandecte-recherche/references/modes-erreur.md", noms)
        for nom in noms:
            self.assertTrue(nom.startswith("pandecte-recherche/"), nom)
            self.assertNotRegex(nom, r"(^|/)(\.env|profil\.md)$|__pycache__")


class ClaudePluginTests(unittest.TestCase):
    """Le dossier plugin/ est tout ce que claude.ai reçoit du dépôt."""

    def test_plugin_copy_is_up_to_date(self):
        self.assertEqual(
            [], generer.ecarts_plugin(generer.fichiers_plugin()),
            "lancer python declinaisons/generer.py",
        )

    def test_plugin_meets_the_directory_file_rules(self):
        fichiers = [p for p in generer.PLUGIN.rglob("*") if p.is_file()]
        self.assertLessEqual(len(fichiers), 512)
        for fichier in fichiers:
            relatif = fichier.relative_to(generer.PLUGIN).as_posix()
            with self.subTest(fichier=relatif):
                self.assertFalse(fichier.is_symlink())
                self.assertLess(fichier.stat().st_size, 256 * 1024)
                self.assertNotRegex(
                    relatif, r"(^|/)(\.DS_Store|Thumbs\.db|\.env|profil\.md)$|__pycache__"
                )

    def test_plugin_readme_is_long_enough_for_the_directory(self):
        texte = (generer.PLUGIN / "README.md").read_text(encoding="utf-8")
        sans_code = re.sub(r"```.*?```", "", texte, flags=re.S)
        self.assertGreaterEqual(len(sans_code.split()), 40)

    def test_plugin_zips_hold_one_manifest_at_their_root(self):
        cas = {
            "claude": (generer.fichiers_plugin_claude(), ".claude-plugin/plugin.json"),
            "openai": (generer.fichiers_plugin_openai(), ".codex-plugin/plugin.json"),
        }
        for nom, (fichiers, manifeste) in cas.items():
            with self.subTest(plugin=nom), tempfile.TemporaryDirectory() as tmp:
                premier = generer.zipper_plugin(fichiers, Path(tmp) / "a.zip")
                second = generer.zipper_plugin(fichiers, Path(tmp) / "b.zip")
                self.assertEqual(premier.read_bytes(), second.read_bytes())
                with zipfile.ZipFile(premier) as zf:
                    noms = zf.namelist()
                manifestes = [n for n in noms if n.endswith("plugin.json")]
                self.assertEqual([manifeste], manifestes)
                for attendu in (".mcp.json", "README.md", "LICENSE",
                                "skills/pandecte-recherche/SKILL.md"):
                    self.assertIn(attendu, noms)
                for entree in noms:
                    self.assertNotRegex(entree, r"(^|/)(\.env|profil\.md|\.DS_Store)$|__pycache__|\.\./")

    def test_plugin_links_stay_inside_the_plugin(self):
        for fichier in generer.PLUGIN.rglob("*.md"):
            for cible in re.findall(r"(?<!!)\[[^\]]*\]\(([^)#]+)", fichier.read_text(encoding="utf-8")):
                if "://" in cible or cible.startswith("mailto:"):
                    continue
                resolu = (fichier.parent / cible).resolve()
                with self.subTest(fichier=fichier.name, cible=cible):
                    self.assertIn(generer.PLUGIN.resolve(), resolu.parents)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Génère les déclinaisons du skill par plateforme, depuis une source unique.

Sources, seules à modifier à la main :

- ``declinaisons/noyau-compact.md`` — méthode condensée, commune à toutes les
  plateformes ;
- ``declinaisons/plateformes/<clé>.md`` — ce qui change par plateforme
  (connecteur, voie de repli, notes, installation) ;
- ``declinaisons/README-modele.md`` — README commun des paquets ;
- ``skill/references/{audit-documentaire,modules,sources-autorisees}.md`` — copiées
  telles quelles depuis le skill complet.

Sorties, à ne jamais modifier à la main : ``gemini_skill/``, ``grok_skill/``,
``manus_skill/``, ``vibe_skill/``, et, sur demande, un zip par plateforme
contenant un dossier ``pandecte-recherche/`` prêt à installer, plus le zip du
skill complet (``skill/``) pour claude.ai et l'application Claude. Le plugin
Claude ``plugin/`` reçoit aussi sa copie du skill complet et la licence ;
``--zip`` en tire deux archives de plugin : claude.ai (« Upload plugin ») et
soumission OpenAI (manifeste ``.codex-plugin``).

    python declinaisons/generer.py            # régénère les dossiers
    python declinaisons/generer.py --check    # échoue si un dossier est périmé
    python declinaisons/generer.py --zip dist # écrit aussi les zips

Sans dépendance hors bibliothèque standard.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "declinaisons"
NOYAU = HERE / "noyau-compact.md"
CONNECTEUR = HERE / "connecteur.md"
#: Méthode servie par l'outil get_method du serveur MCP.
METHODE_SERVEUR = ROOT / "mcp_server" / "methode.md"
README_MODELE = HERE / "README-modele.md"
PLATEFORMES = HERE / "plateformes"
REFERENCES = ("audit-documentaire.md", "modules.md", "sources-autorisees.md")
NOM_SKILL = "pandecte-recherche"
#: Plugin Claude (claude.ai, application, Cowork, Claude Code).
PLUGIN = ROOT / "plugin"
PLUGIN_SKILL = f"skills/{NOM_SKILL}"
DESCRIPTION = (
    "Méthodologie rigoureuse de recherche en droit français et européen, fondée "
    "sur des sources primaires officielles (Légifrance, Judilibre), la "
    "vérification de provenance, de vigueur et d'applicabilité à une date "
    "donnée, et des citations traçables. Utiliser pour toute demande portant "
    "sur des articles, codes, lois, décrets, arrêtés, circulaires, "
    "qualifications, jurisprudences, actes, notes, mémoires, audits ou concours "
    "juridiques. Ne pas utiliser pour le droit étranger non européen ni pour une "
    "question doctrinale sans citation normative."
)
#: Horodatage fixe des entrées zip : deux générations identiques produisent
#: des archives identiques octet pour octet.
ZIP_DATE = (2026, 1, 1, 0, 0, 0)
_MARQUEUR = re.compile(r"\{\{([A-Z_]+)\}\}")


@dataclass(frozen=True)
class Plateforme:
    cle: str
    nom: str
    dossier: str
    sections: dict[str, str]


def version() -> str:
    manifeste = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return manifeste["version"]


SECTIONS_PLATEFORME = frozenset(
    {"intro", "connecteur", "repli", "notes", "presentation", "installation"}
)
SECTIONS_CONNECTEUR = frozenset({"intro", "connecteur", "repli", "notes"})


def lire_plateforme(chemin: Path, attendues: frozenset[str] = SECTIONS_PLATEFORME) -> Plateforme:
    texte = chemin.read_text(encoding="utf-8")
    if not texte.startswith("---\n"):
        raise ValueError(f"{chemin.name} : en-tête --- attendu")
    entete, corps = texte[4:].split("\n---\n", 1)
    champs = dict(
        ligne.split(":", 1) for ligne in entete.strip().splitlines() if ":" in ligne
    )
    champs = {cle.strip(): valeur.strip() for cle, valeur in champs.items()}
    sections: dict[str, str] = {}
    courante = None
    for ligne in corps.splitlines():
        titre = re.match(r"^# (\w+)\s*$", ligne)
        if titre:
            courante = titre[1].lower()
            sections[courante] = ""
        elif courante is not None:
            sections[courante] += ligne + "\n"
    sections = {cle: valeur.strip() for cle, valeur in sections.items()}
    manquantes = attendues - sections.keys()
    if manquantes:
        raise ValueError(f"{chemin.name} : sections manquantes {sorted(manquantes)}")
    return Plateforme(champs["cle"], champs["plateforme"], champs.get("dossier", ""), sections)


def plateformes() -> list[Plateforme]:
    return [lire_plateforme(p) for p in sorted(PLATEFORMES.glob("*.md"))]


def remplir(modele: str, valeurs: dict[str, str]) -> str:
    def remplacement(match: re.Match[str]) -> str:
        if match[1] not in valeurs:
            raise KeyError(f"marqueur sans valeur : {match[0]}")
        return valeurs[match[1]]

    return _MARQUEUR.sub(remplacement, modele)


def skill_md(plateforme: Plateforme, numero: str) -> str:
    supplement = plateforme.sections.get("frontmatter", "")
    entete = [
        "---",
        f"name: {NOM_SKILL}",
        f"description: {DESCRIPTION}",
        "license: CC-BY-SA-4.0",
    ]
    if supplement:
        entete.append(supplement)
    entete += [
        "metadata:",
        f"  version: {numero}-{plateforme.cle}",
        f"  base: {NOM_SKILL} {numero}",
        "  langue: français",
        f"  adapted_for: {plateforme.nom}",
        "---",
        "",
        f"<!-- Généré par declinaisons/generer.py depuis declinaisons/noyau-compact.md "
        f"et declinaisons/plateformes/{plateforme.cle}.md : ne pas modifier à la main. -->",
        "",
        "",
    ]
    return "\n".join(entete) + corps_methode(plateforme)


def corps_methode(plateforme: Plateforme) -> str:
    return remplir(
        NOYAU.read_text(encoding="utf-8"),
        {
            "PLATEFORME": plateforme.nom,
            "INTRO": plateforme.sections["intro"],
            "CONNECTEUR": plateforme.sections["connecteur"],
            "REPLI": plateforme.sections["repli"],
            "NOTES": plateforme.sections["notes"],
        },
    ).rstrip() + "\n"


def methode_serveur() -> str:
    """Texte renvoyé par l'outil get_method, sans en-tête de skill."""
    connecteur = lire_plateforme(CONNECTEUR, SECTIONS_CONNECTEUR)
    return (
        "<!-- Généré par declinaisons/generer.py depuis declinaisons/noyau-compact.md "
        "et declinaisons/connecteur.md : ne pas modifier à la main. -->\n\n"
        + corps_methode(connecteur)
    )


def readme_md(plateforme: Plateforme) -> str:
    texte = remplir(
        README_MODELE.read_text(encoding="utf-8"),
        {
            "PLATEFORME": plateforme.nom,
            "PRESENTATION": plateforme.sections["presentation"],
            "INSTALLATION": plateforme.sections["installation"],
        },
    )
    return texte.rstrip() + "\n"


def contenu(plateforme: Plateforme, numero: str) -> dict[str, str]:
    """Fichiers du paquet, chemin relatif → texte."""
    fichiers = {
        "SKILL.md": skill_md(plateforme, numero),
        "README.md": readme_md(plateforme),
    }
    for nom in REFERENCES:
        fichiers[f"references/{nom}"] = (ROOT / "skill" / "references" / nom).read_text(
            encoding="utf-8"
        )
    return fichiers


def ecrire(plateforme: Plateforme, fichiers: dict[str, str]) -> None:
    dossier = ROOT / plateforme.dossier
    if dossier.exists():
        shutil.rmtree(dossier)
    for chemin, texte in fichiers.items():
        cible = dossier / chemin
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(texte, encoding="utf-8")


def ecarts(plateforme: Plateforme, fichiers: dict[str, str]) -> list[str]:
    dossier = ROOT / plateforme.dossier
    presents = {
        str(p.relative_to(dossier)) for p in dossier.rglob("*") if p.is_file()
    } if dossier.is_dir() else set()
    problemes = [f"{plateforme.dossier}/{c} : en trop" for c in sorted(presents - fichiers.keys())]
    for chemin, texte in fichiers.items():
        cible = dossier / chemin
        if not cible.is_file():
            problemes.append(f"{plateforme.dossier}/{chemin} : absent")
        elif cible.read_text(encoding="utf-8") != texte:
            problemes.append(f"{plateforme.dossier}/{chemin} : périmé")
    return problemes


def zipper(plateforme: Plateforme, fichiers: dict[str, str], dossier: Path, numero: str) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    archive = dossier / f"{NOM_SKILL}-{plateforme.cle}-{numero}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for chemin in sorted(fichiers):
            info = zipfile.ZipInfo(f"{NOM_SKILL}/{chemin}", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, fichiers[chemin])
    return archive


def fichiers_skill_complet() -> dict[str, bytes]:
    """Skill complet, limité aux fichiers suivis par Git.

    Jamais de fichier local : ni ``scripts/.env`` (identifiants), ni
    ``profil.md`` (choix de l'utilisateur), ni cache Python.
    """
    sortie = subprocess.run(
        ["git", "ls-files", "-z", "skill"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8")
    fichiers = {}
    for chemin in sorted(filter(None, sortie.split("\0"))):
        relatif = chemin[len("skill/"):]
        nom = Path(relatif).name
        if nom == ".env" or nom == "profil.md" or "__pycache__" in relatif:
            raise RuntimeError(f"fichier local suivi par Git, refusé : {chemin}")
        fichiers[relatif] = (ROOT / chemin).read_bytes()
    return fichiers


def zipper_skill_complet(dossier: Path, numero: str) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    archive = dossier / f"{NOM_SKILL}-claude-{numero}.zip"
    fichiers = fichiers_skill_complet()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for chemin in sorted(fichiers):
            info = zipfile.ZipInfo(f"{NOM_SKILL}/{chemin}", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, fichiers[chemin])
    return archive


def fichiers_plugin() -> dict[str, bytes]:
    """Part générée du plugin : skill complet et licence.

    Le manifeste, ``.mcp.json`` et le README de ``plugin/`` s'écrivent à la
    main ; le reste est copié ici, car un plugin ne charge rien hors de son
    dossier (ni lien symbolique, ni chemin ``../``).
    """
    fichiers = {"LICENSE": (ROOT / "LICENSE").read_bytes()}
    for chemin, octets in fichiers_skill_complet().items():
        fichiers[f"{PLUGIN_SKILL}/{chemin}"] = octets
    return fichiers


def ecrire_plugin(fichiers: dict[str, bytes]) -> None:
    cible_skill = PLUGIN / PLUGIN_SKILL
    if cible_skill.exists():
        shutil.rmtree(cible_skill)
    for chemin, octets in fichiers.items():
        cible = PLUGIN / chemin
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(octets)


def ecarts_plugin(fichiers: dict[str, bytes]) -> list[str]:
    dossier = PLUGIN / PLUGIN_SKILL
    presents = {
        f"{PLUGIN_SKILL}/{p.relative_to(dossier)}" for p in dossier.rglob("*") if p.is_file()
    } if dossier.is_dir() else set()
    problemes = [f"plugin/{c} : en trop" for c in sorted(presents - fichiers.keys())]
    for chemin, octets in fichiers.items():
        cible = PLUGIN / chemin
        if not cible.is_file():
            problemes.append(f"plugin/{chemin} : absent")
        elif cible.read_bytes() != octets:
            problemes.append(f"plugin/{chemin} : périmé")
    return problemes


def fichiers_plugin_claude() -> dict[str, bytes]:
    """Contenu du zip « Upload plugin » de claude.ai : le dossier plugin/ suivi par Git."""
    fichiers = dict(fichiers_plugin())
    for nom in (".claude-plugin/plugin.json", ".mcp.json", "README.md"):
        fichiers[nom] = (PLUGIN / nom).read_bytes()
    return fichiers


def fichiers_plugin_openai() -> dict[str, bytes]:
    """Contenu du zip de soumission OpenAI : manifeste .codex-plugin, visuels et skill complet.

    L'adaptateur ``skills/`` de la racine renvoie à ``../../skill/`` ; le zip
    reçoit à la place la copie complète, comme le plugin Claude.
    """
    fichiers = fichiers_plugin_claude()
    del fichiers[".claude-plugin/plugin.json"]
    fichiers[".codex-plugin/plugin.json"] = (ROOT / ".codex-plugin" / "plugin.json").read_bytes()
    for visuel in sorted((ROOT / "assets").glob("*.svg")):
        fichiers[f"assets/{visuel.name}"] = visuel.read_bytes()
    return fichiers


def zipper_plugin(fichiers: dict[str, bytes], archive: Path) -> Path:
    """Zip à plat : le manifeste à la racine de l'archive."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for chemin in sorted(fichiers):
            info = zipfile.ZipInfo(chemin, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, fichiers[chemin])
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="échoue si un dossier généré est périmé")
    parser.add_argument("--zip", metavar="DOSSIER", type=Path, help="écrit un zip par plateforme")
    args = parser.parse_args(argv)
    numero = version()
    problemes: list[str] = []
    for plateforme in plateformes():
        fichiers = contenu(plateforme, numero)
        if args.check:
            problemes += ecarts(plateforme, fichiers)
            continue
        ecrire(plateforme, fichiers)
        print(f"✅ {plateforme.dossier}/ ({plateforme.nom})")
        if args.zip:
            print(f"   📦 {zipper(plateforme, fichiers, args.zip, numero)}")
    methode = methode_serveur()
    if args.check:
        if not METHODE_SERVEUR.is_file() or METHODE_SERVEUR.read_text(encoding="utf-8") != methode:
            problemes.append("mcp_server/methode.md : périmé")
    else:
        METHODE_SERVEUR.write_text(methode, encoding="utf-8")
        print("✅ mcp_server/methode.md (outil get_method)")
    plugin = fichiers_plugin()
    if args.check:
        problemes += ecarts_plugin(plugin)
    else:
        ecrire_plugin(plugin)
        print("✅ plugin/ (skill complet et licence du plugin Claude)")
    if args.zip and not args.check:
        print(f"✅ skill complet (claude.ai, application Claude)\n   📦 {zipper_skill_complet(args.zip, numero)}")
        claude = zipper_plugin(fichiers_plugin_claude(), args.zip / f"pandecte-plugin-claude-{numero}.zip")
        openai = zipper_plugin(fichiers_plugin_openai(), args.zip / f"pandecte-plugin-openai-{numero}.zip")
        print(f"✅ plugins (Upload plugin de claude.ai, soumission OpenAI)\n   📦 {claude}\n   📦 {openai}")
    if args.check:
        if problemes:
            print("❌ Déclinaisons périmées — lancer python declinaisons/generer.py :")
            for probleme in problemes:
                print(f"   - {probleme}")
            return 1
        print("✅ Déclinaisons à jour.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

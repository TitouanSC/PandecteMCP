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
contenant un dossier ``pandecte-recherche/`` prêt à installer.

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
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "declinaisons"
NOYAU = HERE / "noyau-compact.md"
README_MODELE = HERE / "README-modele.md"
PLATEFORMES = HERE / "plateformes"
REFERENCES = ("audit-documentaire.md", "modules.md", "sources-autorisees.md")
NOM_SKILL = "pandecte-recherche"
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


def lire_plateforme(chemin: Path) -> Plateforme:
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
    attendues = {"intro", "connecteur", "repli", "notes", "presentation", "installation"}
    manquantes = attendues - sections.keys()
    if manquantes:
        raise ValueError(f"{chemin.name} : sections manquantes {sorted(manquantes)}")
    return Plateforme(champs["cle"], champs["plateforme"], champs["dossier"], sections)


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
    corps = remplir(
        NOYAU.read_text(encoding="utf-8"),
        {
            "PLATEFORME": plateforme.nom,
            "INTRO": plateforme.sections["intro"],
            "CONNECTEUR": plateforme.sections["connecteur"],
            "REPLI": plateforme.sections["repli"],
            "NOTES": plateforme.sections["notes"],
        },
    )
    return "\n".join(entete) + corps.rstrip() + "\n"


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

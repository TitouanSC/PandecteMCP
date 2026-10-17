"""Méthode de recherche servie par le connecteur (outil ``get_method``).

Pour l'utilisateur qui ne peut rien installer — claude.ai sur un poste tiers,
application mobile, ChatGPT —, la méthode arrive avec le connecteur : sans
argument, l'outil rend la méthode condensée (``mcp_server/methode.md``,
générée depuis ``declinaisons/noyau-compact.md``) ; avec une section, la
référence détaillée correspondante du skill complet (``skill/references`` et
``skill/profils``). Lecture seule, sans appel à PISTE.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
METHODE = Path(__file__).resolve().parent / "methode.md"
SKILL = ROOT / "skill"

#: Sections publiques → fichier du skill complet. Un nom absent d'ici n'est
#: jamais lu : aucun chemin fourni par le client n'atteint le système de
#: fichiers.
SECTIONS: dict[str, str] = {
    "modes-erreur": "references/modes-erreur.md",
    "gabarits-sortie": "references/gabarits-sortie.md",
    "checklist-vigueur": "references/checklist-vigueur.md",
    "format-citation": "references/format-citation.md",
    "gabarits-requetes": "references/gabarits-requetes.md",
    "modules": "references/modules.md",
    "sources-autorisees": "references/sources-autorisees.md",
    "audit-documentaire": "references/audit-documentaire.md",
    "profil-avocat": "profils/avocat.md",
    "profil-police-gendarmerie": "profils/police-gendarmerie.md",
    "profil-collectivites": "profils/collectivites.md",
    "profil-juriste-entreprise": "profils/juriste-entreprise.md",
    "profil-etudiant-concours": "profils/etudiant-concours.md",
}

Section = Literal[
    "modes-erreur",
    "gabarits-sortie",
    "checklist-vigueur",
    "format-citation",
    "gabarits-requetes",
    "modules",
    "sources-autorisees",
    "audit-documentaire",
    "profil-avocat",
    "profil-police-gendarmerie",
    "profil-collectivites",
    "profil-juriste-entreprise",
    "profil-etudiant-concours",
]


def read_method(section: str | None, version: str) -> dict[str, Any]:
    """Méthode condensée, ou la section détaillée demandée."""
    if section is None:
        identifiant, titre, chemin = "methode", "Méthode de recherche PandecteMCP", METHODE
    elif section in SECTIONS:
        identifiant = section
        titre = f"PandecteMCP — {section}"
        chemin = SKILL / SECTIONS[section]
    else:
        raise ValueError(f"Section inconnue : {section!r}.")
    return {
        "id": identifiant,
        "title": titre,
        "text": chemin.read_text(encoding="utf-8"),
        "sections": sorted(SECTIONS),
        "metadata": {
            "source": "PandecteMCP",
            "version": version,
            "usage": (
                "Instructions de méthode à appliquer, distinctes des sources "
                "juridiques : ce texte ne vaut pas source de droit."
            ),
        },
    }

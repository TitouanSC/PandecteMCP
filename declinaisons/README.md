# Déclinaisons par plateforme

Le skill complet `pandecte-recherche` (dossier [`skill/`](../skill)) reste la
source de vérité méthodologique. Pour les assistants qui ne peuvent pas le
charger tel quel (Gemini, Grok, Manus, Vibe), ce dossier produit des **paquets
condensés**, tous issus d'une même source.

## Ce qui se modifie à la main

| Fichier | Contenu |
|---|---|
| [`noyau-compact.md`](noyau-compact.md) | Méthode condensée, **commune** à toutes les plateformes |
| [`plateformes/<clé>.md`](plateformes) | Ce qui change par plateforme : connecteur, voie de repli, notes, présentation, installation |
| [`README-modele.md`](README-modele.md) | README commun des paquets |
| `skill/references/{audit-documentaire,modules,sources-autorisees}.md` | Références copiées telles quelles dans chaque paquet |

## Ce qui est généré

Les dossiers `gemini_skill/`, `grok_skill/`, `manus_skill/` et `vibe_skill/`
à la racine du dépôt sont **générés** : ne jamais les modifier à la main.

```bash
python declinaisons/generer.py            # régénère les dossiers
python declinaisons/generer.py --check    # échoue si un dossier est périmé
python declinaisons/generer.py --zip dist # écrit aussi un zip par plateforme
```

Chaque zip contient un dossier `pandecte-recherche/` prêt à installer
(`SKILL.md`, `references/`, `README.md`) ; deux générations identiques donnent
des archives identiques. `--zip` écrit en plus
`pandecte-recherche-claude-<version>.zip`, le **skill complet** (`skill/`,
fichiers suivis par Git uniquement) à importer dans claude.ai, l'application
Claude et Claude mobile, et deux **zips de plugin**, manifeste à la racine :

- `pandecte-plugin-claude-<version>.zip` : le dossier `plugin/`, pour
  *Personnaliser > Plugins > Ajouter > Importer un plugin* dans claude.ai
  (utile hors marketplace) ;
- `pandecte-plugin-openai-<version>.zip` : manifeste `.codex-plugin/`,
  connecteur et skill complet, pour la soumission à l'annuaire ChatGPT.

La CI exécute `--check` : un noyau modifié sans
régénération fait échouer le build.

## Ajouter une plateforme

Créer `plateformes/<clé>.md` sur le modèle des fichiers existants : un
en-tête (`plateforme`, `cle`, `dossier`) puis les sections `# intro`,
`# connecteur`, `# repli`, `# notes`, `# presentation`, `# installation`, et
au besoin `# frontmatter` (lignes YAML ajoutées à l'en-tête du `SKILL.md`).
Puis régénérer et ajouter la plateforme à la liste attendue de
`tests/test_declinaisons.py`.

N'écrire dans une fiche de plateforme que des noms d'outils et des
emplacements vérifiés ; à défaut, dire explicitement qu'ils ne le sont pas.

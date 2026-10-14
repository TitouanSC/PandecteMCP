# CHANGELOG — PandecteMCP

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Numérotation : [SemVer](https://semver.org/lang/fr/), série unique pour le
serveur MCP, les plugins et le skill `pandecte-recherche`.

---

### [0.1.0] — non publié

Première version de PandecteMCP, projet dérivé de
[droit-francais-skill](https://github.com/brissonjo-sudo/droit-francais-skill)
(© 2026 @brissonjo-sudo, CC BY-SA 4.0).

**Base amont** : commit `f0ce68a` du dépôt d'origine, soit le skill 3.5.0
et le candidat plugin 0.9.0 à huit outils MCP. L'historique antérieur reste
consultable dans le
[CHANGELOG d'origine à ce commit](https://github.com/brissonjo-sudo/droit-francais-skill/blob/f0ce68a/skill/CHANGELOG.md).

#### Modifié
- Projet renommé PandecteMCP : paquet Python `pandecte`, skill
  `pandecte-recherche`, serveur MCP `pandecte`.
- Numérotation repartie à 0.1.0, en série unique.
- Manifestes de plugin rattachés au dépôt TitouanSC/PandecteMCP ;
  URL du serveur distant à configurer au déploiement.

#### Retiré
- Infrastructure, identifiants, visuels et documents de travail propres au
  projet d'origine : workflows liés à son serveur, notes Obsidian, banc
  agentique, dossier de soumission ChatGPT, logo.
- Code des déclinaisons `gemini_agent/` et `vibe_skill/tools/`, remplacé par
  le serveur MCP.

#### Conservé
- Méthodologie du skill (sept principes, dix-huit modes d'erreur, procédure
  en neuf étapes) et les huit outils MCP, sous leurs noms d'origine.

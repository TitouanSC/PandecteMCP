# CHANGELOG — PandecteMCP

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Numérotation : [SemVer](https://semver.org/lang/fr/), série unique pour le
serveur MCP, les plugins et le skill `pandecte-recherche`.

---

### [0.1.3] — 2026-10-24

#### Modifié
- Repli web signalé sur toutes les plateformes, plus seulement dans
  claude.ai : la recherche reste silencieuse, mais toute réponse fondée sur
  le web se termine par une ligne qui dit si le connecteur est déconnecté ou
  absent, et comment le connecter (chemin claude.ai, ChatGPT, ou adresse
  MCP). Constaté dans ChatGPT : un plugin non connecté répondait comme s'il
  fonctionnait (SKILL.md, méthode condensée et déclinaisons).

### [0.1.2] — 2026-10-18

Réglages issus des premiers essais réels dans claude.ai.

#### Modifié
- Provenance : aucune référence juridique de mémoire, même signalée comme
  telle (ancienne numérotation, texte modificatif, date) ; ce que les outils
  peuvent vérifier se vérifie avant d'être écrit (SKILL.md P1 et méthode
  condensée).
- Abstention : une limite n'est inscrite qu'après avoir tenté de la lever
  avec les outils disponibles (droit transitoire, autre code, décision citée
  par une autre).
- Plugin sans connecteur connecté : le repli web reste silencieux, mais la
  réponse indique en une ligne comment connecter PandecteMCP.
- README et README du plugin : installation en deux étapes, connexion du
  connecteur marquée obligatoire.

### [0.1.1] — 2026-10-18

#### Modifié
- Plugin Claude déplacé dans `plugin/`, avec une copie générée du skill
  complet : claude.ai ne donne au plugin que son dossier, où le renvoi
  `../../skill/SKILL.md` de l'adaptateur était introuvable. La marketplace
  pointe vers `./plugin`.

### [0.1.0] — 18 octobre 2026

Première version de PandecteMCP, projet dérivé de
[droit-francais-skill](https://github.com/brissonjo-sudo/droit-francais-skill)
(© 2026 @brissonjo-sudo, CC BY-SA 4.0).

**Base amont** : commit `f0ce68a` du dépôt d'origine, soit le skill 3.5.0
et le candidat plugin 0.9.0 à huit outils MCP. L'historique antérieur reste
consultable dans le
[CHANGELOG d'origine à ce commit](https://github.com/brissonjo-sudo/droit-francais-skill/blob/f0ce68a/skill/CHANGELOG.md).

#### Ajouté
- Serveur hébergé sans identifiants propres : chaque utilisateur se connecte
  avec ses identifiants PISTE sur la page « Connexion PISTE » (OAuth 2.1,
  PKCE, enregistrement dynamique), ou les transmet en clé `pk1` (page « Clé
  personnelle »). Le serveur est son propre serveur d'autorisation et ne
  stocke rien : l'état OAuth voyage chez le client en enveloppes
  AES-256-GCM.
- Outil `get_method` : le connecteur sert lui-même la méthode condensée et
  les références détaillées (modes d'erreur, gabarits, profils…), pour les
  utilisateurs qui ne peuvent installer aucun skill (claude.ai sur un poste
  tiers, mobile, ChatGPT) ; les consignes de connexion y renvoient d'abord.
- Cache des lectures en mémoire vive (textes 6 h, décisions 24 h), limite de
  débit par adresse IP.
- Déploiement Render sans disque (`render.yaml`), instance publique
  `https://pandecte-mcp.onrender.com/mcp`, qualifiée depuis claude.ai,
  ChatGPT et Claude Code.

#### Modifié
- Projet renommé PandecteMCP : paquet Python `pandecte`, skill
  `pandecte-recherche`, serveur MCP `pandecte`.
- Numérotation repartie à 0.1.0, en série unique.
- Manifestes de plugin rattachés au dépôt TitouanSC/PandecteMCP.
- Documentation publique réécrite : README FR/EN, conditions d'utilisation
  (clause de mandat), politique de confidentialité, registre CGU, audit de
  sécurité.

#### Retiré
- Infrastructure, identifiants, visuels et documents de travail propres au
  projet d'origine : workflows liés à son serveur, notes Obsidian, banc
  agentique, dossier de soumission ChatGPT, logo.
- Consultation avec les identifiants PISTE de l'exploitant (mode partagé),
  fournisseur OAuth externe, base de données et disque persistant.
- Code des déclinaisons `gemini_agent/` et `vibe_skill/tools/`, remplacé par
  le serveur MCP.

#### Conservé
- Méthodologie du skill (sept principes, dix-huit modes d'erreur, procédure
  en neuf étapes) et les huit outils MCP, sous leurs noms d'origine.

# Architecture plugin — audit et trajectoire

Date de l'audit : **29 août 2026** (projet d'origine). Étape 5 ajoutée le
**18 octobre 2026** pour PandecteMCP.

Les étapes 1 à 4 retracent l'architecture héritée du projet d'origine ; elles
sont conservées parce que leurs invariants restent en vigueur. L'étape 5 décrit
le serveur hébergé actuel.

Branches d'implémentation :

- étape 1 : **`feat/plugin-foundation`** ;
- étape 2a : **`feat/tooling-foundation`** ;
- étape 2b : **`feat/api-clients`** ;
- étape 3 : **`feat/chatgpt-mcp-app`**.

## Décision

Le dépôt évolue selon une approche **skill-first, plugin-ready** :

- `skill/` reste la source de vérité et le paquet autonome historique ;
- le dépôt devient aussi un plugin OpenAI grâce à `.codex-plugin/plugin.json` ;
- `skills/pandecte-recherche/` sert d'adaptateur de découverte, sans copie du noyau ;
- l'outillage API est extrait progressivement dans le paquet autonome avant d'être exposé par une app ou un serveur MCP.

La méthode juridique, l'interface du CLI et les variables d'environnement existantes restent stables.

## Audit de l'existant

### Points solides

- Le noyau méthodologique est isolé dans `skill/SKILL.md`, avec références et profils dédiés.
- La règle de provenance interdit de produire des identifiants officiels non récupérés pendant la session.
- `skill/scripts/legifrance.py` couvre Légifrance et Judilibre en bibliothèque standard, avec configuration BYOK et dégradation vers le web.
- Les contrôles existants compilent le CLI, vérifient les liens, synchronisent documentation et commandes, puis exécutent 21 sondes hors ligne.
- Les secrets sont exclus du dépôt (`.env` ignoré) et aucune clé n'est embarquée.

### Couplages à réduire

- Le transport HTTP, l'authentification, la logique Légifrance, la logique Judilibre, le formatage et le CLI sont réunis dans un seul fichier.
- Le script est rangé dans le paquet du skill : il n'existe pas encore de bibliothèque réutilisable par une app.
- Le dépôt ne possédait ni manifeste de plugin, ni point de découverte `skills/`, ni contrôle de cohérence du paquet.
- L'installation documentée ciblait uniquement Claude Code.

### Risques d'une migration directe

- Déplacer `skill/` casserait le chemin d'installation autonome et les liens relatifs.
- Déplacer immédiatement `legifrance.py` casserait les commandes documentées et le contrôle `check_commands.py`.
- Déclarer `apps` ou `mcpServers` avant leur implémentation créerait un plugin invalide et laisserait croire que les API sont déjà appelables comme outils natifs.
- Copier le noyau sous `skills/` créerait deux sources de vérité susceptibles de diverger.

## Architecture cible

```text
PandecteMCP/
├── .claude-plugin/
│   └── marketplace.json            # le dépôt sert de marketplace Claude (source ./plugin)
├── plugin/                         # plugin Claude autonome (étape 5)
│   ├── .claude-plugin/plugin.json
│   ├── .mcp.json                   # identique au .mcp.json racine
│   ├── README.md
│   ├── LICENSE                     # copie générée
│   └── skills/pandecte-recherche/  # copie générée du skill complet
├── .codex-plugin/
│   └── plugin.json                 # identité et capacités réellement livrées
├── skills/
│   └── pandecte-recherche/
│       └── SKILL.md                # adaptateur vers le noyau historique
├── skill/                          # compatibilité autonome, source de vérité
│   ├── SKILL.md
│   ├── references/
│   ├── profils/
│   └── scripts/
│       ├── legifrance.py           # façade CLI compatible
│       └── pandecte/         # bibliothèque incluse dans skill/
│           ├── errors.py           # erreurs et codes de sortie
│           ├── config.py           # environnement et secrets
│           ├── transport.py        # HTTP, délais, erreurs réseau
│           ├── legifrance.py       # client OAuth/API Légifrance
│           ├── judilibre.py        # client KeyId/OAuth Judilibre
│           └── tools.py            # opérations juridiques structurées
├── mcp_server/
│   └── server.py                   # pont MCP vers la bibliothèque
├── .mcp.json                       # connexion au serveur hébergé
├── requirements-mcp.txt            # dépendance isolée du serveur
└── tests/
    ├── check_plugin.py
    ├── check_commands.py
    ├── check_links.py
    ├── test_tools.py
    └── run_eval.py
```

### Flux cible

```text
Utilisateur
    ↓
Plugin → skill pandecte-recherche → méthode et règles de provenance
    ↓
App / outils MCP → bibliothèque skill/scripts/pandecte
    ↓
API officielles Légifrance et Judilibre
```

Le skill décide **quand et comment rechercher**. La bibliothèque exécute les appels déterministes. L'app expose uniquement des opérations bornées et structurées au modèle.

## Migration progressive

### Étape 1 — socle plugin (implémentée)

- Ajouter un manifeste plugin minimal et valide.
- Ajouter un adaptateur natif sous `skills/` qui charge `skill/SKILL.md`.
- Ne déclarer ni app ni serveur MCP.
- Ajouter un contrôle CI des invariants de compatibilité.
- Documenter la trajectoire et les limites de cette version.

Critère de sortie : le validateur du plugin, le validateur du skill et tous les tests historiques passent sans modifier le noyau.

### Étape 2 — bibliothèque d'outils (implémentée)

- **2a — implémentée :** extraire erreurs, configuration et transport dans `skill/scripts/pandecte/`.
- **2b — implémentée :** extraire les clients Légifrance et Judilibre dans ce même paquet.
- Conserver `skill/scripts/legifrance.py` comme façade compatible vers la nouvelle bibliothèque.
- Ajouter des tests unitaires avec réponses HTTP simulées, sans dépendance au réseau ni aux clés PISTE.
- Stabiliser des résultats structurés indépendants de l'affichage terminal.

Le paquet reste volontairement sous `skill/scripts/` plutôt qu'à la racine :
les installations historiques copient uniquement `skill/`. Un paquet racine
aurait donc cassé le CLI autonome ou imposé une duplication du code.

Critère de sortie atteint : les huit commandes, codes de sortie et variables
d'environnement restent compatibles ; les clients renvoient des structures
JSON indépendantes du rendu terminal et sont testés sans réseau.

### Étape 3 — serveur MCP tool-only (implémentée)

- Exposer les outils standard `search` et `fetch`, plus les opérations bornées
  `search_articles`, `get_article`, `search_case_law` et `get_decision`.
- Définir des schémas d'entrée/sortie stricts et préserver l'abstention en cas d'échec de récupération.
- Ajouter `.mcp.json` seulement lorsque le serveur correspondant est exécutable et testé ; ne pas ajouter `.app.json` car cette version n'a pas de widget.
- Laisser les secrets dans l'environnement ou le mécanisme d'authentification de l'hôte ; ne jamais les placer dans le manifeste ou les réponses d'outil.

Critère de sortie atteint hors réseau : les résultats simulés conservent
l'identifiant et l'URL officiels, et un client MCP réel découvre les outils
sur stdio — six à l'origine, huit avec `get_section` et
`get_text` (voir `extension-sections-textes.md`), neuf avec `get_method`,
qui sert la méthode de recherche aux assistants sans skill installé. Le transport Streamable HTTP sert le même serveur sur `/mcp`.

Le déploiement HTTPS et la connexion à un compte ChatGPT restent des opérations
de distribution de l'étape 4 : aucune URL distante n'est inventée dans le dépôt.

### Étape 4 — distribution (projet d'origine)

- Endpoint MCP public, politiques publiques et métadonnées du manifeste.
- Le projet d'origine faisait consulter les API avec les identifiants PISTE de
  l'exploitant, derrière un fournisseur OAuth externe. PandecteMCP a abandonné
  ce modèle à l'étape 5.

#### Distribution Claude Code (implémentée, 1ᵉʳ septembre 2026)

- `.claude-plugin/plugin.json` réutilise les mêmes briques que le plugin
  OpenAI — adaptateur `skills/pandecte-recherche/` — sans dupliquer le noyau.
  Le serveur MCP est déclaré en **connexion distante** (`type: "http"`,
  adresse du serveur hébergé) plutôt qu'en lancement local : l'installation ne
  requiert ni Python ni les dépendances du dépôt côté utilisateur. Depuis la 0.8.3, cette déclaration n'existe plus
  qu'à un seul endroit : le `.mcp.json` de la racine, que Claude Code reprend
  automatiquement pour un plugin. Le manifeste ne la duplique plus.
- Le lancement local (`python mcp_server/server.py`) reste disponible pour le
  développement et l'auto-hébergement, documenté dans `docs/deployment.md`.
- `.claude-plugin/marketplace.json` (source `./`) faisait du dépôt son propre
  marketplace : l'installation copiait le dépôt entier, donc l'adaptateur
  retrouvait `skill/SKILL.md`. Remplacé à l'étape 5 par le dossier `plugin/`
  (voir plus bas).
- Validé par `claude plugin validate --strict` et un cycle complet
  installation/désinstallation ; les secrets restent hors du paquet publié
  (`.env` ignoré par Git, identifiants PISTE fournis par l'environnement ou
  `LEGIFRANCE_DOTENV`).

#### Convention de versions et de tags

Deux séries cohabitent : **skill** (3.x, méthodologie) et **plugin** (0.x,
empaquetage OpenAI et Claude Code). Les tags Git portent le préfixe de leur
série — `skill-v*` et `plugin-v*`, appliqués pour la première fois le
1er septembre 2026 (voir `skill/CHANGELOG.md`).
Les tags historiques non préfixés (`v2.0.0`, `v2.4.0`, `v3.0.0`) désignent
des versions du skill et sont conservés tels quels.

### Étape 5 — serveur d'autorisation intégré (PandecteMCP, octobre 2026)

- Le serveur hébergé ne détient **aucune** clé PISTE : chaque utilisateur se
  connecte avec les siennes, sur la page « Connexion PISTE » (OAuth 2.1, PKCE,
  enregistrement dynamique), ou les transmet en clé `pk1` dans un en-tête.
- Le serveur est son propre serveur d'autorisation et ne stocke rien : tout
  l'état OAuth voyage chez le client sous forme d'enveloppes AES-256-GCM
  (`mcp_server/sealed.py`, `mcp_server/piste_oauth.py`).
- Plus de base de données ni de disque : cache des réponses publiques en
  mémoire vive, limite de débit par IP.
- Déployé sur Render (offre gratuite) par `render.yaml` ; qualifié le
  17/10/2026 depuis claude.ai, ChatGPT et Claude Code.

```text
Assistant → [OAuth : page « Connexion PISTE » | en-tête pk1]
          → serveur MCP (jeton scellé → identifiants de l'utilisateur)
          → bibliothèque skill/scripts/pandecte → API Légifrance et Judilibre
```

#### Plugin Claude autonome (`plugin/`, 18 octobre 2026)

- claude.ai (chat, application, mobile, Cowork) installe un plugin depuis
  une marketplace GitHub, sans téléchargement, mais ne lui donne que **son
  dossier** : un renvoi `../../skill/SKILL.md` y serait introuvable, et
  l'annuaire d'Anthropic refuse liens symboliques et chemins sortants.
- Le plugin Claude vit donc dans `plugin/` : manifeste, `.mcp.json` (identique
  à celui de la racine) et README écrits à la main ; skill complet et licence
  copiés par `declinaisons/generer.py`, que `--check` et
  `tests/test_declinaisons.py` gardent à jour. La copie est générée : le noyau
  reste maintenu en un seul exemplaire (invariant 6).
- `.claude-plugin/marketplace.json` pointe vers `./plugin`. Le plugin OpenAI
  (`.codex-plugin/`, adaptateur `skills/`) est inchangé.

## Invariants de non-régression

1. `skill/SKILL.md` reste installable indépendamment du plugin.
2. Les chemins et commandes documentés de `skill/scripts/legifrance.py` restent valides jusqu'à une version majeure explicitement annoncée.
3. Une clé absente ne réduit jamais les exigences de provenance ; elle déclenche la voie de repli ou l'abstention.
4. Aucun identifiant officiel n'est présenté comme vérifié s'il ne provient pas d'une récupération effective.
5. Le manifeste ne déclare que les composants réellement présents et testés.
6. Le noyau juridique ne doit exister qu'en un seul exemplaire maintenu.
7. Le serveur hébergé n'utilise jamais d'autres identifiants PISTE que ceux de
   l'utilisateur de la requête.

## Tests actifs

- validation officielle de `.codex-plugin/plugin.json` ;
- validation du frontmatter de `skills/pandecte-recherche/SKILL.md` ;
- `claude plugin validate ./plugin` et règles de fichiers de l'annuaire
  (`tests/test_declinaisons.py`) ;
- contrôle local `tests/check_plugin.py` ;
- tests unitaires hors réseau `tests/test_tools.py` ;
- tests du service et du protocole MCP `tests/test_mcp_app.py` ;
- tests de la connexion PISTE `tests/test_sealed.py`, `tests/test_piste_oauth.py`,
  `tests/test_connexion.py` et `tests/test_piste_end_to_end.py` ;
- compilation Python ;
- contrôle des liens et des commandes documentées ;
- évaluation hors ligne des 21 sondes existantes.

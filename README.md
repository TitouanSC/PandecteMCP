[🇫🇷 Français](README.md) | [🇬🇧 English](README.en.md)

# PandecteMCP

**Recherche en droit français pour les assistants d'IA : une méthode
anti-hallucination et un serveur MCP qui interroge Légifrance et Judilibre
avec vos propres identifiants PISTE (v0.1.3).**

> **Projet indépendant**, sans lien avec l'auteur du projet d'origine, avec une
> personnalité ou une institution, ni avec l'État. PandecteMCP **ne remplace pas
> un avocat** : il aide à trouver et à vérifier des sources, il ne donne pas de
> conseil juridique. Il consulte les API Légifrance et Judilibre dans le respect
> de leurs conditions générales d'utilisation (CGU).

PandecteMCP réunit deux briques :

- **un skill** (méthode) qui impose à l'assistant de travailler sur sources
  primaires, de vérifier la version en vigueur et de dire ce qui reste
  invérifiable ;
- **un serveur MCP** hébergé, que vous ajoutez à votre assistant comme un
  connecteur : **rien à installer**, et chaque consultation passe par **vos
  propres** identifiants PISTE, gratuits.

| Usage | Ce qu'il faut | Pour qui |
|---|---|---|
| Connecteur hébergé | Une adresse à ajouter, vos identifiants PISTE | claude.ai, ChatGPT, Claude Code et tout client MCP |
| Skill seul | Rien, ou une clé PISTE facultative | Assistants qui chargent des skills |
| Instance personnelle | Un hébergeur ou votre poste | Qui ne veut confier ses clés à personne |

---

## Le problème, en 10 secondes

Le danger n'est pas le mensonge évident (un « article L. 9999-1 » que tout
modèle récent rejette). C'est le **mensonge plausible** : une référence
parfaitement formatée, mais fausse — impossible à repérer à l'œil.

**Illustration historique** — Gemini 3.5 extended, 5 juillet 2026, selon le
compte rendu conservé par le projet d'origine. Cet essai isolé ne mesure ni les
modèles actuels ni l'effet de l'outil. Question : *« Donne-moi la référence
exacte (chambre, date, n° de pourvoi) de trois arrêts de la Cour de
cassation. »* Vérification en source primaire des trois réponses :

| Réponse de l'IA | Réalité (Légifrance) | Verdict |
|---|---|---|
| Gabillet — Civ. 2e, 19 févr. 1992, n° 90-19.493 | Ass. plén., 9 mai 1984, n° 80-14.994 | ❌ Chambre, date **et** n° faux |
| Anxiété — Soc., 11 mai 2010, n° 09-42.241 | Soc., 11 mai 2010, n° 09-42.241 | ✅ Exact |
| Rupture brutale — Com., 20 mars 2012, n° 11-13.245 | Aucun arrêt à ce n° | ⚠️ Introuvable |

Deux références sur trois fausses ou fantômes — dont le **bon nom d'arrêt
avec une référence entièrement inventée**. Le **TA d'Orléans**, dans son
[jugement du 29/12/2025, n° 2506461](https://opendata.justice-administrative.fr/recherche/shareFile/TA45/DTA_2506461_20251229),
relève des décisions citées inexistantes ou dont le numéro ne correspond pas
à la date, et invite le conseil à vérifier ses références. Ce constat ne
démontre pas quel outil aurait produit ces références.

**Comportement prescrit par le skill**, à vérifier en exécution :
> ⚠️ *Je ne produis pas ces numéros de pourvoi sans les avoir vérifiés en
> source primaire (Judilibre / Légifrance) — je ne les invente pas.*

---

## Utiliser PandecteMCP sans rien installer

Adresse du serveur : **`https://pandecte-mcp.onrender.com/mcp`**

**Le lien à partager : [pandecte-mcp.onrender.com](https://pandecte-mcp.onrender.com/)**,
une page qui donne la marche à suivre pour chaque IA (Claude, ChatGPT, Le Chat,
Claude Code, Cursor, VS Code, Gemini CLI…), avec des liens d'installation
directe pour Cursor et VS Code.

À la première connexion, votre assistant ouvre la page **« Connexion PISTE »**
du serveur : vous y saisissez votre Client ID et votre Client Secret PISTE, une
seule fois. Ensuite, chaque consultation se fait avec ces identifiants, sans
rien ressaisir.

**La méthode arrive avec le connecteur.** Sans aucun skill installé, l'assistant
lit la méthode de recherche par l'outil `get_method` avant toute analyse
juridique. Le skill complet (ci-dessous) reste préférable quand on peut
l'installer : il est plus détaillé et se charge sans appel d'outil.

### Obtenir ses identifiants PISTE (gratuit)

1. Créez un compte sur [piste.gouv.fr](https://piste.gouv.fr).
2. Acceptez les CGU des API **Légifrance** et **JUDILIBRE** (menu API →
   consentement CGU), en environnement **Production**.
3. Applications → **Créer une application** (environnement Production), en
   cochant Légifrance et JUDILIBRE.
4. Sur la fiche de l'application, bloc **OAuth** : relevez le **Client ID** et
   le **Client Secret**. Ce sont les deux seules valeurs demandées.

Le pas à pas détaillé et les erreurs fréquentes sont dans
[`skill/scripts/README.md`](skill/scripts/README.md).

### claude.ai (web, application, mobile)

**Le plus simple : le plugin**, qui apporte le skill complet et le connecteur,
depuis le navigateur. Deux étapes :

1. **Ajouter le plugin** : **Personnaliser** → **Plugins** → *Ajouter* →
   *Ajouter une marketplace* : `TitouanSC/PandecteMCP`, puis ajoutez le plugin
   **PandecteMCP**.
2. **Connecter le connecteur (obligatoire)** : dans l'onglet **Connecteurs**
   du plugin, *Connecter*, puis renseignez vos identifiants sur la page
   « Connexion PISTE ». Sans cette étape, le skill est là mais aucun outil :
   l'assistant se rabat sur le web, que Légifrance bloque souvent.

Le plugin suit votre compte : application de bureau, mobile, Cowork et Claude
Code le reçoivent aussi. Le message sur la *synchronisation automatique* peut
être ignoré : *Vérifier les mises à jour* suffit.

Connecteur seul : Paramètres → **Connecteurs** → *Ajouter un connecteur personnalisé* : nom
`PandecteMCP`, URL `https://pandecte-mcp.onrender.com/mcp`, champs OAuth
avancés laissés vides. Cliquez sur **Se connecter**, puis renseignez vos
identifiants sur la page « Connexion PISTE ».

### ChatGPT

Paramètres → **Applications et connecteurs** → Paramètres avancés → activez le
**Mode développeur** (selon votre offre), puis **Créer** : URL
`https://pandecte-mcp.onrender.com/mcp`, authentification **OAuth**. ChatGPT
ouvre ensuite la page « Connexion PISTE ».

### Claude Code

```bash
claude mcp add --transport http pandecte https://pandecte-mcp.onrender.com/mcp
```

Puis `/mcp` → `pandecte` → **Authenticate** : le navigateur ouvre la page
« Connexion PISTE ». Le plugin du dépôt déclare le même serveur :

```bash
claude plugin marketplace add TitouanSC/PandecteMCP
claude plugin install pandecte@pandecte
```

### Autres clients MCP

Cursor, VS Code, Gemini CLI et les autres clients compatibles MCP « HTTP »
se connectent de la même façon (OAuth). Ceux qui ne gèrent pas OAuth acceptent
une **clé personnelle** en en-tête `Authorization: Bearer pk1.…`, assemblée
dans votre navigateur sur
[la page « Clé personnelle »](https://pandecte-mcp.onrender.com/cle).
Seuls claude.ai, ChatGPT et Claude Code ont été testés à ce jour.

### Vos identifiants, et les limites du service

- **Rien n'est stocké.** Le serveur vérifie vos identifiants auprès de PISTE,
  puis les **chiffre** (AES-256-GCM) dans le jeton que garde votre assistant.
  Il ne les déchiffre que le temps de chaque consultation ; il ne les écrit
  nulle part et ne les journalise jamais. Le serveur ne possède **aucun**
  identifiant PISTE à lui.
- **Retirer l'accès** : déconnectez le connecteur, ou régénérez votre Client
  Secret sur PISTE (cela invalide immédiatement tout jeton qui le contient).
- **Responsabilité** : vos identifiants restent réservés à votre usage (CGU
  Légifrance § III.3, Judilibre § XI.C). En les confiant au service, vous lui
  donnez mandat de consulter les API **en votre nom**, comme intermédiaire
  technique — voir les [conditions d'utilisation](docs/terms-of-use.md). Pour
  ne les confier à personne, hébergez votre propre instance.
- **Quotas** : vos consultations consomment **votre** quota PISTE. Le serveur
  limite en outre chaque adresse IP à 30 appels d'outil par minute.
- **Hébergement gratuit** : le serveur reste éveillé de 7 h à 23 h (heure de
  Paris). La nuit, il s'endort après 15 minutes sans activité ; le premier
  appel suivant attend son réveil (environ 30 secondes) et peut échouer une
  fois. Réessayez simplement.
- **Données traitées** : voir la [politique de confidentialité](docs/privacy-policy.md).

---

## Public visé

Tout praticien du droit français — **le métier se configure via un profil**
(voir [« Choisir son profil »](#choisir-son-profil)) :

- **Forces de l'ordre** (police nationale, gendarmerie, police municipale)
- **Avocats** (conseil et contentieux)
- **Juristes d'entreprise** (droit des affaires, conformité)
- **Cadres et juristes territoriaux** (collectivités)
- **Étudiants et candidats aux concours** juridiques
- Toute personne ayant besoin de références juridiques fiables dans un acte
  ou un document officiel

---

## Ce que fait le skill

Quand l'assistant détecte une requête juridique (article de loi, qualification
pénale, jurisprudence, rédaction d'acte, vérification d'un texte en
vigueur…), le skill active une procédure en 9 étapes incluant :

- **7 principes** anti-hallucination (primarité des sources, date de
  référence, hiérarchie des normes, citation traçable, séparation des
  registres, légalité criminelle, abstention informée)
- **9 étapes** avec critères de sortie explicites : qualification (0) →
  arbitrage des informations manquantes (0 bis) → cartographie (1) →
  récupération (2) → fraîcheur (3) → jurisprudence (4) → articulation (5) →
  rédaction (6) → auto-critique (7)
- **18 modes d'erreur** documentés et contrés
- **4 techniques** de raisonnement (qualification adversariale,
  triangulation, archéologie textuelle, distinction)
- **6 modules activables** selon la requête (PÉNAL, ACTE-ADMIN, PA-PJ,
  FOND, CONTENTIEUX, DOC-AUDIT)
- **Gabarits de sortie** normalisés (express, fond, citation pour acte,
  audit documentaire, note de concours)
- **Règle de provenance** : tout identifiant officiel (`LEGIARTI`, `NOR`,
  n° de pourvoi…) doit provenir d'un appel d'outil de la session, jamais de la
  mémoire — sinon il est marqué « non vérifié »
- **Récupération outillée** : le serveur MCP, ou le script
  `skill/scripts/legifrance.py`, interroge **Légifrance** (codes, textes,
  décisions CE et CC) et **Judilibre** (Cour de cassation, cours d'appel,
  tribunaux). Sans accès, l'étape 2 bascule sur la recherche web encadrée sur
  domaines officiels, sans rien perdre en exigence de provenance
- **Profils configurables** : le métier de l'utilisateur se règle via un
  `profil.md` — le noyau méthodologique reste universel

> 🔑 **Le skill fonctionne sans clé.** À défaut d'outil, la récupération passe
> par la recherche web sur les domaines officiels. Le serveur MCP, ou une clé
> PISTE locale, rend la récupération déterministe et fiabilise la règle de
> provenance.

---

<a id="choisir-son-profil"></a>
## Choisir son profil

Le skill s'adapte à votre métier via un fichier `profil.md` (défauts de
contexte, jamais des certitudes — voir [`skill/profils/`](skill/profils/)) :

| Profil | Pour qui | 3ᵉ regard d'auto-critique |
|--------|----------|---------------------------|
| `police-gendarmerie` | Police nationale / gendarmerie / police municipale | L'avocat de la défense (nullité de procédure) |
| `avocat` | Avocat (conseil, contentieux) | Le confrère adverse |
| `juriste-entreprise` | Direction juridique, conformité | Le régulateur / l'auditeur |
| `collectivites` | DGS, secrétaire de mairie, juriste territorial | Le contrôle de légalité préfectoral |
| `etudiant-concours` | Étudiant / candidat concours | Le jury / le correcteur |

**Activation** (après installation) :

```bash
cd ~/.claude/skills/pandecte-recherche
cp profils/avocat.md profil.md      # remplacer par votre profil
```

Sans `profil.md`, le skill tourne en **profil neutre** : il ne présume aucun
contexte et pose la question quand elle devient décisionnelle.

---

## Installer le skill

### Avec `npx` (recommandé)

```bash
npx skills add https://github.com/TitouanSC/PandecteMCP/tree/main/skill --skill pandecte-recherche
```

Le skill signale une fois par session qu'une nouvelle version existe, sans
interrompre une recherche. La mise à jour reste à votre main :

```bash
npx skills update pandecte-recherche
```

Pour une mise à jour automatique (installation globale), créez le fichier
`.pandecte-recherche-update.json` à la racine installée du skill :

```json
{ "automatic": true }
```

Votre `profil.md` et votre `scripts/.env` sont conservés.

### Manuellement

Copier le **contenu** du dossier `skill/` dans
`~/.claude/skills/pandecte-recherche/` (macOS, Linux) :

```bash
git clone https://github.com/TitouanSC/PandecteMCP
cp -r PandecteMCP/skill ~/.claude/skills/pandecte-recherche
```

Sous Windows :

```powershell
git clone https://github.com/TitouanSC/PandecteMCP
Copy-Item -Recurse PandecteMCP\skill "$env:USERPROFILE\.claude\skills\pandecte-recherche"
```

Le champ `name:` de `skill/SKILL.md` doit correspondre au nom du dossier
d'installation. Le guide [`docs/installation.md`](docs/installation.md) couvre
les plugins Claude Code et OpenAI.

### Sur d'autres plateformes

| Dossier | Plateforme | Nature |
|---|---|---|
| [`gemini_skill/`](gemini_skill) | Gemini (Google) | Noyau condensé, connecteur MCP en priorité, repli sur la recherche Google |
| [`grok_skill/`](grok_skill) | Grok (xAI) | Noyau condensé, outils web natifs |
| [`vibe_skill/`](vibe_skill) | Vibe (Mistral) | Noyau condensé, outils `web_search` / `web_fetch` |
| [`manus_skill/`](manus_skill) | Manus | Noyau condensé, connecteur MCP en priorité |

Ces paquets sont **générés** depuis une source unique
([`declinaisons/`](declinaisons/README.md)) : un noyau condensé commun et une
fiche par plateforme. `skill/` reste la source de vérité méthodologique.

---

## Déclenchement

Le skill s'active quand vous :
- citez ou demandez un article de loi, de code, un décret, un arrêté
- demandez une qualification juridique (pénale, administrative, civile)
- vérifiez si un texte est en vigueur, abrogé ou modifié
- demandez une jurisprudence (Cass., CE, CC, CJUE, CEDH)
- auditez, relisez ou corrigez juridiquement un document ou un corpus
- rédigez un arrêté municipal, une note au Maire, un mémoire
- préparez un oral ou écrit de concours

**Balises de contrôle :**
- `[complet]` — mode exhaustif, tous modules activés
- `[express]` — mode allégé (PÉNAL et DOC-AUDIT restent actifs lorsqu'applicables)
- `[syllogisme]` — structure majeure / mineure / conclusion (concours)
- `[opérationnel]` — section implications opérationnelles activée
- `[lookup]` — voie rapide : référence ponctuelle, sortie minimale

---

## Héberger sa propre instance

Pour ne confier vos identifiants à personne, faites tourner le serveur
vous-même :

- **En local** (Claude Code, Claude Desktop, Cursor…), avec vos identifiants
  dans un `.env` :

```bash
python -m pip install -r requirements-mcp.txt
python mcp_server/server.py
```

- **En ligne**, sur Render (offre gratuite possible) ou tout hébergeur Docker :
  voir le [guide de déploiement](docs/deployment.md). L'instance n'a besoin
  d'aucun identifiant PISTE : chacun de ses utilisateurs se connecte avec les
  siens.

---

## Arborescence

```
PandecteMCP/
├── .claude-plugin/                 ← marketplace Claude (pointe vers plugin/)
├── .codex-plugin/                  ← plugin OpenAI
├── .mcp.json                       ← connexion au serveur hébergé
├── assets/                         ← logo et icône (SVG)
├── mcp_server/
│   ├── server.py                   ← outils MCP (stdio ou HTTP /mcp)
│   ├── piste_oauth.py              ← serveur d'autorisation sans stockage
│   ├── sealed.py                   ← enveloppes chiffrées (AES-256-GCM)
│   ├── connexion.py                ← page « Connexion PISTE »
│   ├── accueil.py                  ← page d'accueil, marche à suivre par IA
│   ├── cle.py                      ← page « Clé personnelle »
│   └── catalog.py                  ← liste des outils publiés
├── plugin/                         ← plugin Claude (claude.ai, Claude Code)
├── skills/pandecte-recherche/      ← adaptateur du plugin OpenAI vers le noyau
├── skill/                          ← skill autonome, source de vérité
│   ├── SKILL.md                    ← noyau méthodologique
│   ├── CHANGELOG.md                ← historique des versions
│   ├── profils/                    ← profils métier
│   ├── references/                 ← gabarits, modules, modes d'erreur…
│   └── scripts/                    ← accès PISTE (Légifrance, Judilibre)
├── docs/                           ← déploiement, CGU, confidentialité…
├── gemini_skill/ grok_skill/ vibe_skill/ manus_skill/
├── tests/                          ← tests hors réseau et contrôles du dépôt
├── Dockerfile, render.yaml         ← image et Blueprint Render
├── README.md, README.en.md
└── LICENSE
```

---

## Maintenance

Revue annuelle recommandée le **1er septembre** (rentrée juridique).
Procédure détaillée → [`skill/references/maintenance.md`](skill/references/maintenance.md).

> **Note de synchronisation :** à chaque version, mettre à jour `README.md` et
> sa traduction complète `README.en.md`, ainsi que `skill/CHANGELOG.md`.

---

## Crédits et licence

PandecteMCP est une **version modifiée** de
[droit-francais-skill](https://github.com/brissonjo-sudo/droit-francais-skill),
créé par **@brissonjo-sudo** : la méthode de recherche, les modes d'erreur, les
profils et l'accès aux API PISTE en proviennent. Les modifications (serveur
hébergé, connexion par identifiants PISTE de l'utilisateur, renommage,
documentation) sont de **@TitouanSC**. Le projet n'est ni affilié ni approuvé
par l'auteur d'origine.

- © 2026 @brissonjo-sudo — œuvre d'origine
- Modifications © 2026 @TitouanSC

L'ensemble est publié sous
[Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)](LICENSE),
comme l'œuvre d'origine. Les données consultées proviennent de Légifrance
(DILA) et de la base Open Data de la Cour de cassation (Judilibre).

---

## Contribution

Issues et pull requests bienvenues sur GitHub.

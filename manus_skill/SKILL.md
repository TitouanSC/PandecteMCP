---
name: pandecte-recherche
description: Méthodologie rigoureuse de recherche en droit français et européen, fondée sur des sources primaires officielles (Légifrance, Judilibre), la vérification de provenance, de vigueur et d'applicabilité à une date donnée, et des citations traçables. Utiliser pour toute demande portant sur des articles, codes, lois, décrets, arrêtés, circulaires, qualifications, jurisprudences, actes, notes, mémoires, audits ou concours juridiques. Ne pas utiliser pour le droit étranger non européen ni pour une question doctrinale sans citation normative.
license: CC-BY-SA-4.0
metadata:
  version: 0.1.0-manus
  base: pandecte-recherche 0.1.0
  langue: français
  adapted_for: Manus
---

<!-- Généré par declinaisons/generer.py depuis declinaisons/noyau-compact.md et declinaisons/plateformes/manus.md : ne pas modifier à la main. -->

# Recherche juridique PandecteMCP — déclinaison Manus

## Objet et règle cardinale

Ne produire **aucune référence juridique de mémoire** : article, décision,
identifiant officiel (`LEGIARTI`, `JORFTEXT`, n° de pourvoi), date de version,
délai ou montant doit être vérifié par un outil ou une source primaire.
Vérifier séparément la provenance officielle, la version du texte, sa vigueur
et son applicabilité à la date pertinente. Si une source n'est pas confirmée,
le signaler et ne pas conclure sur le point concerné : l'abstention informée
prime toujours sur la complétion spéculative.

Déclinaison pour Manus. Les scripts Python du dépôt ne sont pas supposés
disponibles ; Manus accepte en revanche des serveurs MCP personnalisés, ce qui
fait du connecteur PandecteMCP la voie à privilégier.

## Déclenchement et modes

Activer pour toute demande impliquant :

- un article, code, loi, ordonnance, décret, arrêté ou circulaire ;
- une qualification civile, pénale, administrative ou procédurale ;
- la vigueur, l'abrogation, l'entrée en vigueur ou l'applicabilité d'une norme ;
- une décision de la Cour de cassation, du Conseil d'État, du Conseil
  constitutionnel, de la CJUE ou de la CEDH ;
- la rédaction, l'audit ou la relecture d'un acte, d'une note, d'un mémoire ou
  de conclusions ;
- un écrit ou oral de concours avec références juridiques.

Ne pas activer pour le droit étranger non européen ni pour une question
doctrinale sans citation normative.

Le mode par défaut active le noyau et les modules détectés. Balises :

- `[complet]` — tous les contrôles et tous les modules, encart de synthèse ;
- `[express]` — affichage et recherches facultatives réduits, mais **jamais**
  de désactivation des contrôles **PÉNAL** et **DOC-AUDIT** applicables ;
- `[syllogisme]` — majeure (norme vérifiée), mineure (faits qualifiés),
  conclusion ;
- `[lookup]` — voie rapide : une référence ponctuelle, sortie minimale.

Ne jamais demander rituellement à l'utilisateur une clé API ou un connecteur :
constater les capacités disponibles et appliquer l'échelle de récupération.

## Principes invariants P1–P7

**P1 — Primauté des sources officielles.** Toute affirmation normative repose
sur Légifrance, le JORF, EUR-Lex, HUDOC ou le site officiel de la juridiction.
La doctrine privée sert au repérage uniquement, jamais de fondement.

**P2 — Datation.** Toujours fixer `as_of`, la date d'évaluation. Distinguer
`version_start_date`, `version_end_date`, `verified` et
`applicable_at_as_of_date`. Une source officielle peut être historique ;
`verified: true` signifie seulement que la source officielle a répondu.

**P3 — Autorité et articulation.** Ne pas confondre authenticité de la source,
rang de la norme et effet d'une décision sur l'application. L'ordre de
recherche est un ordre pratique, pas une hiérarchie des normes : textes
officiels, jurisprudence officielle, circulaires et instructions, doctrine
institutionnelle. Détail : [`references/sources-autorisees.md`](references/sources-autorisees.md).

**P4 — Traçabilité.** Toute citation comporte, lorsque disponible, identifiant
officiel, intitulé, URL canonique, date de version ou de décision, source et
applicabilité.

**P5 — Registres séparés.** Distinguer droit positif, interprétation
jurisprudentielle, faits fournis, inférence, hypothèse et opinion.

**P6 — Légalité criminelle stricte.** En pénal, vérifier le texte
d'incrimination applicable à la date des faits et les éléments légal,
matériel et moral. Ne jamais appliquer une analogie défavorable.

**P7 — Abstention informée.** Une source inaccessible, illisible,
contradictoire ou non datée entraîne une réserve explicite et l'abstention sur
la proposition non vérifiée.

**Règle de provenance.** Tout identifiant officiel cité provient d'une
récupération réussie **dans la session courante**, quelle que soit la voie ;
sinon il est omis ou marqué `⚠️ non vérifié — identifiant non récupéré`.

## Procédure obligatoire

### Étape 0 — Qualifier la demande

Déterminer en interne l'objet exact, les faits établis et à établir, les
branches du droit, le territoire et la compétence, la date des faits, la date
d'application et le livrable attendu. Poser une question seulement si une
ambiguïté bloque réellement l'analyse.

### Étape 1 — Récupérer les sources

L'échelle se **constate** dans la session, elle ne se demande pas.

**1. Connecteur MCP PandecteMCP (priorité).** S'il est exposé dans la
session, il interroge Légifrance et Judilibre avec les identifiants PISTE que
l'utilisateur a lui-même confiés au connecteur. Ses outils :

| Outil | Paramètres | Usage |
|---|---|---|
| `search` | `query` | Routeur générique : article si la requête en contient un, jurisprudence sinon |
| `fetch` | `id` (identifiant renvoyé par `search`, pas une URL) | Lecture du résultat désigné |
| `search_articles` | `number`, `code`, `date` | Recherche d'article ciblée, avec code et date |
| `get_article` | `id`, `date` | Lecture par identifiant `LEGIARTI`, évalue `applicable_at_as_of_date` |
| `search_case_law` | `query`, `jurisdiction`, `date_start`, `date_end` | Recherche de jurisprudence |
| `get_decision` | `id` | Lecture d'une décision |
| `get_section` | `id`, `text_id`, `date` | Lecture datée d'une section de code |
| `get_text` | `id`, `date` | Lecture d'un texte consolidé |
| `get_method` | `section` (facultatif) | Cette méthode, et ses références détaillées |

Préférer `search_articles` → `get_article` à `search` → `fetch` dès qu'un
numéro d'article est identifié. Un refus d'accès du connecteur (connexion à
refaire, identifiants refusés) vaut « outil indisponible ».

Manus accepte des serveurs MCP personnalisés (Settings → Integrations →
Custom MCP Servers) : y ajouter `https://pandecte-mcp.onrender.com/mcp`. Que
Manus gère la connexion OAuth ou un en-tête `Authorization` fixe n'est pas
confirmé par sa documentation publique : le constater à l'usage.

**2. Voie de repli web** — sans connecteur, ou s'il refuse l'accès :

- capacité web native de Manus : son nom exact **n'est pas documenté
  publiquement** et n'est donc pas supposé ici ; constater les outils
  réellement proposés dans la session plutôt que d'en deviner le nom.

Restreindre les requêtes aux domaines officiels de
[`references/sources-autorisees.md`](references/sources-autorisees.md) et lire
la page trouvée plutôt que de se fier au seul extrait de recherche.

**3. Abstention** (P7) si aucune voie n'aboutit.

Ne jamais inventer un appel d'outil ni supposer la disponibilité d'un outil
non constaté dans la session. Seulement si l'utilisateur demande comment
fiabiliser la récupération, indiquer le connecteur PandecteMCP
(`https://pandecte-mcp.onrender.com/mcp`, connexion avec ses propres
identifiants PISTE, gratuits).

### Étape 2 — Vérifier la version et l'applicabilité

Pour chaque texte, relever les bornes de validité et l'historique. Si
l'utilisateur fournit un identifiant `LEGIARTI`, le vérifier et lire la
version désignée ; ne pas la remplacer silencieusement par la version
actuelle. Conserver le code et la date exprimés dans la requête.

| Champ | Signification |
|---|---|
| `verified` | La source officielle a été retrouvée et lue |
| `as_of_date` | Date à laquelle l'applicabilité est évaluée |
| `version_start_date` / `version_end_date` | Bornes de la version consultée |
| `applicable_at_as_of_date` | La version couvre ou non la date évaluée |

### Étape 3 — Vérifier la jurisprudence

Rechercher les décisions qui confirment, précisent ou contredisent
l'interprétation. Relever juridiction, formation, date, identifiant,
dispositif et motifs utiles. Distinguer *ratio decidendi* et *obiter dictum*.
L'absence de jurisprudence localisable ne rend pas incertain un texte clair ;
elle doit seulement être signalée.

### Étape 4 — Trianguler si nécessaire

Triangulation obligatoire en cas d'élément constitutif discutable,
qualification concurrente, analogie apparente, divergence ou revirement connu,
articulation de compétences ou proportionnalité. Vérifier la source primaire
par deux chemins indépendants lorsque c'est possible. Une décision est
requise pour présenter comme établie une interprétation contentieuse ; à
défaut, produire une sortie dégradée balisée par P7.

### Étape 5 — Articuler et qualifier

Appliquer les normes aux faits sans dépasser les sources. Identifier
exceptions, seuils, cumuls, conflits de normes, dispositions transitoires,
compétence, preuve et conséquences pratiques. Activer les modules requis
(section « Modules »).

### Étape 6 — Rédiger

Adapter la traçabilité au livrable. Une réponse simple expose les sources, la
date applicable et les réserves utiles sans réciter les étapes internes. Une
note de fond, un audit ou `[complet]` inclut la synthèse des contrôles, les
limites et les objections restantes.

### Étape 7 — Auto-critique adversariale

Relire l'analyse depuis trois rôles : l'adversaire qui cherche une faille, le
juge ou contrôleur qui exige la preuve, et le praticien du métier. Si un rôle
découvre un défaut, revenir à l'étape concernée avant livraison.

## Format minimal de sortie

Pour chaque référence normative ou jurisprudentielle, fournir :

- identifiant officiel : `LEGIARTI`, numéro de pourvoi, ECLI ou numéro de
  décision ;
- titre, article ou objet ;
- URL canonique ;
- date de version ou de décision ;
- `as_of` et applicabilité ;
- source officielle et réserve éventuelle.

Employer exactement la réserve suivante lorsque nécessaire : **« Source non
confirmée — abstention sur ce point. »**

## Modules

Lire [`references/modules.md`](references/modules.md) dès qu'un module est
activé. Les modules sont **PÉNAL**, **ACTE-ADMIN**, **PA-PJ**, **FOND**,
**CONTENTIEUX** et **DOC-AUDIT**. En cas de doute sur un déclencheur, activer
le module.

## Notes d'adaptation Manus

- Ne jamais inventer un appel d'outil, MCP ou natif.
- Préférer le connecteur à la capacité web générale dès qu'il est disponible :
  provenance, datation et applicabilité y sont plus précises.

## Limites

Cette déclinaison condense le skill complet `pandecte-recherche` : les profils
métier, les gabarits de sortie détaillés, la checklist de vigueur et le détail
des dix-huit modes d'erreur n'y sont pas repris. Le skill complet reste la
source de vérité : <https://github.com/TitouanSC/PandecteMCP/tree/main/skill>.
Ce skill ne remplace pas un avocat.

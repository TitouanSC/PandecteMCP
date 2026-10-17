# `tests/` — évaluation du skill

Deux jeux d'éval complémentaires, des tests unitaires hors réseau, quatre
**contrôles statiques** et des vérifications de déploiement exécutés en CI.

## 1. `eval-modes-erreur.csv` — éval mappée sur les 18 modes d'erreur

Une sonde **par mode d'erreur** du §1 du SKILL (1 à 18), plus des contrôles
transverses :

- **P** — règle de provenance (un identifiant non récupéré n'est jamais inventé) ;
- **L** — voie rapide `[lookup]` (sortie minimale, sans en-tête ni encart) ;
- **Bc / Be / Bs / Bo** — comportement des balises `[complet]` / `[express]` /
  `[syllogisme]` / `[opérationnel]` (ajoutées en v2.4.0) ;
- **N** — profil neutre (v3.0.0) : sans `profil.md`, le skill ne présume aucun
  contexte territorial et pose la question (étape 0 bis) — garde-fou
  anti-régression contre l'ancien contexte codé en dur.

Colonnes : `Mode`, `Intitule`, `Question sonde`, `Comportement attendu`,
`Motifs attendus` (regex, alternation `a|b|c` — une branche suffit),
`Motifs interdits` (regex — aucune occurrence tolérée).

### Lancer l'éval

```bash
# Check-list hors-ligne (aucun appel modèle) — éval manuelle reproductible
python tests/run_eval.py

# Éval réelle via l'API Anthropic (SKILL.md servi en prompt système)
export ANTHROPIC_API_KEY="sk-…"
python tests/run_eval.py --live

# Sous-ensemble de modes
python tests/run_eval.py --live --only 1,5,P

# Verdict par LLM-juge (plus robuste que les regex)
export ANTHROPIC_JUDGE_MODEL="claude-opus-4-8"   # optionnel
python tests/run_eval.py --live --judge
```

Heuristique de réussite par sonde (mode regex, défaut) :

```
PASS ⇔ (motifs attendus vides OU un attendu présent)
       ET (motifs interdits vides OU aucun interdit présent)
```

Avec `--judge`, un **second modèle** note la réponse contre le « Comportement
attendu » et rend un verdict PASS/FAIL sur le fond — cela corrige les **faux
positifs** des regex (le bon mot-clé dans une réponse pourtant fausse).

Le harnais (`run_eval.py`) n'a **aucune dépendance externe** (urllib + csv de
la bibliothèque standard).

### Limites du harnais (à connaître avant d'interpréter un résultat)

- **Le modèle est appelé sans outils.** `--live` envoie `SKILL.md` en système
  et la sonde en message, mais **ne fournit aucun outil** au modèle : il ne
  peut ni exécuter `legifrance.py` ni appeler `web_fetch`. Les sondes de
  provenance (`P`) et d'hallucination (`1`) mesurent donc l'**instinct de
  refus** du modèle, pas la boucle outillée réelle. En production (Claude
  Code), le skill dispose des outils : le comportement peut différer. Une
  validation fidèle de la provenance demanderait un harnais *agentic* (avec
  outils), non couvert ici.
- **Les motifs interdits `LEGIARTI[0-9]{6}` (sondes `1` et `P`) ne valent que
  sans outils.** Sans outil, produire un identifiant officiel ne peut être
  qu'une invention, donc l'interdire est correct. Avec les outils, un
  identifiant **récupéré** est au contraire le comportement attendu : le même
  critère produirait un faux négatif. Ne pas transposer ces interdits à un
  harnais outillé — la provenance s'y juge sur la trace d'appels (l'identifiant
  cité figure-t-il dans un résultat d'outil de la session ?), pas sur son
  absence.
- **Heuristiques regex indicatives** : un échec regex signale une sonde à
  revoir manuellement, pas nécessairement un défaut du skill. `--judge` réduit
  ce bruit mais dépend du jugement d'un modèle (non déterministe).

## 2. `evaluation-copilot-studio.csv` — jeu fonctionnel Copilot Studio

Questions de bout en bout (fond + forme) pour une évaluation qualitative
manuelle dans Copilot Studio (correspondance de mots-clés, comparaison de
signification, qualité générale). Inclut une sonde d'hallucination
(article `L. 9999-1` inexistant).

## 3. Tests unitaires de l'outillage

`test_tools.py` vérifie sans réseau et sans clé PISTE :

- la sélection des environnements Légifrance et Judilibre ;
- la priorité des variables exportées sur le fichier `.env` ;
- le transport JSON et la traduction des erreurs HTTP ;
- OAuth2 Légifrance et la construction des requêtes JSON authentifiées ;
- le cache et la bascule `KeyId` vers OAuth2 de Judilibre ;
- la conservation des huit sous-commandes publiques du CLI.

```bash
python tests/test_tools.py
```

`test_mcp_app.py` couvre le contrat des neuf outils, le masquage des secrets,
les limites de capacité, la configuration de production, les annotations et
une session MCP `stdio` réelle. `test_deployment.py` contrôle le paquet Docker
sans lancer de conteneur.

La connexion par identifiants PISTE est couverte à trois niveaux, sans
réseau ni secret réel :

- `test_sealed.py` — enveloppes chiffrées : confidentialité, intégrité, usage
  lié, expiration, rotation de clé ;
- `test_piste_oauth.py` et `test_connexion.py` — serveur d'autorisation sans
  stockage (enregistrement, code à usage unique, jetons, renouvellement
  glissant) et page « Connexion PISTE » (origine, consentement, refus de
  PISTE, redirection) ;
- `test_piste_end_to_end.py` — la **chaîne complète** en processus, comme un
  client OAuth : découverte, enregistrement, `/authorize`, page de connexion,
  `/token`, appel d'outil avec les identifiants de l'utilisateur,
  renouvellement. Des identifiants « du titulaire » placés dans
  l'environnement doivent être retirés au démarrage et jamais utilisés.

Le CI démarre en plus le serveur Streamable HTTP, vérifie `/health`, initialise
une vraie session sur `/mcp`, découvre les neuf outils, puis construit l'image
Docker. La même sonde HTTP peut viser un déploiement de test :

```bash
python tests/check_mcp_http.py https://domaine.example/mcp
```

`check_oauth_metadata.py` contrôle le point dont dépend l'acceptation du
connecteur ChatGPT : les deux routes RFC 9728 doivent annoncer l'émetteur
**exactement** tel qu'il est configuré, sans normalisation de la barre oblique
finale, et une requête anonyme doit être refusée en `401` avec un challenge
renvoyant vers la bonne route. Aucun jeton n'est présenté, aucun secret n'est
lu. La CI l'exécute sur les deux écritures avec un émetteur factice ; la même
sonde vise la production, l'émetteur attendu étant alors lu dans le document
de découverte :

```bash
python tests/check_oauth_metadata.py https://domaine.example --discover
```

`check_live_tools.py` valide les **outils contre le service déployé**, avec
une vraie clé personnelle `pk1.…` : découverte et annotations, appel effectif de chacun des neuf,
latence des premiers appels Légifrance et Judilibre, lectures avec texte,
datation, provenance, parcours `search → fetch` et article inexistant. Lorsque
les valeurs des clés fournisseur existent localement, la sonde vérifie aussi
qu'elles ne sont pas renvoyées ; sinon elle avertit explicitement que cette
comparaison n'a pas pu être faite. La clé est lue dans `MCP_ACCESS_TOKEN` —
jamais en argument — et n'est ni affichée ni écrite.

```bash
export MCP_ACCESS_TOKEN="pk1.…"
python tests/check_live_tools.py https://pandecte-mcp.onrender.com/mcp
```

Sans clé locale, le workflow manuel **Sonde fonctionnelle**
(`.github/workflows/sonde-fonctionnelle.yml`) exécute le même parcours depuis
GitHub, avec la clé enregistrée dans le secret de dépôt `PANDECTE_PROBE_KEY`.
Il n'est pas planifié : chaque exécution consomme le quota PISTE de cette clé.

`check_service_health.py` est la sonde d'**exploitation courante** : latence
de `/health`, version et mode d'authentification annoncés, plus les contrôles
de métadonnées rejoués. Elle n'appelle aucun outil, donc ne consomme aucun
quota, et n'exige aucun jeton. Sa sortie `--json` tient sur une ligne, faite
pour être accumulée — une dérive de latence ne se voit que sur une série.

```bash
python tests/check_service_health.py https://pandecte-mcp.onrender.com
python tests/check_service_health.py https://pandecte-mcp.onrender.com --json >> surveillance.jsonl
```

La sonde fonctionnelle n'est **pas** jouée en CI : elle exige une clé et
consomme du quota PISTE. Voir `docs/exploitation.md` § 1.

## 4. Contrôles statiques (CI)

Quatre vérificateurs statiques sans dépendance externe, exécutés à chaque push
et chaque PR par `.github/workflows/ci.yml`, aux côtés des sondes HTTP
`check_mcp_http.py` et `check_oauth_metadata.py`. Ils ne jugent pas le skill : ils empêchent
le dépôt de se contredire lui-même.

```bash
python tests/check_links.py         # liens Markdown relatifs
python tests/check_commands.py      # sous-commandes doc ↔ CLI
python tests/check_affirmations.py  # affirmations de la doc ↔ code
python tests/check_plugin.py        # manifeste et adaptateur plugin
python tests/check_vault.py         # maillage du vault (vue graphe)
```

**`check_links.py`** — vérifie que chaque lien relatif Markdown (`[libellé]`
suivi de `(chemin)`) des `.md` pointe vers un fichier existant. Hors
`vault/`, qui utilise des wikilinks Obsidian non résolus en chemins.

**`check_vault.py`** — prend en charge ce que `check_links.py` laisse de côté :
le maillage de wikiliens du vault, lu par la vue graphe. Quatre invariants —
section `## Liens (maillage Graphify)` sur chaque note, aucune note orpheline
(sans lien entrant), aucun cul-de-sac (sans lien sortant), aucun lien non
résolu. Un auto-lien ne rend pas une note atteignable et ne compte pas comme
lien entrant ; un wikilien écrit en `code` n'est pas un lien, Obsidian ne
l'interprétant pas.

La tolérance aux liens non résolus **n'est pas une liste dans le
vérificateur** : elle est dérivée de la section « Fichiers supprimés (remplacés
par agrégats) » de `index-pandecte-recherche.md`, où ces notions sont écrites
en `code`. Déclarer une notion agrégée dans l'index suffit à la faire accepter ;
l'oublier fait échouer le contrôle. `tests/test_check_vault.py` éprouve chaque
invariant sur un vault de test qui le viole — un vérificateur qui passe toujours
ne vérifie rien.

Il vise une dérive constatée le 5 septembre 2026 : deux notes sur treize
portaient une section de liens, trois agrégats n'avaient aucun lien sortant, et
deux notes de version aucun lien entrant. Une note isolée existe mais aucun
chemin de lecture n'y mène.

**`check_commands.py`** — compare les sous-commandes citées dans la
documentation à celles réellement exposées par `build_parser()` de
`legifrance.py`, dans les deux sens : commande **citée mais inexistante**, et
commande **exposée mais jamais documentée**. La liste de référence est
extraite du parser par introspection argparse, jamais par regex sur le source
— sans quoi elle divergerait à son tour. Le balayage ne lit que le contexte
de code (blocs clôturés et spans `` `…` ``), la prose étant hors champ.

Exclusions : `vault/` (notes historiques) et `skill/CHANGELOG.md` (journal
immuable, qui cite légitimement des commandes retirées depuis).

**`check_affirmations.py`** — même principe que `check_commands.py`, appliqué
aux affirmations chiffrées de la prose. Il confronte au code, qui fait foi :
les versions de plugin citées (`v0.x.y`), les valeurs d'annotations d'outils
citées (`openWorldHint`, `readOnlyHint`, `destructiveHint`) et les variables
d'environnement `MCP_*` mentionnées. Il vérifie aussi que le dossier de
soumission annonce les mêmes annotations que le serveur.

Il vise une classe d'erreur constatée trois fois lors de l'audit du 1er
septembre 2026 : *un document affirme une propriété que le code contredit*,
chaque affirmation restant plausible isolément faute de recoupement. Le
contrôle se déclenche dans les deux sens — documentation périmée comme dérive
du serveur.

Exclusion : `docs/roadmap-chatgpt-plugin.md`, journal daté qui doit pouvoir
citer une valeur d'époque. Une entrée devenue fausse y reçoit une mention de
péremption, à la main — même logique que `skill/CHANGELOG.md` ci-dessus.

**`check_plugin.py`** — vérifie le manifeste, son identité, son interface, le
point de découverte `skills/pandecte-recherche/` et la présence intacte du
skill historique `skill/SKILL.md`. Il interdit aussi de déclarer une app ou un
serveur MCP sans fichier compagnon.

Il applique en outre les **limites publiées par OpenAI** pour la soumission —
longueurs de champs, liste des catégories, nombre et longueur des prompts et
des capacités, quatre URL publiques, notes de version, justification par
annotation — et la règle de version retenue : *le manifeste du plugin suit le
serveur MCP*, le skill gardant sa propre ligne éditoriale.

Enfin, il **valide `chatgpt-app-submission.json` contre le schéma officiel**,
dont une copie est embarquée dans `fixtures/`. Cette validation est facultative :
elle demande `jsonschema`, qui arrive avec le SDK MCP. Quand il manque, son
absence est dite explicitement — un contrôle muet se lit à tort comme un
contrôle réussi. Rafraîchir la copie depuis l'URL déclarée lors des revues.

> **Pourquoi cette validation existe.** Le fichier déclarait une URL de schéma
> obsolète (`apps-sdk` au lieu de `plugins`) et **échouait à la validation
> officielle**. Le défaut n'a été vu qu'en téléchargeant le schéma à la main,
> une fois. Rien, dans le dépôt, ne l'aurait signalé.

> **Pourquoi ce contrôle existe.** La v3.1.0 a dû réparer la suppression
> accidentelle de `ceta` et `constit` par une PR qui n'avait touché **aucun**
> `.md` : pendant ce temps, quatre fichiers prescrivaient au modèle des
> commandes inexistantes, et deux commandes ajoutées (`decision`, `taxonomy`)
> n'étaient documentées nulle part, donc inutilisables. Aucun contrôle
> existant ne pouvait le voir. Un garde-fou dont on a oublié le motif finit
> désactivé : voilà le motif.

---

Voir aussi la **revue annuelle** (`skill/references/maintenance.md` §7), qui
fait tourner quatre requêtes témoins après chaque mise à jour méthodologique.

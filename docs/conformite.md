# État des contrôles — serveur MCP public

Revue sur pièces du serveur MCP hébergé, de ses garde-fous et de son rapport
aux fournisseurs de données. Établi le 18 octobre 2026, sur l'état du dépôt à
cette date. Il remplace la revue du projet d'origine, faite pour une autre
architecture (clés du titulaire, émetteur OAuth externe).

Ce document **n'est pas une attestation de conformité**. Le plan d'audit
([audit-securite.md](audit-securite.md)) en organise la vérification ; le
registre CGU ([obligations-cgu.md](obligations-cgu.md)) en porte l'analyse
contractuelle.

Le principe qui structure tout ce qui suit : **le service n'a aucune clé PISTE
à lui.** Chaque utilisateur consulte les API avec ses propres identifiants,
qu'il confie au service le temps de chaque appel. Chaque mesure ci-dessous
existe pour que cette confiance soit tenable.

---

## 1. Secrets

| Point | État | Où c'est établi |
|---|---|---|
| Aucun secret suivi par Git | ✅ | `.gitignore` exclut `.env` et `.env.*` (sauf `.env.example`) et l'état local de Wrangler ; recherche de motifs et des valeurs réelles connues dans tout l'historique avant chaque push |
| Aucun identifiant PISTE sur le serveur | ✅ | Retirés du processus au démarrage, et démarrage refusé en production s'ils sont présents (`test_owner_credentials_are_removed_at_startup`, `test_production_errors_never_echo_values`) |
| Identifiants des utilisateurs jamais stockés ni journalisés | ✅ | Scellés dans les jetons ; `test_secrets_never_reach_the_log`, `test_credentials.py` |
| Seul secret de l'instance : la clé de scellement | ✅ | `PANDECTE_SEAL_KEY`, exigée en production, rotation par `PANDECTE_SEAL_KEY_PREVIOUS` |
| Secrets absents du manifeste MCP | ✅ | `check_plugin.py` échoue si `.mcp.json` nomme une variable sensible |
| Secrets masqués dans les erreurs | ✅ | Identifiants de la requête masqués avant toute réponse ou journal (`test_server_error_masks_request_credentials`) |
| Détail amont réservé au journal | ✅ | Le client reçoit un message public et un identifiant de corrélation ; le détail va au journal sous cet identifiant |

## 2. Authentification

| Contrôle | État |
|---|---|
| Le serveur est son propre serveur d'autorisation (OAuth 2.1, PKCE S256, enregistrement dynamique) | ✅ Protocole porté par le SDK MCP |
| Jetons chiffrés et authentifiés, liés à leur usage, expirants | ✅ AES-256-GCM ; accès 1 h, renouvellement 90 jours glissants, code 5 min |
| Jeton lié à son client et à la ressource MCP | ✅ Ressource étrangère refusée ; `validate_token_resource` actif |
| Code d'autorisation à usage unique | ✅ Par instance ; PKCE en complément |
| Identifiants vérifiés auprès de PISTE avant émission d'un code | ✅ Refus explicite si PISTE les rejette |
| Page de connexion protégée | ✅ Origine contrôlée, CSP à nonce, aucun cadre, destinataire affiché |
| Passerelle anonyme impossible en production | ✅ `validate_public()` exige `MCP_AUTH_MODE=piste` |

Ces contrôles sont couverts par `test_sealed.py`, `test_piste_oauth.py`,
`test_connexion.py` et `test_piste_end_to_end.py` (chaîne complète, transport
compris).

## 3. Limitation et robustesse

| Mesure | Valeur par défaut | Rôle |
|---|---|---|
| Concurrence maximale | 8 | Protège l'instance |
| Débit d'instance | 120 appels/min | Protège l'instance |
| Débit par adresse IP | 30 appels/min | Limite les abus ; IP lue dans `cf-connecting-ip` sur Render |
| Attente en file | 2 s | Refuse vite plutôt que d'accumuler |
| Taille maximale de requête | 1 Mio | Borne l'entrée |
| Délai des appels sortants | 30 s | Borne la sortie |
| Reprise sur erreur transitoire | 2 au plus, budget 8 s | Absorbe un `429`/`5xx` ponctuel des API amont ; `Retry-After` respecté, aucun autre `4xx` rejoué |

Chaque utilisateur consomme son propre quota PISTE : aucun quota partagé n'est
à protéger. Un dépassement produit un message explicite, distinct d'une erreur
de source.

## 4. Journalisation et vie privée

Le journal métier (`pandecte.mcp`) reste en `INFO` même lorsque l'image tourne
en `WARNING`. Chaque appel d'outil y porte l'outil, l'issue, la durée, l'usage
du cache et une empreinte tronquée dérivée des identifiants de l'utilisateur,
non réversible et renouvelée à chaque redémarrage. Chaque connexion n'y laisse
que son issue. Jamais d'identifiant, de jeton, d'argument ni de résultat.

## 5. Dépendances et image

`mcp`, `PyJWT[crypto]` et `cryptography` sont **épinglés à une version
exacte**. L'image de base est épinglée par digest et ses paquets système mis à
niveau pendant le build ; le conteneur tourne sans privilège et **sans
disque**. La CI produit un SBOM CycloneDX, audite les dépendances Python
(`pip-audit --strict`), inventorie les CVE élevées et critiques de l'image et
bloque celles disposant d'un correctif (Trivy).

## 6. Rapport aux fournisseurs

**Clés de l'utilisateur, en son nom.** Le service agit comme intermédiaire
technique sur mandat de l'utilisateur, qui a lui-même accepté les CGU de PISTE.
L'interprétation de III.3 (Légifrance) et XI.C (Judilibre) dans ce modèle
n'est pas confirmée par les producteurs : voir le registre CGU, § 4.

**Aucune prétention d'officialité.** Les conditions d'utilisation portent une
clause de non-affiliation explicite.

**Vérifiabilité.** La méthode du skill impose de lire la source avant de la
citer, de signaler un échec d'accès comme une source non vérifiée, et de dater
explicitement la version consultée (`as_of_date`, `date_basis`). Le cache
signale ses réponses (`from_cache`) avec leur date de récupération réelle.

**Licences.** Les données récupérées restent soumises à la Licence Ouverte 2.0
et aux conditions de réutilisation de Légifrance et Judilibre. Le code et le
skill sont sous CC BY-SA 4.0.

---

## Points à surveiller

1. **Clé de scellement.** Seul secret de l'instance : comptes Render et GitHub
   à protéger par double authentification.
2. **Enregistrement dynamique ouvert.** Surveiller dans le journal les
   connexions vers des domaines inconnus ; une liste blanche reste possible.
3. **Épinglage.** Une version figée doit être suivie : revue régulière des
   mises à jour du SDK MCP, de PyJWT et de `cryptography`.
4. **Journaux de l'hébergeur.** Les journaux d'accès de Render et de Cloudflare
   (adresses IP, en-têtes) sont hors du journal métier et relèvent de leurs
   propres politiques.
5. **Métadonnées OAuth.** À revérifier après tout changement d'adresse —
   `python tests/check_oauth_metadata.py <url> --issuer <url>`.

# Plan d'audit sécurité — serveur MCP PandecteMCP

─────────────────────────────────────────────
Date d'analyse           : 18/10/2026
Date(s) de référence     : 18/10/2026
Date des faits           : sans objet
Date d'action / analyse  : 18/10/2026
Champ territorial        : France / service internet
Régime juridique primaire: sécurité, données personnelles et contrats d'API
Niveau d'exigence        : note de fond
Mode opératoire          : B complet
─────────────────────────────────────────────

Ce document est un **plan vivant**, pas une attestation. Il distingue ce qui
est **prouvé par un test du dépôt** (rejoué à chaque CI), ce qui a été
**constaté** sur l'instance hébergée à une date donnée, et ce qui reste
**ouvert**. Il remplace le plan d'audit du projet d'origine, conçu pour une
autre architecture (émetteur OAuth externe, clés du titulaire) ; celui-ci
reste consultable dans l'historique git.

## 1. Architecture

```text
Assistant (claude.ai, ChatGPT, Claude Code…)
   │  OAuth 2.1 + PKCE (DCR)            ou en-tête « Bearer pk1.… »
   ▼
Cloudflare (bord de Render, TLS) → Render → conteneur PandecteMCP (sans disque)
   │  identifiants PISTE de l'utilisateur, le temps de l'appel
   ├→ PISTE → DILA / Légifrance
   └→ PISTE → Cour de cassation / Judilibre
```

Le serveur est **son propre serveur d'autorisation** et **ne stocke rien** :
identifiant de client, demande de connexion, code, jeton d'accès et jeton de
renouvellement sont des enveloppes AES-256-GCM transportées par le client. Il
ne détient **aucune** clé PISTE. Les huit outils sont en lecture seule
(`readOnlyHint=true`, `openWorldHint=false`) ; les textes juridiques reçus
sont des données non fiables (`content_trust: untrusted_source_data`), jamais
des instructions.

## 2. Actifs et menaces

| Actif | Menace principale | Contrôle |
|---|---|---|
| Identifiants PISTE des utilisateurs | Fuite par le service (journal, réponse, page, disque) | Jamais stockés ni journalisés ; scellés dans les jetons ; masqués dans les erreurs |
| Clé de scellement `PANDECTE_SEAL_KEY` | Vol : déchiffrement de tous les jetons | Seul secret de l'instance, variable de l'hébergeur ; rotation documentée (`incident-response.md`) |
| Jetons d'un utilisateur | Rejeu, falsification, usage par un autre client | AES-GCM authentifié, usage lié, expiration, lien au client |
| Page « Connexion PISTE » | Hameçonnage par un client enregistré à cette fin ; soumission inter-sites | Destinataire affiché et signalé s'il est inconnu ; contrôle d'origine ; CSP |
| Quota PISTE de l'utilisateur | Abus par un tiers ou emballement | Clés de l'utilisateur seul ; limite par IP ; plafond d'instance |
| Disponibilité de l'instance | Saturation | Limite par IP, plafond et concurrence d'instance, protection de Cloudflare |
| Décisions Judilibre | Redistribution d'une décision à retirer | Liste de retrait vérifiée à chaque lecture, cache compris |

## 3. Contrôles prouvés par les tests

| ID | Contrôle | Preuve (tests du dépôt) |
|---|---|---|
| T1 | Enveloppes illisibles pour le porteur, infalsifiables, liées à leur usage, expirantes, avec rotation | `test_sealed.py` (13 tests, dont `test_content_is_not_readable_by_the_carrier`, `test_tampering_is_detected`, `test_purpose_is_bound`) |
| T2 | Client enregistré scellé ; client forgé ou d'une autre instance refusé | `test_piste_oauth.py` : `test_registration_returns_a_sealed_client_id`, `test_unknown_or_forged_client_is_none` |
| T3 | Code à usage unique, lié à son client ; ressource étrangère refusée | `test_code_is_single_use`, `test_code_belongs_to_its_client`, `test_foreign_resource_is_refused` |
| T4 | Jetons non interchangeables, liés au client, expirants ; renouvellement glissant | `test_tokens_are_not_interchangeable`, `test_refresh_token_belongs_to_its_client`, `test_refresh_is_silent_and_sliding` |
| T5 | Page de connexion : destinataire affiché, domaine inconnu signalé, soumission inter-sites refusée, consentement exigé, identifiants jamais renvoyés ni journalisés | `test_connexion.py` (11 tests) |
| T6 | Parcours OAuth complet, appel d'outil avec les seuls identifiants de l'utilisateur ; identifiants du titulaire retirés au démarrage | `test_piste_end_to_end.py` : `test_full_oauth_flow_uses_only_the_user_keys`, `test_owner_credentials_are_removed_at_startup` |
| T7 | Sans jeton valide, aucun outil ne s'exécute | `test_without_a_valid_token_nothing_runs` |
| T8 | Identifiants isolés par requête et par fil d'exécution, masqués dans toute erreur | `test_credentials.py` (13 tests) |
| T9 | Page « Clé personnelle » : aucun champ nommé, aucun formulaire, aucune connexion sortante | `test_cle.py` |
| T10 | Limite par IP exacte, indépendante par adresse, sûre en concurrence ; IP cliente non falsifiable par un préfixe | `test_quotas.py`, `test_http_guard.py` |
| T11 | Production refusée sans clé de scellement, avec identifiants PISTE présents, ou sans authentification | `test_mcp_app.py` (`PisteModeSettingsTests`, `RuntimeSafetyTests`) |
| T12 | Hôtes et origines admis : `localhost` et le nom public seulement | `test_mcp_app.py` (`TransportSecurityTests`) |
| T13 | Dépendances sans CVE connue ; image sans CVE élevée ou critique corrigeable | CI : `pip-audit --strict` (SBOM CycloneDX archivé) et Trivy |

## 4. Constats sur l'instance hébergée

| Date | Constat |
|---|---|
| 17/10/2026 | Connexion et appels réels depuis claude.ai, ChatGPT et Claude Code ; secret de l'utilisateur absent du journal |
| 17/10/2026 | Métadonnées OAuth cohérentes, refus anonyme en 401 (`check_oauth_metadata.py`) |
| 17/10/2026 | Conteneur sous l'utilisateur `app` ; refus de démarrer sans clé ou avec identifiants PISTE (image construite et sondée localement) |
| 17/10/2026 | IP cliente lue dans `cf-connecting-ip` ; page de diagnostic refermée |
| 18/10/2026 | Sonde de disponibilité conforme (`check_service_health.py`) |

## 5. Points ouverts

| ID | Sévérité | Point | Suite |
|---|---|---|---|
| O1 | Moyenne | **Enregistrement dynamique ouvert** : n'importe qui peut enregistrer un client avec une adresse de retour à lui et envoyer un lien de connexion à une victime (hameçonnage). | Atténué par l'affichage du destinataire et l'avertissement pour un domaine inconnu ; envisager une liste blanche de domaines si un abus est constaté |
| O2 | Moyenne | **Pas de révocation individuelle** d'un jeton (aucun stockage). | Révocation par l'utilisateur (Client Secret) ou de tous (rotation de clé) ; documenté |
| O3 | Moyenne | **Terminaison TLS chez Cloudflare** : identifiants en clair à l'intérieur de HTTPS sur la page de connexion. | Inhérent à l'hébergeur ; mentionné dans la politique de confidentialité ; alternative d'auto-hébergement |
| O4 | Basse | **Code réutilisable sur une autre instance** pendant 5 minutes si plusieurs instances partagent la clé (mémoire des codes par instance). | PKCE le rend inutilisable sans vérificateur ; une seule instance aujourd'hui |
| O5 | Basse | **Aucun test d'intrusion externe** ni revue tierce. | À programmer avant une diffusion large |
| O6 | Information | Interprétation des CGU sur les clés confiées (III.3 / XI.C). | Voir [obligations-cgu.md](obligations-cgu.md) § 4 |

## 6. Sévérité et clôture

- **Critique** : fuite d'identifiants ou de la clé de scellement, exécution
  d'outil sans jeton valide. Correction et rotation immédiates.
- **Élevée** : contournement d'un contrôle de T1 à T7. Correction avant tout
  nouveau déploiement.
- **Moyenne / basse** : consignée ici, avec une décision datée.

Un point n'est clos que par un test de non-régression dans le dépôt, ou par une
décision écrite et datée dans ce document.

## Étape 7 — Auto-critique adversariale

- Un attaquant chercherait d'abord la clé de scellement : elle n'existe que
  dans l'environnement de l'hébergeur, mais un compte Render ou GitHub
  compromis y donne accès — d'où la double authentification de ces comptes,
  hors du périmètre de ce dépôt.
- Les tests prouvent le comportement du code, pas celui des clients : un
  client qui journaliserait ses jetons exposerait des enveloppes chiffrées,
  pas des identifiants en clair.
- L'avertissement de domaine inconnu suppose que l'utilisateur le lise.

─────────────────────────────────────────────
Modules activés                       : [DOC-AUDIT]
Modules non activés                   : [PÉNAL, ACTE-ADMIN, PA-PJ, FOND, CONTENTIEUX]
Niveau de confiance global            : modéré
Sources informelles signalées         : aucune
Limites de la recherche               : aucun test d'intrusion externe
─────────────────────────────────────────────

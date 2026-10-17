# Registre des obligations — Légifrance et Judilibre

─────────────────────────────────────────────
Date d'analyse           : 18/10/2026 (révision du registre du 31/08/2026)
Date(s) de référence     : 15/12/2022 (Légifrance) / 06/01/2022 (Judilibre)
Date des faits           : sans objet
Date d'action / analyse  : 18/10/2026
Champ territorial        : France
Régime juridique primaire: contrats d'accès API et réutilisation de données
Niveau d'exigence        : note de fond
Mode opératoire          : B complet
─────────────────────────────────────────────

**Modèle d'accès examiné.** Le service hébergé PandecteMCP ne détient aucune
clé PISTE. Chaque utilisateur crée sa propre application PISTE, accepte
lui-même les CGU, puis confie ses identifiants au service, qui consulte les API
**en son nom** (mandat, voir les [conditions d'utilisation](terms-of-use.md),
art. 3). Les identifiants voyagent chiffrés dans les jetons conservés par
l'assistant de l'utilisateur ; le service ne les stocke ni ne les journalise.
Le titulaire des clés, et donc l'« Utilisateur » au sens des deux CGU, reste
la personne qui les a créées.

## 1. État des sources

| Source | État vérifié au 18/10/2026 | Empreinte SHA-256 |
|---|---|---|
| CGU de l'API Légifrance, V1.0 du 15/12/2022 (`CGU_Legifrance_API_VF_15-12-2022.pdf`, 9 pages) | Texte intégral obtenu et lu | `9db9cde0dac918721eac7508f76ea47ebfd0b2a7822db3ad9b41bb11629851fd` (export du 06/01/2023, servi au 18/10/2026) |
| Même document, autre export PDF | Texte extrait **identique** au caractère près | `1545c57d9cf0523e8eb17f5fd86c9538e168d503082b4e741907fd542894fa41` (export du 18/12/2023, archivé lors d'une revue précédente) |
| CGU Judilibre du 06/01/2022 (`CGU_open_data_V8.pdf`, 12 pages) | Texte intégral obtenu et lu | `73f99f811475a0f9c7eb3e18ff431c37a41672e4c549fce64415eae71a713554` |
| Licence Ouverte 2.0 | Texte officiel Etalab | — |
| PDF `DILA_Legifrance_Beta_v2.pdf` (2020) | **Historique, supersédé** | — |

Les deux empreintes Légifrance correspondent à deux exports PDF du même texte ;
une empreinte différente lors d'une prochaine revue impose de comparer le
**texte extrait**, pas seulement le fichier.

## 2. Contrôles communs

| ID | Contrôle appliqué au service | Judilibre 2022 | Légifrance 2022 | État technique |
|---|---|---|---|---|
| C1 | Clés réservées à l'application de leur titulaire, jamais publiques ni divulguées à un tiers | XI.C | III.3 | Clés de l'utilisateur, chiffrées, jamais stockées ni journalisées ni renvoyées ; **risque résiduel**, voir § 4 |
| C2 | Sécurité des identifiants et de l'environnement d'exécution | XI.C / XI.E | III.3, V.2 | Conteneur non-root sans disque ; scellement AES-256-GCM ; CSP stricte sur les pages |
| C3 | En cas de compromission : réinitialiser les identifiants et avertir la DILA (Légifrance) ou la Cour de cassation (Judilibre), et/ou l'AIFE | XI.E | V.3 | Révocation par l'utilisateur (Client Secret) ; procédure de l'exploitant dans `incident-response.md` |
| C4 | Respecter les quotas et leurs changements | XI.D | IV.3 | Chaque utilisateur consomme son propre quota ; limite de débit par IP en plus |
| C5 | Usage licite, responsabilité de l'utilisateur | XII | V.1, VI.2 | Conditions publiques (art. 5 et 7) |
| C6 | Ne pas altérer ni dénaturer, mentionner la source et la date de mise à jour | V / XIII + LO 2.0 | V.1 + LO 2.0 (IX) | Provenance structurée, date de récupération, `from_cache` |
| C7 | Ne pas transformer une panne en vérification réussie | XI.D | IV.1, VI.1 | Erreur « source officielle non vérifiée » |
| C8 | Suspension ou résiliation possible de l'accès | XII | VII.1 | Dégradation documentée, aucune clé de secours |

## 3. Judilibre — affirmations vérifiées

| ID | Nature | Règle | Contrôle du service |
|---|---|---|---|
| J1 | Contractuelle/légale | Ne pas profiler magistrats ou membres du greffe à partir de leur identité | Fonction absente et usage interdit |
| J2 | Contractuelle/légale | Ne pas réidentifier les personnes occultées ou pseudonymisées | Usage interdit ; aucune base de rapprochement |
| J3 | **Recommandation forte** | Section VII : le réutilisateur est **invité** à signaler une réidentification manifeste persistante à `anonymisation.sder.courdecassation@justice.fr` | Canal et runbook proposés ; ne pas présenter comme engagement contractuel |
| J4 | **Obligation contractuelle** | Section IX : transmettre sans délai une demande relative à un défaut d'occultation des nom/prénoms et effectuer une occultation socle provisoire | Retrait complet temporaire via `MCP_JUDILIBRE_SUPPRESSED_IDS`, relais immédiat, levée après correction amont |
| J5 | Compétence exclusive | Les demandes d'occultation/levée relèvent de la Cour de cassation ; le réutilisateur n'en décide pas seul | Orientation vers `occultations.courdecassation@justice.fr` ; aucune altération autonome |
| J6 | Contractuelle | Juridiction, formation, siège et date du prononcé restent indissociables de la décision | Champs renvoyés lorsqu'ils existent |
| J7 | Contractuelle | Mention « base Open Data de la Cour de cassation » et date de dernière mise à jour ; recommandation 72 h pour une base dérivée | Source exacte + date amont si fournie + date de récupération ; cache de 24 h au plus, aucune base dérivée persistante |
| J8 | Information RGPD | Accès/rectification du traitement Judilibre auprès du SDER | Renvoi dans la politique de confidentialité |

### Mesure conservatoire J4

Le service ne doit pas inventer une occultation ni modifier la décision. Dès
qu'un signalement crédible vise une décision :

1. ajouter son identifiant à `MCP_JUDILIBRE_SUPPRESSED_IDS` sur l'hébergeur ;
2. redémarrer et vérifier que recherche et lecture ne la redistribuent plus
   (le cache vérifie la liste à chaque lecture) ;
3. transmettre sans délai le signalement à la Cour de cassation selon
   `incident-response.md` ;
4. conserver une preuve privée minimale, sans recopier les données exposées ;
5. retirer l'identifiant uniquement après correction de la source et contrôle.

## 4. Point à arbitrer — clés confiées au service

III.3 (Légifrance) et XI.C (Judilibre) disposent, dans les mêmes termes, que
les clés d'authentification sont **strictement réservées à l'application** de
leur titulaire et ne doivent être ni rendues publiques ni divulguées à un
tiers. Le service reçoit pourtant les clés de ses utilisateurs.

Lecture retenue : l'utilisateur ne divulgue pas ses clés, il les confie à un
**intermédiaire technique** qui agit pour son compte, sur sa demande, le temps
de chaque requête, sans les conserver — de la même façon qu'il les confierait
à un logiciel hébergé de son choix. Cette lecture **n'est pas confirmée** par
la DILA ni par la Cour de cassation. Mesures en conséquence :

- avertissement explicite citant III.3 et XI.C avant toute saisie (pages
  « Connexion PISTE » et « Clé personnelle ») ;
- clause de mandat et responsabilité de l'utilisateur dans les conditions
  d'utilisation ;
- alternative sans transmission documentée : instance personnelle ou mode
  local ;
- garanties techniques : aucune conservation, chiffrement des jetons,
  révocation par l'utilisateur.

Il reste possible de demander une position écrite à la DILA (les CGU, § II,
renvoient aux mentions légales de Légifrance) et à la Cour de cassation ; l'écrire « conforme aux CGU » sans cette
position serait excessif.

## 5. Points restant à vérifier

- position de la DILA et de la Cour de cassation sur le modèle d'intermédiaire
  (§ 4) ;
- valeurs effectivement présentes dans les réponses Judilibre pour siège et
  date de mise à jour ;
- délai de rétention et contenu exact des journaux de l'hébergeur ;
- exercice chronométré du retrait J4.

## Sources primaires

- [Catalogue PISTE — Légifrance](https://piste.gouv.fr/api-catalog-sandbox?filter=legifrance)
- [CGU de l'API Légifrance du 15 décembre 2022](https://piste.gouv.fr/images/cgu/CGU_Legifrance_API_VF_15-12-2022.pdf)
- [CGU Judilibre du 6 janvier 2022](https://piste.gouv.fr/images/cgu/CGU_open_data_V8.pdf)
- [Licence Ouverte 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence)

## Étape 7 — Auto-critique adversariale

- Le confrère adverse soutiendrait que « divulguées à un tiers » vise toute
  communication hors de l'application du titulaire, intermédiaire compris :
  l'argument est sérieux, d'où le § 4 et l'alternative d'auto-hébergement.
- Le retrait complet d'une décision réduit la diffusion mais ne remplace pas la
  transmission sans délai à la Cour de cassation.
- Les champs absents d'une réponse Judilibre ne doivent pas être inventés.

─────────────────────────────────────────────
Modules activés                       : [DOC-AUDIT]
Modules non activés                   : [PÉNAL, ACTE-ADMIN, PA-PJ, FOND, CONTENTIEUX]
Niveau de confiance global            : modéré
Sources informelles signalées         : aucune
Limites de la recherche               : interprétation de III.3 / XI.C non confirmée par les producteurs
─────────────────────────────────────────────

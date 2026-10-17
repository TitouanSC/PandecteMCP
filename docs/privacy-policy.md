# Politique de confidentialité — PandecteMCP

Dernière mise à jour : 18 octobre 2026

## Responsable et contact

Le service **PandecteMCP** (serveur MCP hébergé à l'adresse
`https://pandecte-mcp.onrender.com/mcp`) est édité, à titre personnel et non
commercial, par le mainteneur du dépôt public
[`TitouanSC/PandecteMCP`](https://github.com/TitouanSC/PandecteMCP).

Pour une question relative à la confidentialité, utiliser la
[page de support](https://github.com/TitouanSC/PandecteMCP/issues) en
demandant, si nécessaire, un canal privé. Ne jamais publier d'identifiant
PISTE, de jeton, de donnée personnelle ou de pièce confidentielle dans une
issue publique.

## Objet du service

Le service recherche et lit, à la demande de l'utilisateur, des articles de
droit français et des décisions de justice provenant de Légifrance et de
Judilibre, **avec les identifiants PISTE de l'utilisateur**. Il fonctionne en
lecture seule et ne crée, ne modifie ni ne supprime aucune donnée dans ces
sources.

## Données traitées

- **Identifiants PISTE de l'utilisateur** (Client ID et Client Secret, et le
  cas échéant KeyId). Saisis sur la page « Connexion PISTE », ils sont vérifiés
  auprès de PISTE, puis **chiffrés** (AES-256-GCM) dans les jetons remis à
  l'assistant de l'utilisateur, qui les conserve et les renvoie à chaque
  requête. Le service ne les écrit sur aucun support, ne les journalise jamais
  et ne les déchiffre que le temps de chaque consultation. Avec une clé
  personnelle `pk1`, ils sont transmis encodés à chaque requête, avec les
  mêmes garanties.
- **Requêtes juridiques** : termes de recherche, filtres et identifiants de
  textes ou de décisions fournis par l'assistant.
- **Résultats publics** : textes et métadonnées renvoyés par Légifrance ou
  Judilibre. Ils peuvent être conservés en **mémoire vive** (cache commun :
  6 heures pour les textes, 24 heures pour les décisions, jamais sur disque) pour éviter des appels répétés ; ce
  cache ne contient aucune donnée propre à un utilisateur.
- **Métadonnées techniques** : adresse IP (utilisée en mémoire, le temps d'une
  minute, pour limiter le débit par adresse), en-têtes HTTP, horodatages,
  identifiant de session MCP éphémère.

Les décisions diffusées par Judilibre sont pseudonymisées avant leur mise à
disposition, mais peuvent encore contenir des données personnelles présentes
dans une décision publique. L'utilisateur ne doit pas transmettre de données
personnelles sans nécessité pour sa recherche. Constituer un profil de
magistrat ou de membre du greffe à partir des décisions diffusées est interdit
(voir les [conditions d'utilisation](terms-of-use.md), art. 5).

## Finalités et bases juridiques

Les identifiants, requêtes et résultats sont traités pour exécuter la
consultation demandée par l'utilisateur, en son nom (voir le mandat, art. 3 des
conditions d'utilisation) : ce traitement est nécessaire à la fourniture du
service sollicité. Les métadonnées techniques strictement nécessaires à la
sécurité, à la prévention des abus et au diagnostic relèvent de l'intérêt
légitime de l'éditeur à exploiter un service sûr et disponible.

Le service n'utilise pas les requêtes pour la publicité, le profilage des
utilisateurs ou l'entraînement d'un modèle.

## Destinataires et prestataires

Selon l'opération demandée, les données nécessaires sont transmises :

- au **fournisseur de l'assistant** choisi par l'utilisateur (par exemple
  Anthropic pour Claude, OpenAI pour ChatGPT), qui appelle le serveur MCP et
  conserve les jetons chiffrés ; ses propres traitements sont régis par ses
  conditions ;
- à **Render Services, Inc.**, hébergeur du serveur, déployé dans la région de
  Francfort ;
- à **Cloudflare, Inc.**, par lequel Render achemine tout le trafic de ses
  services : Cloudflare termine le chiffrement HTTPS et voit donc passer les
  requêtes, réponses et jetons (lesquels restent chiffrés par le service), ainsi
  que les identifiants saisis sur la page de connexion ;
- à **PISTE / DILA** pour les recherches Légifrance, avec les identifiants de
  l'utilisateur ;
- à **PISTE et à la Cour de cassation** pour les recherches Judilibre, avec les
  identifiants de l'utilisateur.

Render et Cloudflare sont des prestataires établis aux États-Unis ; leurs
accords de traitement des données décrivent les garanties contractuelles
applicables aux transferts.

## Conservation

Le service ne possède **aucune base de données ni aucun disque** : il ne
conserve ni identifiant, ni jeton, ni requête, ni compte utilisateur. Son
journal n'enregistre que :

- pour chaque appel d'outil : le nom de l'outil, l'issue, la durée, l'usage du
  cache et une **empreinte tronquée** dérivée des identifiants de
  l'utilisateur. Cette empreinte est une **donnée pseudonymisée** : elle ne
  permet pas de retrouver les identifiants, et elle change à chaque redémarrage
  du service ;
- pour chaque connexion : sa seule issue (réussite, refus, annulation).

Les arguments, résultats, identifiants, jetons et adresses e-mail sont exclus
du journal. L'hébergeur conserve ses propres journaux techniques selon le
forfait du compte (actuellement 7 jours pour un espace Hobby selon la
documentation Render). Aucun flux de journaux vers un tiers n'est prévu.

L'historique de la conversation et les jetons de connexion sont conservés
séparément par le fournisseur de l'assistant, selon les paramètres du compte de
l'utilisateur. L'utilisateur peut les rendre inutilisables à tout moment en
déconnectant le connecteur ou en régénérant son Client Secret sur PISTE.

## Droits

Lorsque le RGPD ou la loi Informatique et Libertés s'applique, une personne peut
demander l'accès, la rectification, l'effacement ou la limitation de ses données
et, selon la base juridique, s'opposer au traitement. Elle peut également saisir
la [CNIL](https://www.cnil.fr/).

Le service ne conservant aucun compte ni aucune donnée nominative, et son
journal ne portant qu'une empreinte non réversible, l'éditeur ne peut
généralement pas retrouver les données d'une personne déterminée ; passé le
délai de rétention de l'hébergeur, aucune entrée ne subsiste. Les demandes
portant sur les jetons conservés par un assistant relèvent de son fournisseur.
Les demandes d'occultation ou de levée d'occultation d'une décision Judilibre
relèvent exclusivement de la Cour de cassation et peuvent être adressées à
`occultations.courdecassation@justice.fr` ; les droits portant sur le
traitement Judilibre relèvent du SDER de la Cour de cassation.

## Sécurité et limites

Les échanges utilisent HTTPS. Les jetons sont chiffrés et authentifiés
(AES-256-GCM) avec une clé propre au serveur ; ils expirent (1 heure pour
l'accès, 90 jours sans usage pour le renouvellement). Le conteneur s'exécute
sans privilège, sans disque, et refuse de démarrer si des identifiants PISTE
figurent dans sa configuration. Les erreurs sont filtrées avant d'être
renvoyées au client. Lorsqu'un défaut d'occultation crédible est signalé, la
décision concernée peut être rendue temporairement indisponible, puis le
signalement est transmis sans délai à la Cour de cassation (une
réidentification manifeste persistante peut être signalée à
`anonymisation.sder.courdecassation@justice.fr`). Aucun système ne pouvant être
garanti sans risque, un incident peut être signalé par la page de support
ci-dessus.

## Sources de référence

- [Information des personnes — CNIL](https://www.cnil.fr/fr/conformite-rgpd-information-des-personnes-et-transparence)
- [Données ouvertes et API Judilibre](https://www.courdecassation.fr/acces-rapide-judilibre/donnees-ouvertes-open-data-et-api)
- [Accord de traitement des données Render](https://render.com/dpa)
- [Conservation des journaux Render](https://render.com/docs/logging#retention-period)
- [Accord de traitement des données Cloudflare](https://www.cloudflare.com/cloudflare-customer-dpa/)

# Déploiement du serveur MCP

Ce guide met en ligne votre propre instance de PandecteMCP sur
[Render](https://render.com), avec [WorkOS AuthKit](https://workos.com) pour la
connexion des utilisateurs. Comptez une heure la première fois.

```text
claude.ai, ChatGPT…        Claude Code, Cursor…          Claude Code, Cursor…
   (OAuth WorkOS)          (jeton personnel pdt_…)       (clé personnelle pk1.…)
        │                          │                              │
        └──────────── HTTPS : https://<service>.onrender.com/mcp ─┘
                                   │
                    Garde HTTP (débit par IP, échecs d'authentification)
                                   │
              Mode « serveur partagé »          Mode « clés personnelles »
              identifiants PISTE du titulaire   identifiants PISTE de l'appelant,
              quotas par personne et global     le temps de l'appel ; débit par IP
                                   │
                         API PISTE : Légifrance, Judilibre
```

Le disque persistant contient la base SQLite : empreintes des jetons
personnels, compteurs de quotas et cache des réponses publiques. Aucun
identifiant PISTE n'y est écrit.

## Coût

| Élément | Offre | Prix indicatif |
|---|---|---|
| Render, service web | Starter (toujours allumé) | 7 $/mois |
| Render, disque persistant | 1 Go | 0,25 $/mois |
| WorkOS AuthKit | gratuit jusqu'à 1 million d'utilisateurs actifs mensuels | 0 $ |
| PISTE (Légifrance, Judilibre) | gratuit, avec quotas | 0 $ |

Vérifiez les tarifs en vigueur sur les sites des fournisseurs.

## 1. Prérequis

- Le dépôt sur GitHub, à jour sur la branche indiquée par `branch` dans
  `render.yaml`.
- Une application PISTE abonnée aux API **Légifrance** et **Judilibre**
  (https://piste.gouv.fr → Applications). Notez son *client ID*, son *client
  secret* et sa clé d'API (*KeyId*). Consultez ses quotas : Applications →
  Actions → Consulter les quotas.
- Un compte WorkOS.
- Un compte Render.

## 2. WorkOS

Le tableau de bord WorkOS a deux environnements. **Staging** sert aux essais
(y compris en local) ; **Production** sert au service public. Les réglages
ci-dessous se font dans chacun.

1. **Authentication → Methods** : activez *Email + Password* et *Magic Auth*,
   puis les fournisseurs souhaités (Google, Microsoft, Apple, GitHub…). En
   Production, chaque fournisseur social demande ses propres identifiants
   OAuth (console Google, portail Azure…) ; WorkOS le guide pas à pas.
2. **Connect → Configuration** : activez **Client ID Metadata Document
   (CIMD)** et **Dynamic Client Registration (DCR)**. C'est ce qui permet à
   claude.ai et ChatGPT de s'inscrire seuls.
3. Ajoutez l'**indicateur de ressource** (*resource indicator*) :
   `https://<service>.onrender.com/mcp`. Les jetons émis porteront cette valeur
   dans `aud`, que le serveur exige.
4. **Applications → votre application → Redirects → Redirect URIs** : ajoutez
   `https://<service>.onrender.com/compte/callback` (et, en Staging,
   `http://localhost:8765/compte/callback` pour les essais locaux).
5. Relevez le **domaine AuthKit** (*Domains*, de la forme
   `xxxx.authkit.app`) et le **Client ID** (`client_01…`, onglet *API keys*).
   Ces deux valeurs sont publiques. La clé secrète `sk_…` n'est **pas**
   nécessaire : la page de compte se connecte en PKCE.

Contrôle : `https://<domaine>.authkit.app/.well-known/oauth-authorization-server`
doit répondre avec `client_id_metadata_document_supported: true` et un
`registration_endpoint`.

## 3. Render

1. **New → Blueprint**, choisissez le dépôt. Render lit `render.yaml` :
   service Docker `pandecte-mcp`, offre Starter, région Francfort, disque de
   1 Go monté sur `/var/data`.
2. Render demande les valeurs marquées `sync: false` :

   | Variable | Valeur |
   |---|---|
   | `MCP_PUBLIC_URL` | `https://<service>.onrender.com` (sans `/mcp`, sans barre finale) |
   | `MCP_OAUTH_ISSUER` | `https://<domaine>.authkit.app`, recopié **à l'identique** du champ `issuer` des métadonnées |
   | `WORKOS_CLIENT_ID` | `client_01…` |
   | `LEGIFRANCE_CLIENT_ID` | client ID PISTE |
   | `LEGIFRANCE_CLIENT_SECRET` | client secret PISTE |
   | `JUDILIBRE_KEY_ID` | KeyId PISTE |

   L'URL exacte du service n'est connue qu'après sa création : si besoin,
   mettez une valeur provisoire, puis corrigez `MCP_PUBLIC_URL` (et les
   réglages WorkOS de l'étape 2) dans *Environment* une fois l'URL affichée.
3. `PANDECTE_TOKEN_PEPPER` est tiré au hasard par Render. **Ne le changez
   jamais ensuite** : tous les jetons personnels et toutes les sessions
   deviendraient invalides.
4. Lancez le déploiement. Le conteneur refuse de démarrer si une variable
   obligatoire manque ou si la configuration de production est incohérente ; le
   message d'erreur nomme la variable, sans jamais afficher de valeur.

## 4. Vérifications après le premier déploiement

1. **Santé** : `https://<service>.onrender.com/health` →
   `{"status":"ok", "auth":"oauth", "personal_keys":true, "account":true, …}`.
2. **Métadonnées OAuth** :
   `https://<service>.onrender.com/.well-known/oauth-protected-resource/mcp`
   doit annoncer `resource` = `https://<service>.onrender.com/mcp` et
   `authorization_servers` = l'émetteur, caractère pour caractère.
3. **Adresse IP cliente.** Les limites par adresse (mode clés, garde HTTP)
   supposent que le serveur lit la vraie adresse du client derrière le proxy
   de Render, dont le comportement n'est pas documenté de façon fiable.
   Ouvrez `https://<service>.onrender.com/diagnostic-ip` et comparez
   `resolved_ip` à votre adresse publique (affichée par n'importe quel site
   « quelle est mon IP ») :
   - identiques : rien à changer ;
   - différentes : repérez votre adresse dans `headers`. Si elle figure seule
     dans `cf-connecting-ip` ou `true-client-ip`, définissez
     `MCP_CLIENT_IP_HEADER` avec ce nom ; si elle figure dans
     `x-forwarded-for`, réglez `MCP_TRUSTED_PROXY_HOPS` sur sa position
     comptée depuis la **droite** (1 = dernière entrée).

   Une fois le réglage confirmé, passez **`MCP_IP_DIAGNOSTIC` à `false`**.
4. **Page de compte** : `https://<service>.onrender.com/compte` → connexion
   WorkOS → « Générer mon jeton ».
5. **Client MCP** :
   `claude mcp add --transport http pandecte https://<service>.onrender.com/mcp --header "Authorization: Bearer pdt_…"`,
   puis une recherche réelle (par exemple « article 1240 du code civil »).
6. **claude.ai** : *Paramètres → Connecteurs → Ajouter un connecteur
   personnalisé*, URL `https://<service>.onrender.com/mcp` ; la connexion
   passe par WorkOS.

Enfin, reportez l'URL réelle dans `.mcp.json` et dans les manifests du dépôt
(valeur provisoire : `https://pandecte-a-configurer.invalid/mcp`).

## Variables d'environnement

### Obligatoires en production

| Variable | Rôle |
|---|---|
| `MCP_ENV=production` | Contrôles de démarrage stricts (déjà défini par l'image) |
| `MCP_AUTH_MODE=oauth` | Authentification obligatoire sur `/mcp` |
| `MCP_PUBLIC_URL` | URL publique, https, sans `/mcp` |
| `MCP_OAUTH_ISSUER` | Émetteur WorkOS, identique au champ `issuer` publié |
| `PANDECTE_TOKEN_PEPPER` | Poivre des jetons personnels, 32 caractères aléatoires minimum |
| `LEGIFRANCE_CLIENT_ID`, `LEGIFRANCE_CLIENT_SECRET` | Identifiants PISTE du titulaire |
| `JUDILIBRE_KEY_ID` | KeyId PISTE (`PISTE_KEY_ID` reste accepté) |
| `LEGIFRANCE_ENV=prod`, `JUDILIBRE_ENV=prod` | Interdisent le bac à sable |

Le démarrage échoue en production sans authentification : une passerelle
publique anonyme consommerait les quotas PISTE du titulaire.

### Comptes et accès

| Variable | Défaut | Effet |
|---|---|---|
| `WORKOS_CLIENT_ID` | vide | Active la page `/compte` (sinon absente) |
| `WORKOS_API_BASE` | `https://api.workos.com` | API WorkOS (sans objet en usage normal) |
| `MCP_PERSONAL_KEYS_ENABLED` | `true` | Accepte les clés personnelles `pk1.…` et publie `/cle` |
| `MCP_OAUTH_AUDIENCE` | `MCP_PUBLIC_URL` + `/mcp` | Audience exigée dans les jetons OAuth |
| `MCP_OAUTH_JWKS_URL` | émetteur + `/oauth2/jwks` | Clés publiques de l'émetteur (WorkOS) |
| `MCP_OAUTH_REQUIRED_SCOPES` | aucune | Portées exigées ; WorkOS ne délivre que des portées OpenID |

### Quotas

| Variable | Défaut | Effet |
|---|---:|---|
| `MCP_USER_CALLS_PER_MINUTE` | `10` | Mode partagé, par personne |
| `MCP_USER_CALLS_PER_DAY` | `100` | Mode partagé, par personne, remise à zéro à 00:00 UTC |
| `MCP_GLOBAL_CALLS_PER_DAY` | `2000` | Mode partagé, tous utilisateurs confondus : protège le quota PISTE |
| `MCP_KEYS_CALLS_PER_MINUTE` | `30` | Mode clés personnelles, par adresse IP |
| `MCP_TOOL_CALLS_PER_MINUTE` | `120` | Plafond de l'instance, tous modes |
| `MCP_MAX_CONCURRENT_REQUESTS` | `8` | Appels d'outils simultanés |

Réglez `MCP_GLOBAL_CALLS_PER_DAY` sous le quota journalier de votre
application PISTE : un appel d'outil peut faire plusieurs requêtes amont.

### Cache, données, réseau

| Variable | Défaut | Effet |
|---|---:|---|
| `PANDECTE_DATA_DIR` | `/var/data` dans l'image | Dossier de la base SQLite (point de montage du disque) |
| `PANDECTE_CACHE_TEXT_TTL` | `21600` (6 h) | Articles, sections, textes ; `0` désactive |
| `PANDECTE_CACHE_DECISION_TTL` | `86400` (24 h) | Décisions Judilibre ; `0` désactive |
| `PANDECTE_CACHE_MAX_MB` | `200` | Plafond du cache, éviction des plus anciennes entrées |
| `MCP_TRUSTED_PROXY_HOPS` | `0` (`1` dans `render.yaml`) | Position de l'IP cliente dans X-Forwarded-For, depuis la droite |
| `MCP_CLIENT_IP_HEADER` | vide | En-tête posé par le proxy portant l'IP cliente (prioritaire) |
| `MCP_IP_DIAGNOSTIC` | `false` | Publie `/diagnostic-ip` le temps du réglage |
| `MCP_JUDILIBRE_SUPPRESSED_IDS` | vide | Retrait d'urgence de décisions, voir `incident-response.md` |
| `MCP_LOG_LEVEL` | `WARNING` dans l'image | Niveau des journaux du SDK et du serveur HTTP |

## Essai local

Sans Docker, depuis la racine du dépôt :

```bash
cp .env.example .env        # puis remplacer les valeurs factices
python mcp_server/server.py --transport streamable-http
```

Avec l'image de production :

```bash
docker build -t pandecte-mcp .
docker run --rm -p 8765:8000 --env-file .env pandecte-mcp
```

L'image démarre en root le temps de donner le dossier de données à
l'utilisateur `app`, puis lance le serveur sous `app` (`deploy/entrypoint.sh`).
Le contrôle de configuration sans démarrage :
`python mcp_server/server.py --check-config`.

## Exploitation

- **Journaux** : une ligne par appel d'outil, avec le mode, une empreinte
  tronquée du sujet (donnée pseudonymisée), le résultat et `cache=hit|miss`.
  Jamais de jeton, de clé, d'adresse e-mail ni d'argument d'outil.
- **Sauvegarde** : Render prend un instantané quotidien des disques. Perdre la
  base ne fait perdre que les jetons personnels (à régénérer), les compteurs du
  jour et le cache.
- **Une seule instance** : le disque persistant l'impose, et les quotas
  comme le cache le supposent.
- **Mise à jour** : chaque commit sur `main` redéploie le service ; un
  redéploiement interrompt brièvement le service (disque attaché).
- **Compromission des identifiants PISTE** : les réinitialiser sur PISTE,
  mettre à jour les variables Render, et prévenir la DILA ou l'AIFE comme le
  prévoient les CGU (voir `obligations-cgu.md`).

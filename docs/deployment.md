# Déploiement du serveur MCP

Ce guide met en ligne votre propre instance de PandecteMCP sur
[Render](https://render.com). Comptez une demi-heure la première fois.

```text
claude.ai, ChatGPT…                      Claude Code, Cursor…
(connexion OAuth : page « Connexion PISTE »)   (clé personnelle pk1.… en en-tête)
        │                                              │
        └──── HTTPS : https://<service>.onrender.com/mcp ────┘
                                   │
                Garde HTTP (débit par IP, échecs d'authentification)
                                   │
          Identifiants PISTE DE L'UTILISATEUR, le temps de l'appel
                                   │
                    API PISTE : Légifrance, Judilibre
```

Le serveur **ne stocke rien** et **n'a aucun identifiant PISTE à lui**.
Chaque utilisateur se connecte avec les siens : le serveur les vérifie, les
scelle (AES-256-GCM) dans le jeton que garde son assistant, et ne les
déchiffre que le temps de chaque consultation. Le seul secret de l'instance
est la clé de scellement `PANDECTE_SEAL_KEY`.

## Coût

| Élément | Offre | Prix indicatif |
|---|---|---|
| Render, service web | Free (s'endort après une période d'inactivité) | 0 $ |
| Render, service web | Starter (toujours éveillé), si le réveil gêne | 7 $/mois |
| PISTE (Légifrance, Judilibre) | gratuit, quota de chaque utilisateur | 0 $ |

Avec l'offre Free, le premier appel après une période d'inactivité attend le
réveil du service. Vérifiez les tarifs et les conditions en vigueur sur le
site de Render.

## 1. Prérequis

- Le dépôt sur GitHub, à jour sur la branche indiquée par `branch` dans
  `render.yaml`.
- Un compte Render.
- Pour vos essais : votre propre application PISTE abonnée aux API
  **Légifrance** et **JUDILIBRE** (https://piste.gouv.fr → Applications,
  environnement Production). Ses identifiants ne se configurent **pas** sur
  le serveur : vous les saisirez, comme tout utilisateur, à la connexion.

## 2. Render

1. **New → Blueprint**, choisissez le dépôt. Render lit `render.yaml` :
   service Docker `pandecte-mcp`, région Francfort, sans disque.
2. Render demande `MCP_PUBLIC_URL` : `https://<service>.onrender.com` (sans
   `/mcp`, sans barre finale). L'URL exacte n'est connue qu'après la création :
   mettez une valeur provisoire si besoin, puis corrigez-la dans *Environment*.
3. `PANDECTE_SEAL_KEY` est tirée au hasard par Render. La changer déconnecte
   tous les utilisateurs, qui se reconnectent simplement ; pour une rotation
   sans coupure, placez l'ancienne valeur dans `PANDECTE_SEAL_KEY_PREVIOUS`.
4. Lancez le déploiement. Le conteneur refuse de démarrer si la
   configuration de production est incohérente — clé de scellement absente,
   ou identifiants PISTE présents dans l'environnement ; le message nomme la
   variable, sans jamais afficher de valeur.

## 3. Vérifications après le premier déploiement

1. **Santé** : `https://<service>.onrender.com/health` →
   `{"status":"ok", "auth":"piste", "personal_keys":true, …}`.
2. **Métadonnées OAuth** :
   - `/.well-known/oauth-protected-resource/mcp` annonce `resource` =
     `https://<service>.onrender.com/mcp` et le service lui-même comme
     serveur d'autorisation ;
   - `/.well-known/oauth-authorization-server` publie `authorization_endpoint`,
     `token_endpoint` et `registration_endpoint`.
3. **Adresse IP cliente.** La limite par adresse suppose que le serveur lit la
   vraie adresse du client derrière le proxy de Render, dont le comportement
   n'est pas documenté de façon fiable. Ouvrez
   `https://<service>.onrender.com/diagnostic-ip` et comparez `resolved_ip` à
   votre adresse publique (affichée par n'importe quel site « quelle est mon
   IP ») :
   - identiques : rien à changer ;
   - différentes : repérez votre adresse dans `headers`. Si elle figure seule
     dans `cf-connecting-ip` ou `true-client-ip`, définissez
     `MCP_CLIENT_IP_HEADER` avec ce nom ; si elle figure dans
     `x-forwarded-for`, réglez `MCP_TRUSTED_PROXY_HOPS` sur sa position
     comptée depuis la **droite** (1 = dernière entrée).

   Une fois le réglage confirmé, passez **`MCP_IP_DIAGNOSTIC` à `false`**.

   Constaté sur Render le 17/10/2026, et déjà reporté dans `render.yaml` :
   l'adresse cliente arrive seule dans `cf-connecting-ip` (Render passe par
   Cloudflare) et `x-forwarded-for` vaut « client, Cloudflare, proxy
   interne ». D'où `MCP_CLIENT_IP_HEADER=cf-connecting-ip`, avec
   `MCP_TRUSTED_PROXY_HOPS=3` en repli.
4. **claude.ai** : *Paramètres → Connecteurs → Ajouter un connecteur
   personnalisé*, URL `https://<service>.onrender.com/mcp`, puis
   « Se connecter » : la page « Connexion PISTE » demande vos identifiants
   PISTE. Posez ensuite une question réelle (par exemple « article 1240 du
   code civil »).
5. **Claude Code** : clé `pk1.…` assemblée sur
   `https://<service>.onrender.com/cle`, puis
   `claude mcp add --transport http pandecte https://<service>.onrender.com/mcp --header "Authorization: Bearer pk1.…"`.

Enfin, reportez l'URL réelle dans `.mcp.json`. Celui du dépôt pointe vers
l'instance publique du projet, `https://pandecte-mcp.onrender.com/mcp`.

## Variables d'environnement

### Obligatoires en production

| Variable | Rôle |
|---|---|
| `MCP_ENV=production` | Contrôles de démarrage stricts (déjà défini par l'image) |
| `MCP_AUTH_MODE=piste` | Connexion obligatoire sur `/mcp` (déjà défini par l'image) |
| `MCP_PUBLIC_URL` | URL publique, https, sans `/mcp` |
| `PANDECTE_SEAL_KEY` | Clé de scellement des jetons : 32 octets aléatoires en base64 |
| `LEGIFRANCE_ENV=prod`, `JUDILIBRE_ENV=prod` | Interdisent le bac à sable |

Le démarrage échoue en production :

- sans `MCP_AUTH_MODE=piste` : une passerelle publique anonyme n'a pas lieu
  d'être ;
- si `LEGIFRANCE_CLIENT_ID`, `LEGIFRANCE_CLIENT_SECRET`, `JUDILIBRE_KEY_ID` ou
  `PISTE_KEY_ID` sont définis : le serveur n'utilise que les identifiants de
  ses utilisateurs. Hors production, ces variables sont retirées du processus
  dès le démarrage.

### Accès et limites

| Variable | Défaut | Effet |
|---|---:|---|
| `PANDECTE_SEAL_KEY_PREVIOUS` | vide | Ancienne clé de scellement, acceptée en lecture le temps d'une rotation |
| `MCP_PERSONAL_KEYS_ENABLED` | `true` | Accepte les clés personnelles `pk1.…` et publie `/cle` |
| `MCP_CALLS_PER_MINUTE_PER_IP` | `30` | Appels d'outils par minute et par adresse IP |
| `MCP_TOOL_CALLS_PER_MINUTE` | `120` | Plafond de l'instance |
| `MCP_MAX_CONCURRENT_REQUESTS` | `8` | Appels d'outils simultanés |

### Cache et réseau

| Variable | Défaut | Effet |
|---|---:|---|
| `PANDECTE_CACHE_TEXT_TTL` | `21600` (6 h) | Articles, sections, textes ; `0` désactive |
| `PANDECTE_CACHE_DECISION_TTL` | `86400` (24 h) | Décisions Judilibre ; `0` désactive |
| `PANDECTE_CACHE_MAX_MB` | `50` | Plafond du cache en mémoire vive, éviction des plus anciennes entrées |
| `MCP_TRUSTED_PROXY_HOPS` | `0` (`3` dans `render.yaml`) | Position de l'IP cliente dans X-Forwarded-For, depuis la droite |
| `MCP_CLIENT_IP_HEADER` | vide (`cf-connecting-ip` dans `render.yaml`) | En-tête posé par le proxy portant l'IP cliente (prioritaire) |
| `MCP_IP_DIAGNOSTIC` | `false` | Publie `/diagnostic-ip` le temps du réglage |
| `MCP_JUDILIBRE_SUPPRESSED_IDS` | vide | Retrait d'urgence de décisions, voir `incident-response.md` |
| `MCP_LOG_LEVEL` | `WARNING` dans l'image | Niveau des journaux du SDK et du serveur HTTP |

Le cache ne contient que des réponses publiques (textes, décisions), communes
à tous les utilisateurs ; aucune donnée d'utilisateur.

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

Pour un essai depuis claude.ai sans hébergeur, exposez le serveur local par
un tunnel HTTPS (par exemple `cloudflared tunnel --url http://localhost:8765`)
et utilisez l'adresse du tunnel comme `MCP_PUBLIC_URL`.

Le contrôle de configuration sans démarrage :
`python mcp_server/server.py --check-config`.

## Exploitation

- **Journaux** : une ligne par appel d'outil, avec une empreinte tronquée du
  sujet (donnée pseudonymisée), le résultat et `cache=hit|miss` ; une ligne
  par connexion avec sa seule issue. Jamais de jeton, de clé, d'identifiant
  PISTE ni d'argument d'outil.
- **Aucune sauvegarde nécessaire** : rien n'est stocké. Un redémarrage vide
  le cache et rien d'autre ; les utilisateurs restent connectés tant que la
  clé de scellement ne change pas.
- **Plusieurs instances possibles** : rien n'est partagé entre instances,
  sauf la clé de scellement (même valeur partout). Le refus du rejeu d'un
  code d'autorisation est alors assuré par instance, PKCE le rendant de toute
  façon inutilisable sans son vérificateur.
- **Mise à jour** : chaque commit sur la branche de `render.yaml` redéploie
  le service.
- **Clé de scellement compromise** : la remplacer immédiatement (tous les
  utilisateurs devront se reconnecter) et inviter les utilisateurs à
  régénérer leur Client Secret sur PISTE, la seule révocation certaine de
  leurs identifiants.

# Installer et vérifier PandecteMCP

État du guide : 18 octobre 2026. Version du skill et des plugins : 0.1.0.

**Qualifié le 17/10/2026** sur le serveur hébergé
`https://pandecte-mcp.onrender.com/mcp` : connexion par la page « Connexion
PISTE » puis recherche et lecture d'article réelles depuis **claude.ai**,
**ChatGPT** (mode développeur) et **Claude Code** (`claude mcp add`). Les
parcours par plugin (marketplaces Claude Code et Codex) ne sont pas encore
qualifiés : les commandes ci-dessous suivent la documentation officielle.

## Choisir le canal

- **Connecteur hébergé** : outils juridiques sans rien installer. Il faut
  ses propres identifiants PISTE (gratuits), saisis une fois à la connexion.
  Voir le [README](../README.md#utiliser-pandectemcp-sans-rien-installer).
- **Plugin du dépôt** : skill méthodologique et même serveur hébergé, déclaré
  par la racine `.mcp.json`. Python n'est pas nécessaire sur le poste.
- **Skill autonome** : méthode uniquement. Sans outil, la récupération passe
  par une recherche web sur sources officielles si le client le permet ; sinon
  la réponse doit expliciter cette limite.
- **Serveur local** : Python, dépendances MCP et identifiants PISTE dans un
  `.env`. Personne d'autre ne voit vos identifiants.

## Claude Code

Connecteur seul (qualifié) :

~~~powershell
claude mcp add --transport http pandecte https://pandecte-mcp.onrender.com/mcp
~~~

Puis `/mcp` → `pandecte` → **Authenticate** : le navigateur ouvre la page
« Connexion PISTE » ; le retour se fait sur une adresse `localhost`.

Plugin complet (skill et connecteur), depuis la marketplace du dépôt :

~~~powershell
claude plugin marketplace add TitouanSC/PandecteMCP
claude plugin install pandecte@pandecte
claude plugin list
~~~

Ouvrir une nouvelle session. Contrôler la présence du skill
`pandecte-recherche` et du serveur dans `/mcp`. Demander une recherche puis une
lecture d'article ; une réponse rappelant la méthode, sans appel réel, ne
prouve pas que le connecteur fonctionne.

Mise à jour, puis nouvelle session :

~~~powershell
claude plugin marketplace update pandecte
claude plugin update pandecte@pandecte
~~~

Retrait du plugin uniquement :

~~~powershell
claude plugin uninstall pandecte@pandecte
claude plugin list
~~~

Si le même nom `pandecte` est déclaré dans plusieurs portées (projet et
utilisateur) avec des adresses différentes, Claude Code le signale dans
`claude mcp list` : n'en garder qu'une.

## Codex

Le dépôt contient une marketplace native `.agents/plugins/marketplace.json` :

~~~powershell
codex plugin marketplace add TitouanSC/PandecteMCP
codex plugin add pandecte@pandecte
codex plugin list --json
~~~

La version 0.1.0 et la description du plugin se trouvent dans
`.codex-plugin/plugin.json`, conformément aux exemples officiels OpenAI. Le
chemin `./` est relatif à la racine de la marketplace, pas à
`.agents/plugins/`.

Mise à jour de la source puis réinstallation :

~~~powershell
codex plugin marketplace upgrade pandecte
codex plugin add pandecte@pandecte
~~~

Retrait du plugin uniquement :

~~~powershell
codex plugin remove pandecte@pandecte
codex plugin list --json
~~~

## Dépannage

- **Premier appel en échec ou très lent** : le serveur gratuit sortait de
  veille (environ 30 secondes). Réessayer.
- **« PISTE refuse ces identifiants »** sur la page de connexion : vérifier le
  Client ID et le Client Secret de l'application en environnement
  **Production**, et son abonnement aux API Légifrance et JUDILIBRE.
- **Connexion qui échoue avant la page « Connexion PISTE »** : supprimer le
  connecteur et le recréer, pour forcer un nouvel enregistrement du client.
- **Outils présents mais erreur de récupération** : noter l'outil, l'heure et
  le message, sans copier de jeton, de code d'autorisation ni d'identifiant
  dans une issue.
- **Deux installations du skill** : n'en garder qu'une active.

## Skill autonome

~~~powershell
npx skills add https://github.com/TitouanSC/PandecteMCP/tree/main/skill --skill pandecte-recherche
npx skills update pandecte-recherche
~~~

La méthode est utilisable sans le plugin. La gestion et le retrait dépendent
du client et de la portée choisie par `skills` ; vérifier `npx skills --help` et
la liste des installations avant de supprimer un répertoire.

Sources des commandes : [Claude Code](https://code.claude.com/docs/en/discover-plugins),
[Codex CLI](https://learn.chatgpt.com/docs/developer-commands) et
[marketplaces OpenAI](https://developers.openai.com/plugins/build/plugins).

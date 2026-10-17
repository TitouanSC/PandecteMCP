---
plateforme: Gemini
cle: gemini
dossier: gemini_skill
---

# intro

Déclinaison pour l'écosystème Gemini (Gemini CLI, Google Antigravity, Google
AI Studio). Les scripts Python du dépôt ne sont pas supposés disponibles : la
voie outillée passe par le connecteur MCP, la voie de repli par la recherche
Google restreinte aux domaines officiels.

# connecteur

Gemini CLI et Google Antigravity acceptent des serveurs MCP distants : le
connecteur s'y ajoute avec l'adresse `https://pandecte-mcp.onrender.com/mcp`
(connexion OAuth, ou en-tête `Authorization: Bearer pk1.…`). Google AI Studio
n'accepte pas de serveur MCP.

# repli

- recherche Google / *grounding* avec `site:legifrance.gouv.fr`,
  `site:courdecassation.fr`, `site:conseil-etat.fr`… ;
- lecture de la page officielle trouvée lorsque l'outil le permet.

# notes

- Ne jamais reconstituer un texte ou un numéro de pourvoi de mémoire, même si
  la recherche Google en affiche un extrait.
- Conserver le code et la date dans les requêtes de recherche.
- Dans Google AI Studio, sans connecteur ni lecture de page, la vérification
  repose sur le *grounding* : signaler toute référence non lue sur sa page
  officielle comme non vérifiée.

# presentation

Déclinaison **Gemini** (Gemini CLI, Google Antigravity, Google AI Studio) de la
méthode PandecteMCP. Elle met en tête le connecteur MCP PandecteMCP, que Gemini
CLI et Antigravity savent utiliser, et se replie sur la recherche Google
restreinte aux domaines officiels.

# installation

**Gemini CLI** — copier le dossier `pandecte-recherche/` (contenu du zip) dans
`~/.gemini/skills/` (portée utilisateur) ou `.gemini/skills/` (portée projet).
Pour la voie outillée, déclarer le connecteur dans `settings.json` :

```json
{
  "mcpServers": {
    "pandecte": { "httpUrl": "https://pandecte-mcp.onrender.com/mcp" }
  }
}
```

**Google Antigravity** — copier le dossier dans
`~/.gemini/antigravity/skills/pandecte-recherche/`, puis ajouter le serveur MCP
dans les réglages de l'éditeur.

**Google AI Studio** — copier le contenu de `SKILL.md` dans les *System
Instructions* et activer *Grounding with Google Search*. Le connecteur MCP n'y
est pas disponible.

La prise en charge d'OAuth pour un serveur MCP distant dépend de la version de
Gemini CLI : à défaut, assembler une clé personnelle sur
<https://pandecte-mcp.onrender.com/cle> et l'ajouter en en-tête
`Authorization`.

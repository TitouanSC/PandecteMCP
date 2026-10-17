---
plateforme: Grok
cle: grok
dossier: grok_skill
---

# intro

Déclinaison pour Grok (xAI). Aucun connecteur MCP ni script local n'est
supposé : la voie habituelle est celle des outils web natifs de Grok,
restreints aux domaines officiels.

# connecteur

Un connecteur MCP n'est utilisable que si l'environnement Grok permet
d'ajouter un serveur MCP distant ; ne pas le supposer sans l'avoir constaté.

# repli

- `web_search` avec `site:legifrance.gouv.fr` ou un domaine juridictionnel ;
- `open_page` sur les pages d'articles, de codes et de décisions ;
- `browser_tab` lorsqu'une interaction est nécessaire.

# notes

- Préférer toujours les domaines officiels `.gouv.fr` et les sites des
  juridictions.
- Un identifiant n'est cité qu'après lecture de la page officielle qui le
  porte (`open_page`), jamais d'après le seul extrait de `web_search`.
- Les noms d'outils ci-dessus correspondent aux outils natifs constatés de
  Grok ; vérifier ceux réellement proposés dans la session.

# presentation

Déclinaison **Grok** (xAI) de la méthode PandecteMCP. Elle s'appuie sur les
outils web natifs de Grok, restreints aux domaines officiels, et n'utilise le
connecteur MCP PandecteMCP que si l'environnement permet de l'ajouter.

# installation

Charger le contenu du zip dans Grok comme jeu d'instructions personnalisées,
en conservant l'arborescence : `SKILL.md` renvoie à `references/` en chemins
relatifs. Si l'environnement ne lit qu'un seul fichier, y coller `SKILL.md`
puis, au besoin, `references/modules.md`.

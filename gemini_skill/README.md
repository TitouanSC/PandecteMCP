# PandecteMCP — déclinaison Gemini

Déclinaison **Gemini** (Gemini CLI, Google Antigravity, Google AI Studio) de la
méthode PandecteMCP. Elle met en tête le connecteur MCP PandecteMCP, que Gemini
CLI et Antigravity savent utiliser, et se replie sur la recherche Google
restreinte aux domaines officiels.

> **Projet indépendant**, sans lien avec l'auteur du projet d'origine, avec une
> personnalité ou une institution, ni avec l'État. Ce skill **ne remplace pas
> un avocat**.

## Contenu

```
pandecte-recherche/
├── SKILL.md                      ← méthode condensée, adaptée à Gemini
├── references/
│   ├── sources-autorisees.md     ← hiérarchie et autorité des sources (P3)
│   ├── modules.md                ← six modules activables
│   └── audit-documentaire.md     ← protocole du module DOC-AUDIT
└── README.md                     ← ce document
```

## Installation

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

## Voie outillée : le connecteur PandecteMCP

Le connecteur hébergé `https://pandecte-mcp.onrender.com/mcp` interroge
Légifrance et Judilibre avec **vos propres** identifiants PISTE (gratuits sur
<https://piste.gouv.fr>), saisis une fois à la connexion ; le serveur ne les
stocke pas. Sans connecteur, le skill applique sa voie de repli web, avec la
même règle de provenance.

## Origine et licence

Paquet **généré** à partir du dépôt
<https://github.com/TitouanSC/PandecteMCP> (dossier `declinaisons/`) : ne pas
le modifier à la main. La méthode complète est dans le skill
`pandecte-recherche` du même dépôt.

PandecteMCP est une version modifiée de
[droit-francais-skill](https://github.com/brissonjo-sudo/droit-francais-skill)
(© 2026 @brissonjo-sudo) ; modifications © 2026 @TitouanSC. Licence
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.fr).

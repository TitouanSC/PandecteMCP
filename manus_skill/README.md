# PandecteMCP — déclinaison Manus

Déclinaison **Manus** de la méthode PandecteMCP. Manus acceptant des serveurs
MCP personnalisés, le connecteur PandecteMCP y est la voie prioritaire ; la
capacité web native sert de repli, sans nom d'outil supposé.

> **Projet indépendant**, sans lien avec l'auteur du projet d'origine, avec une
> personnalité ou une institution, ni avec l'État. Ce skill **ne remplace pas
> un avocat**.

## Contenu

```
pandecte-recherche/
├── SKILL.md                      ← méthode condensée, adaptée à Manus
├── references/
│   ├── sources-autorisees.md     ← hiérarchie et autorité des sources (P3)
│   ├── modules.md                ← six modules activables
│   └── audit-documentaire.md     ← protocole du module DOC-AUDIT
└── README.md                     ← ce document
```

## Installation

1. Dans Manus : onglet **Skills** → **+ Add** → **Upload a skill** →
   sélectionner le zip.
2. Le skill apparaît dans la liste accessible en tapant `/` dans le chat.
3. Pour la voie prioritaire, ajouter le connecteur : **Settings →
   Integrations → Custom MCP Servers**, adresse
   `https://pandecte-mcp.onrender.com/mcp`.

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

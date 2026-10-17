---
plateforme: Manus
cle: manus
dossier: manus_skill
---

# intro

Déclinaison pour Manus. Les scripts Python du dépôt ne sont pas supposés
disponibles ; Manus accepte en revanche des serveurs MCP personnalisés, ce qui
fait du connecteur PandecteMCP la voie à privilégier.

# connecteur

Manus accepte des serveurs MCP personnalisés (Settings → Integrations →
Custom MCP Servers) : y ajouter `https://pandecte-mcp.onrender.com/mcp`. Que
Manus gère la connexion OAuth ou un en-tête `Authorization` fixe n'est pas
confirmé par sa documentation publique : le constater à l'usage.

# repli

- capacité web native de Manus : son nom exact **n'est pas documenté
  publiquement** et n'est donc pas supposé ici ; constater les outils
  réellement proposés dans la session plutôt que d'en deviner le nom.

# notes

- Ne jamais inventer un appel d'outil, MCP ou natif.
- Préférer le connecteur à la capacité web générale dès qu'il est disponible :
  provenance, datation et applicabilité y sont plus précises.

# presentation

Déclinaison **Manus** de la méthode PandecteMCP. Manus acceptant des serveurs
MCP personnalisés, le connecteur PandecteMCP y est la voie prioritaire ; la
capacité web native sert de repli, sans nom d'outil supposé.

# installation

1. Dans Manus : onglet **Skills** → **+ Add** → **Upload a skill** →
   sélectionner le zip.
2. Le skill apparaît dans la liste accessible en tapant `/` dans le chat.
3. Pour la voie prioritaire, ajouter le connecteur : **Settings →
   Integrations → Custom MCP Servers**, adresse
   `https://pandecte-mcp.onrender.com/mcp`.

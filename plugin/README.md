# PandecteMCP — plugin

Recherche en droit français fondée sur les sources officielles : Légifrance
pour les textes, Judilibre pour la jurisprudence. Le plugin réunit deux
éléments :

- **le skill `pandecte-recherche`** : la méthode de recherche (sources
  primaires, contrôle de vigueur, citations traçables, aucune référence de
  mémoire) ;
- **le connecteur PandecteMCP** : le serveur MCP hébergé
  `https://pandecte-mcp.onrender.com/mcp`, qui interroge les API officielles
  de la plateforme PISTE.

Projet personnel, gratuit et open source ; ni officiel, ni affilié à la DILA,
à la Cour de cassation ou à l'État.

## Installation

Dans claude.ai ou l'application Claude : **Personnaliser > Plugins > Ajouter >
Ajouter une marketplace**, saisir `TitouanSC/PandecteMCP`, puis ajouter le
plugin **PandecteMCP**. Ouvrir ensuite son onglet **Connecteurs** et connecter
PandecteMCP. Rien à télécharger ni à installer.

Dans Claude Code :

```
/plugin marketplace add TitouanSC/PandecteMCP
/plugin install pandecte@pandecte
```

## Ce que le plugin envoie, et à qui

- Le skill ne contacte aucun service : ce sont des instructions.
- Le connecteur envoie les recherches de l'assistant (articles, textes,
  décisions demandés) au serveur PandecteMCP hébergé chez Render, derrière
  Cloudflare, qui les relaie aux API Légifrance et Judilibre de PISTE.
- À la connexion, une page du serveur demande **vos propres** identifiants
  PISTE (compte gratuit sur piste.gouv.fr). Le serveur ne les stocke pas : ils
  voyagent chiffrés dans le jeton que garde votre assistant, et ne servent
  qu'à vos appels.
- Le serveur n'a ni compte utilisateur ni base de données ; Render et
  Cloudflare tiennent leurs propres journaux techniques.

Détails : [politique de confidentialité](https://github.com/TitouanSC/PandecteMCP/blob/main/docs/privacy-policy.md)
et [conditions d'utilisation](https://github.com/TitouanSC/PandecteMCP/blob/main/docs/terms-of-use.md).

## Contenu

Le dossier `skills/pandecte-recherche/` est une copie générée du skill complet
(`skill/` à la racine du dépôt) par `declinaisons/generer.py` : ne pas le
modifier à la main.

## Licence et crédits

CC BY-SA 4.0 — voir `LICENSE`. Projet modifié à partir de
[droit-francais-skill](https://github.com/brissonjo-sudo/droit-francais-skill),
© 2026 @brissonjo-sudo ; modifications © 2026 @TitouanSC.

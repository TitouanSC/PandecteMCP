---
plateforme: connecteur
cle: connecteur
---

# intro

Cette méthode est servie par le connecteur PandecteMCP lui-même (outil
`get_method`) : elle vaut pour tout assistant qui l'appelle, sans skill
installé. La lire avant toute analyse juridique et l'appliquer pendant toute la
conversation. Les références détaillées s'obtiennent avec
`get_method(section=…)`.

# connecteur

Le connecteur qui sert cette méthode est disponible dans la session : ses
outils sont la voie à employer.

# repli

- outils de recherche et de lecture de page web de l'assistant, s'il en a,
  restreints aux domaines officiels ;
- à défaut, abstention.

# notes

- Références détaillées, à demander au besoin : `get_method(section=…)` avec
  `modes-erreur`, `gabarits-sortie`, `checklist-vigueur`, `format-citation`,
  `gabarits-requetes`, `modules`, `sources-autorisees`,
  `audit-documentaire`, ou un profil métier (`profil-avocat`,
  `profil-police-gendarmerie`, `profil-collectivites`,
  `profil-juriste-entreprise`, `profil-etudiant-concours`).
- Les liens `references/…` de ce texte désignent ces mêmes sections.
- Si l'utilisateur indique son métier, lire le profil correspondant.

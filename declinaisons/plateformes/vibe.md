---
plateforme: Vibe
cle: vibe
dossier: vibe_skill
---

# frontmatter

user-invocable: false
allowed-tools:
  - web_search
  - web_fetch
  - read_file
  - ask_user_question

# intro

Déclinaison pour Mistral Vibe. Les outils natifs `web_search` et `web_fetch`
assurent la récupération ; le connecteur PandecteMCP est utilisé en priorité
s'il a été configuré.

# connecteur

Vibe peut se connecter à des serveurs MCP déclarés dans sa configuration ; si
le connecteur PandecteMCP y figure, ses outils sont prioritaires. Ne pas le
supposer sans l'avoir constaté dans la session.

# repli

- `web_search` (paramètre `query`) avec `site:legifrance.gouv.fr` ou un
  domaine juridictionnel ;
- `web_fetch` (paramètre `url`) sur la page trouvée, pour lire l'identifiant,
  la date et le texte.

# notes

- Noms d'outils vérifiés contre le registre public des outils intégrés de
  Vibe (`mistralai/mistral-vibe`, `vibe/core/tools/builtins/`, relevé du
  5 septembre 2026) ; vérifier qu'ils correspondent à la version installée.
- Tout identifiant cité provient d'un `web_search` **suivi** d'un `web_fetch`
  qui le confirme sur la page officielle.

# presentation

Déclinaison **Vibe** (Mistral) de la méthode PandecteMCP. Elle s'appuie sur
les outils natifs `web_search` et `web_fetch`, restreints aux domaines
officiels, et sur le connecteur PandecteMCP lorsqu'il est configuré.

# installation

Vibe découvre un skill par dossier, nommé comme le champ `name:` du
frontmatter, ici `pandecte-recherche` :

| Emplacement | Portée |
|---|---|
| `./.vibe/skills/` ou `./.agents/skills/` | Projet (répertoire de travail approuvé) |
| `~/.vibe/skills/` | Utilisateur (tous les projets) |

Décompresser le zip dans l'un de ces emplacements : il contient déjà le
dossier `pandecte-recherche/`. Le paquet est autonome et ne dépend d'aucun
autre fichier du dépôt.

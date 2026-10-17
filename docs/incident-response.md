# Procédure d'incident — clés PISTE et données Judilibre

Dernière mise à jour : 18 octobre 2026

Cette procédure est utilisable sans outil particulier. Les captures et preuves
contenant une clé, un jeton ou une identité restent dans un dossier privé à
accès restreint, jamais dans une issue GitHub publique.

## Déclencheurs

- hausse inexpliquée de consommation, 401/403/429 inhabituels ;
- secret trouvé dans un commit, une image, un log ou une réponse ;
- compte GitHub ou Render compromis, ou clé de scellement exposée ;
- utilisateur signalant que ses identifiants PISTE ont pu fuir par le service ;
- signalement d'un nom/prénom non occulté ou d'une réidentification manifeste ;
- réponse du plugin redistribuant une décision qui devrait être retirée.

## Priorités immédiates

1. Ouvrir une fiche privée avec heure UTC, service, version et déclarant.
2. Contenir : suspendre le service ou l'accès concerné si la fuite continue.
3. Ne pas recopier le secret ni la donnée personnelle dans les journaux.
4. Préserver les preuves minimales et relever l'image/commit déployé.

## Clé de scellement exposée

Le service ne détient aucune clé PISTE. Son seul secret est
`PANDECTE_SEAL_KEY` : qui la possède peut déchiffrer les jetons des
utilisateurs, donc leurs identifiants PISTE.

1. Remplacer **immédiatement** `PANDECTE_SEAL_KEY` sur l'hébergeur par une
   nouvelle valeur aléatoire, **sans** renseigner `PANDECTE_SEAL_KEY_PREVIOUS` :
   tous les jetons existants deviennent illisibles et chaque utilisateur doit
   se reconnecter.
2. Redéployer et vérifier `/health` puis une connexion complète.
3. Publier un avis sur le dépôt invitant les utilisateurs à **régénérer leur
   Client Secret sur PISTE** — seule révocation certaine de leurs
   identifiants — et, le cas échéant, à avertir la DILA (Légifrance) ou la Cour
   de cassation (Judilibre) et/ou l'AIFE (CGU Légifrance V.3, Judilibre XI.E).
4. Rechercher la cause (journal, image, dépôt, compte de l'hébergeur) et
   révoquer les accès compromis.

## Identifiants d'un utilisateur exposés

1. L'utilisateur régénère son Client Secret sur PISTE **au plus vite** et
   avertit la DILA et/ou la Cour de cassation et l'AIFE, comme le prévoient
   les CGU qu'il a acceptées.
2. Si l'exposition vient du service (journal, réponse, page), traiter comme
   une violation de données : corriger, ajouter un test de non-régression,
   évaluer la clé de scellement (section précédente) et informer les
   utilisateurs potentiellement concernés par un avis public.

## Défaut d'occultation Judilibre

1. Identifier la décision sans reproduire publiquement le passage.
2. Ajouter l'identifiant exact à la variable d'environnement
   `MCP_JUDILIBRE_SUPPRESSED_IDS` (liste séparée par des virgules). Un
   identifiant Judilibre fait 24 caractères hexadécimaux ; la casse est
   indifférente, les espaces autour des virgules sont ignorés.
3. Redémarrer le service et vérifier :
   - le journal de démarrage porte `judilibre_suppression_list count=N`, où
     `N` est le nombre d'identifiants attendus — jamais les identifiants
     eux-mêmes. **Une entrée malformée empêche le service de démarrer**, avec
     un message qui nomme la position fautive dans la liste : corriger la
     variable, ne pas contourner ;
   - la décision est filtrée des résultats de recherche ;
   - sa lecture directe renvoie « temporairement indisponible ».
4. Transmettre **sans délai** la demande portant sur un défaut d'occultation à
   la Cour de cassation. Pour une demande d'occultation ou levée, utiliser
   `occultations.courdecassation@justice.fr`.
5. Une réidentification manifeste persistante peut être signalée à
   `anonymisation.sder.courdecassation@justice.fr` ; il s'agit d'une
   recommandation forte de la section VII, distincte de l'obligation précédente.
6. Ne pas modifier soi-même le texte ou la pseudonymisation. Le retrait complet
   est la mesure conservatoire du service.
7. Après confirmation de la correction amont, relire la décision, retirer son
   identifiant de la variable, redémarrer et consigner la clôture.

## Communication et clôture

- informer les personnes ou autorités requises selon l'incident et le droit
  applicable ; faire valider toute notification RGPD si une violation de
  données personnelles est plausible ;
- documenter cause, durée, impact, identifiants ou clés touchés, décisions retirées et actions ;
- ajouter un test de non-régression sans intégrer les données exposées ;
- réaliser un exercice semestriel et dater son résultat dans
  `audit-securite.md`.


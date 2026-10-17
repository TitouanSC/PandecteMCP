# Conditions d'utilisation — PandecteMCP

Dernière mise à jour : 18 octobre 2026

## 1. Objet

**PandecteMCP** fournit des outils en lecture seule pour rechercher et
consulter des sources juridiques françaises via les API Légifrance et
Judilibre, ainsi qu'une méthode de vérification et de citation traçable
(le skill du même dépôt). Le service hébergé est un serveur MCP que
l'utilisateur ajoute à son assistant d'IA (claude.ai, ChatGPT, Claude Code…).

**Projet indépendant.** PandecteMCP est un projet personnel et open source,
édité par @TitouanSC. Il est sans lien avec l'auteur du projet d'origine dont il
dérive, avec une personnalité ou une institution, ni avec l'État. Il n'est ni
édité, ni approuvé, ni labellisé par la DILA, Légifrance, la Cour de cassation,
Judilibre ou une autre administration. Le nom de ces sources n'est employé que
pour désigner l'origine des données consultées.

## 2. Absence de conseil juridique

Le service facilite l'accès aux sources ; **il ne remplace pas un avocat** ni
un professionnel compétent, notamment pour un contentieux, une sanction, un
acte officiel ou une décision produisant des effets juridiques. L'utilisateur
vérifie la date, le champ d'application, les dispositions transitoires et
l'adéquation de la source à sa situation.

## 3. Identifiants PISTE de l'utilisateur et mandat

Le service ne dispose d'**aucun** identifiant PISTE propre. Pour l'utiliser,
l'utilisateur crée gratuitement son application sur PISTE, accepte lui-même
les CGU de Légifrance et de Judilibre, puis saisit son Client ID et son Client
Secret sur la page « Connexion PISTE » du service (ou les transmet sous forme
de clé personnelle `pk1`).

**Mandat.** En saisissant ses identifiants, l'utilisateur **donne mandat** au
service de consulter les API Légifrance et Judilibre **en son nom et pour son
compte**, dans la seule limite des outils de consultation qu'il appelle depuis
son assistant. Le service agit comme **intermédiaire technique** : il n'utilise
ces identifiants que le temps de chaque consultation demandée, ne les stocke
pas, ne les journalise pas, ne les communique à personne et ne s'en sert à
aucune autre fin.

**Responsabilité de l'utilisateur.** Les CGU de l'API Légifrance (§ III.3) et
de l'API Judilibre (§ XI.C) réservent les clés à l'application de leur titulaire
et interdisent de les divulguer à un tiers. L'utilisateur reste seul
responsable, vis-à-vis de PISTE et des producteurs de données, de l'usage de
ses identifiants et de leur confiance au service. Pour ne les confier à
personne, il peut héberger sa propre instance (le code est public) ou utiliser
le mode local.

**Révocation.** L'utilisateur retire l'accès à tout moment en déconnectant le
connecteur dans son assistant ou en régénérant son Client Secret sur PISTE, ce
qui invalide immédiatement tout jeton qui le contient.

## 4. Sources, exactitude et disponibilité

Les résultats proviennent des API accessibles au moment de la requête. Les
sources peuvent être incomplètes, temporairement indisponibles, modifiées ou
corrigées. Le service signale un échec de récupération comme une source non
vérifiée et ne présente pas une réponse de substitution comme officielle.

Le service est fourni **gratuitement et sans garantie** de disponibilité. Une
mise en veille de l'hébergeur (offre gratuite), des limites de débit ou une
indisponibilité de PISTE peuvent retarder ou empêcher une recherche.

La copie d'un texte ou d'une décision restituée par le service n'a pas de
valeur officielle ; seule la publication sur Légifrance ou sur le site de la
Cour de cassation fait foi.

## 5. Utilisations interdites

L'utilisateur s'engage à ne pas utiliser le service :

- pour tenter de réidentifier une personne occultée ou pseudonymisée ;
- pour constituer un profil de magistrats ou de membres du greffe à partir des
  décisions diffusées ;
- pour harceler, discriminer ou porter atteinte à une personne citée dans une
  décision ;
- avec des identifiants PISTE qui ne sont pas les siens ;
- pour contourner les quotas, mécanismes de sécurité ou conditions d'accès de
  PISTE, Légifrance, Judilibre ou des prestataires du service ;
- pour publier une conclusion juridique comme certaine lorsque le service a
  signalé une source non vérifiée ou une limite.

## 6. Données et licences

Le code et le skill sont distribués sous licence
[CC BY-SA 4.0](../LICENSE). Les données récupérées restent soumises aux droits,
licences et conditions de leurs producteurs, notamment la Licence Ouverte 2.0
et les conditions de réutilisation de Légifrance et Judilibre. Le traitement
des données personnelles est décrit dans la
[politique de confidentialité](privacy-policy.md).

## 7. Responsabilité

L'utilisateur reste responsable de l'usage des résultats et de toute décision
prise sur leur fondement. Dans les limites permises par la loi applicable,
l'éditeur ne répond pas des dommages résultant d'une source incomplète ou
indisponible, d'une mauvaise interprétation, d'une absence de mise à jour,
d'une indisponibilité du service ou d'un usage contraire aux présentes
conditions ou aux CGU de PISTE.

## 8. Suspension

L'accès peut être limité ou suspendu pour protéger le service, respecter une
obligation légale, répondre à un incident ou faire respecter les conditions des
fournisseurs d'API. Le service peut être arrêté à tout moment ; le code reste
disponible pour un auto-hébergement.

## 9. Modification et droit applicable

Ces conditions peuvent être mises à jour lorsque le service, l'hébergement ou
les exigences des sources évoluent. La date de la version applicable figure en
tête. Elles sont régies par le droit français, sous réserve des règles
impératives applicables à l'utilisateur.

## 10. Support

Les questions et incidents peuvent être signalés sur la
[page de support du projet](https://github.com/TitouanSC/PandecteMCP/issues).
Ne jamais y publier d'identifiant PISTE, de jeton, de pièce confidentielle ou
de donnée personnelle.

## Sources de référence

- [Registre des obligations CGU (Légifrance et Judilibre)](obligations-cgu.md)
- [CGU de réutilisation Judilibre](https://piste.gouv.fr/images/cgu/CGU_open_data_V8.pdf)
- [API et données ouvertes Judilibre](https://www.courdecassation.fr/acces-rapide-judilibre/donnees-ouvertes-open-data-et-api)
- [Catalogue PISTE — Légifrance et identifiant de la CGU courante](https://piste.gouv.fr/api-catalog-sandbox?filter=legifrance)
- [Licence Ouverte 2.0 (Etalab)](https://www.etalab.gouv.fr/licence-ouverte-open-licence)

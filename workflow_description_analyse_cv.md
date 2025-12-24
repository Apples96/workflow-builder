# Analyse et classement de CV par rapport à une fiche de poste

Ce workflow permet d'analyser 5 CV uploadés par l'utilisateur et de les comparer à une fiche de poste également uploadée en PDF. L'objectif est d'évaluer chaque candidat selon des critères précis et de produire un rapport détaillé avec des scores de correspondance.

## Ce que l'utilisateur fournit

L'utilisateur doit uploader exactement 6 fichiers PDF : 5 fichiers contenant les CV des candidats à évaluer, et 1 fichier contenant la fiche de poste. La fiche de poste doit inclure les missions principales, les compétences techniques requises, les compétences comportementales souhaitées, l'expérience minimale, la formation attendue, et les langues nécessaires si applicable.

## Comment le workflow fonctionne

D'abord, le workflow attend que tous les fichiers soient correctement indexés par le système. Cette étape est cruciale car les fichiers PDF (les 5 CV et la fiche de poste) doivent être traités avant de pouvoir être analysés. Le workflow vérifie le statut de chaque fichier et attend jusqu'à 2 minutes maximum. Si un fichier n'est pas prêt après ce délai, le workflow attend 90 secondes supplémentaires avant de continuer.

Le workflow commence par extraire le contenu complet de la fiche de poste uploadée. Cette fiche servira de référence pour toutes les évaluations des candidats.

Ensuite, le workflow extrait les informations de tous les CV en parallèle pour gagner du temps. Pour chaque CV, il récupère le nom complet du candidat, son email, son téléphone, sa formation avec les diplômes et établissements, son expérience professionnelle détaillée avec les postes occupés et les durées, ses compétences techniques incluant les langages de programmation et outils maîtrisés, ses compétences comportementales comme le leadership ou l'autonomie, les langues parlées avec leurs niveaux, et calcule le nombre total d'années d'expérience depuis le premier emploi.

Une fois toutes les informations extraites, le workflow analyse chaque candidat en profondeur par rapport à la fiche de poste fournie par l'utilisateur. Cette analyse se fait également en parallèle pour les 5 candidats afin d'optimiser la performance. Pour chaque candidat, le workflow évalue 6 critères avec des pondérations spécifiques.

Les compétences techniques représentent 35% du score total. Le workflow vérifie si le candidat maîtrise les technologies et outils mentionnés dans la fiche de poste, évalue son niveau de maîtrise apparent, et considère les technologies supplémentaires pertinentes qu'il possède.

L'expérience professionnelle compte pour 30% du score. Le workflow compare le nombre d'années d'expérience du candidat avec ce qui est requis, examine la pertinence des postes précédemment occupés, et vérifie si le candidat a travaillé dans des secteurs d'activité similaires.

La formation représente 15% du score total. Le workflow vérifie si les diplômes du candidat correspondent à ceux demandés et prend en compte les formations complémentaires pertinentes.

Les compétences comportementales comptent pour 10% du score. Le workflow évalue si le candidat possède les soft skills demandés dans la fiche de poste, comme le leadership, l'autonomie, ou le travail en équipe.

Les langues représentent 5% du score, en vérifiant la maîtrise des langues requises pour le poste.

Enfin, les éléments bonus comptent pour les 5% restants. Le workflow recherche des certifications pertinentes, des contributions à des projets open source, des publications ou participations à des conférences.

Pour chaque critère, le workflow attribue un score de 0 à 100 points, justifie ce score en 2 à 3 phrases, et identifie clairement les points forts et les points faibles du candidat sur ce critère.

Après avoir évalué tous les critères, le workflow calcule le score global pondéré pour chaque candidat en appliquant les pourcentages de pondération. Le score final est arrondi à une décimale et se situe entre 0% et 100%.

## Le rapport final généré

Le workflow produit un rapport professionnel au format Markdown qui présente tous les candidats de manière égale, sans hiérarchie ni classement. Le rapport commence par un résumé de la fiche de poste en 2 à 3 lignes.

Pour chaque candidat, le rapport affiche son nom en titre, son score global en pourcentage, ses coordonnées (email et téléphone), puis une section détaillant les 6 scores par critère avec leurs pondérations. Chaque score est accompagné d'une justification.

Le rapport liste ensuite les points forts du candidat en 3 à 5 points clairs, suivis des points d'attention en 2 à 4 points. Il résume les 2 à 3 expériences professionnelles les plus pertinentes pour le poste, et mentionne les diplômes principaux.

Cette structure est répétée de manière identique pour les 5 candidats, tous présentés au même niveau sans ordre de préférence.

Après avoir présenté tous les candidats, le rapport inclut une section de recommandations divisée en trois catégories. Les candidats ayant obtenu un score supérieur ou égal à 70% sont recommandés pour un entretien, avec une phrase expliquant la raison principale de cette recommandation. Les candidats ayant un score entre 50% et 69% sont placés en réserve, avec une brève justification. Les candidats ayant un score inférieur à 50% sont classés comme non retenus, avec une phrase expliquant la raison principale du rejet.

Enfin, le rapport se termine par une synthèse globale indiquant le nombre total de candidatures analysées (5), le score moyen obtenu, et la liste détaillée des scores de chaque candidat. Le rapport est horodaté avec la date et l'heure de génération.

## Points techniques importants pour la génération

Le premier fichier uploadé est la fiche de poste, les 5 suivants sont les CV. Le workflow doit extraire le contenu de la fiche de poste du premier fichier PDF et l'utiliser comme référence pour toutes les évaluations. Il ne doit pas créer d'exemple de fiche de poste hardcodé dans le code.

Le traitement des 5 CV doit se faire en parallèle pour optimiser les performances et réduire le temps d'exécution total.

Le workflow doit attendre que chaque fichier soit complètement indexé avant de tenter de l'analyser, en utilisant la méthode de vérification de statut et d'attente appropriée.

L'extraction complète des données de CV doit utiliser l'API d'analyse de documents avec polling pour garantir que toutes les informations sont récupérées.

L'évaluation et le scoring doivent utiliser l'API de completion pour analyser objectivement chaque candidat par rapport aux critères de la fiche de poste fournie.

Les scores doivent être calculés de manière factuelle en se basant uniquement sur les données extraites des CV et les critères de la fiche de poste, sans biais ni jugement subjectif.

Le rapport final doit être formaté en Markdown professionnel avec des emojis pour améliorer la lisibilité, mais sans créer de hiérarchie visuelle entre les candidats (pas de médailles, pas de numéros de classement).
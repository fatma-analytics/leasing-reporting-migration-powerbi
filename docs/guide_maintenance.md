# Guide de déploiement et maintenance

## Portée

Ce guide décrit un déploiement Power BI cible et un prototype local. Les environnements, noms d’espaces, propriétaires, droits, passerelles et horaires ci-dessous sont des paramètres à définir par l’organisation; aucune publication dans un tenant réel n’a été effectuée. Le projet ne contient pas de fichier natif `.pbix` (Power BI Desktop non disponible dans l’environnement de réalisation); voir [`powerbi/README.md`](../powerbi/README.md) pour reconstruire le rapport et valider les maquettes.

## Publication dans Power BI Service

1. Dans Power BI Desktop, ouvrir le rapport reconstruit et confirmer la source (ODBC SQLite de démonstration ou connecteur d’entreprise DB2/Oracle). Les identifiants et secrets ne doivent pas être intégrés au fichier ni au dépôt.
2. Publier d’abord dans un espace de travail de développement, puis dans un espace de validation métier, puis dans l’espace de production selon le processus de changement de l’organisation.
3. Configurer la passerelle de données lorsque la source est locale ou privée; vérifier que le compte de service ne dispose que des droits nécessaires. Remplacer SQLite de démonstration par la plateforme de données administrée avant tout usage métier réel.
4. Configurer l’actualisation planifiée après validation des règles de date d’arrêté et du fuseau horaire. À titre de scénario de démonstration seulement : rafraîchissement quotidien hors heures ouvrées et arrêté mensuel signé par le contrôle de gestion.
5. Définir les rôles et droits d’accès par groupe d’entreprise; tester la sécurité au niveau des lignes si les utilisateurs ne doivent voir que leurs territoires. Valider le partage des rapports, l’export des données et la rétention avec les responsables habilités.
6. Surveiller l’historique d’actualisation, les volumes, les erreurs de schéma et le nombre d’anomalies qualité. Une actualisation réussie ne remplace pas l’approbation métier.

## Ajouter ou modifier un indicateur

1. Définir avec le métier le libellé, le grain, la date d’arrêté, la devise, le périmètre, les exclusions et l’exemple de calcul attendu.
2. Modifier la vue SQL correspondante dans `sql/02_views.sql` ou créer une vue versionnée; garder la règle compatible avec le SGBD cible et documenter les adaptations DB2/Oracle.
3. Ajouter/ajuster la mesure dans `powerbi/Measures.dax`, vérifier le contexte des filtres, les valeurs nulles et les périodes sans mouvement.
4. Ajouter au moins un cas positif, un cas limite et un cas de non-régression dans `docs/cahier_de_recette.md` et `recette/recette_resultats.xlsx`.
5. Comparer les valeurs à une source de référence approuvée; expliquer tout écart avant publication. Mettre à jour les captures, la documentation et le `CHANGELOG.md`.

## Checklist de montée de version (exemple type CASSIOPAE)

- [ ] Sauvegarder le PBIX/PBIP, les fichiers source, les scripts SQL et les exports de recette dans un espace versionné et contrôlé.
- [ ] Vérifier l’impact de la version source/CASSIOPAE sur les colonnes, types, clés et règles de gestion; ce dépôt ne se connecte pas à CASSIOPAE.
- [ ] Comparer les schémas et volumes source avant/après; consigner les changements.
- [ ] Exécuter les tests Python et les contrôles `v_controles_qualite`.
- [ ] Rejouer les rapprochements de production, encours et impayés sur une date d’arrêté définie.
- [ ] Faire approuver les écarts par les propriétaires métier; ne pas assimiler un écart attendu à une anomalie corrigée sans validation.
- [ ] Contrôler le modèle, les relations, les segments, les navigations, les alertes et les droits dans Power BI Desktop.
- [ ] Déployer d’abord en validation; vérifier l’actualisation de bout en bout via la passerelle.
- [ ] Obtenir le visa métier/DSI, mettre à jour la version, les notes de livraison et le plan de retour arrière.
- [ ] Publier en production et surveiller le premier cycle; documenter l’incident et revenir à la version précédente si les seuils convenus sont dépassés.

## Rôles proposés

| Rôle | Responsabilité |
|---|---|
| Contrôle de gestion | Définit les indicateurs et signe les résultats de recette |
| Data/BI | Maintient SQL, modèle sémantique, mesures DAX et tests |
| DSI / DBA | Gère le SGBD, les accès, la passerelle, les sauvegardes et les changements de schéma |
| Propriétaire métier | Autorise la publication et les droits d’accès |

## Dépannage courant

- **Montant différent :** contrôler le grain (contrat vs échéance vs paiement), doublons, dates d’arrêté et règle de capital/intérêts.
- **Taux d’impayés instable :** vérifier que le numérateur reste à payer et le dénominateur échéances échues utilisent le même périmètre et la même date.
- **Rafraîchissement en échec :** confirmer le DSN/pilote, l’accès de la passerelle au fichier source, les types, le temps d’exécution et les droits du compte de service.
- **Filtre territoire incohérent :** contrôler les clés de relation, l’unicité de la dimension et l’absence de chemins multiples/bidirectionnels involontaires.

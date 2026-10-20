# Données de démonstration

Tous les fichiers de ce dossier sont générés localement par `scripts/generate_data.py`; ils ne proviennent pas d’un client, d’un employeur ni d’un jeu externe. Les identités et raisons sociales sont des valeurs Faker fictives. Le générateur est déterministe avec une graine documentée dans `manifest.json`.

Les CSV `contrats.csv`, `echeances.csv` et `paiements.csv` conservent les anomalies injectées pour l’exercice qualité. `expected_anomalies.csv` décrit les volumes injectés; `controles_qualite.csv` donne les lignes réellement signalées par les contrôles SQL (les deux occurrences d’une clé dupliquée sont comptées dans le résultat de détection). `leasing_demo.sqlite` est le mart décisionnel après déduplication et rejet contrôlé des données invalides; il contient également le staging et les vues SQL. Ne pas utiliser les fichiers `stg_` comme sources de mesures métiers.

La date de référence de démonstration est le 31 mars 2026. Pour reconstruire tous les fichiers : exécuter d’abord `python scripts/generate_data.py`, puis `python scripts/build_project.py` depuis la racine du dépôt.

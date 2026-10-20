# Cahier de recette — migration des reportings leasing

**Environnement :** jeu entièrement synthétique, SQLite local, arrêté au 31/03/2026. Les valeurs de référence sont produites par `scripts/build_project.py`, reprises dans [`recette_resultats.xlsx`](../recette/recette_resultats.xlsx) et recalculables à partir des CSV. Les deux premiers cas documentent des écarts constatés et corrigés. Les tests SQL et de cohérence sont exécutables dans ce dépôt; deux tests d’interaction nécessitent un vrai rapport ouvert dans Power BI Desktop et restent explicitement « À valider Desktop ».

| ID | Type | Cas / source | Résultat attendu | Statut |
|---|---|---|---|---|
| R01 | Non-régression | Production déc. 2025, crédit-bail, Île-de-France — export de type BO vs `v_production_mensuelle` | Le brut 19 contrats / 1 746 243,04 EUR est rapproché du périmètre nettoyé 16 contrats / 1 694 763,44 EUR; écart expliqué par des lignes qualité | Corrigé et vérifié |
| R02 | Non-régression | Encours au 31/03/2026 — formule de l’ancien classeur vs échéancier SQL | `FactEncours` somme le principal restant; le calcul hérité retranchait les paiements d’intérêts du capital initial | Corrigé et vérifié; valeur calculée dans le classeur |
| R03 | Fonctionnel | Segment territoire sur les pages et navigation inter-pages | Le segment filtre les faits concernés; sa persistance est cohérente pendant la navigation | À valider dans Power BI Desktop |
| R04 | Actualisation | Ajouter un contrat valide dans une copie du fichier source et actualiser | Le nouveau contrat est intégré une seule fois dans le modèle et les agrégats sont recalculés | Procédure documentée; exécution Desktop à valider |
| R05 | Qualité / clé | Doublons `contrat_id` en staging | Les occurrences sont signalées; le contrat nettoyé est unique | Réussi — clés nettoyées uniques |
| R06 | Qualité / intégrité | Échéances rattachées à un contrat absent | Toutes les échéances orphelines du staging apparaissent au contrôle et sont rejetées du mart | Réussi |
| R07 | Qualité / dates | `date_fin_prevue < date_debut` | Toutes les lignes incohérentes sont détectées avant chargement | Réussi |
| R08 | Qualité / montant | `montant_finance <= 0` | Tous les financements invalides sont signalés et non chargés | Réussi |
| R09 | Qualité / montant | `montant_du <= 0` | Toutes les échéances invalides sont signalées et non chargées | Réussi |
| R10 | Qualité / paiements | Paiement unitaire supérieur au montant dû | Toutes les lignes de surpaiement sont détectées; elles ne gonflent pas l’encours métier | Réussi |
| R11 | Fonctionnel / risque | Retard >90 jours | Les échéances dépassant le seuil alimentent le compteur et la liste de surveillance | Réussi sur `v_impayes` |
| R12 | Non-régression | Tranche de retard | La tranche SQL correspond à la règle de référence Python pour chaque ligne d’impayé | Réussi — 0 écart |
| R13 | Rapprochement | Tous les regroupements de production | Comparaison au même grain mois × produit × territoire après règles qualité; les divergences legacy initiales sont consignées | Réussi — 55 regroupements legacy divergents expliqués |
| R14 | Intégrité | Reste à payer des lignes de `v_impayes` | Chaque ligne visible a un reste strictement positif | Réussi — 0 ligne non positive |
| R15 | Qualité / exploitation | Vue de résultats des contrôles | Les sept familles de contrôles sont retournées avec un décompte d’anomalies | Réussi — 7 contrôles, résultat dans `data/controles_qualite.csv` |

## Écarts trouvés et corrigés

1. **Production:** l’export legacy lit le staging brut. L’exemple R01 présente des copies et lignes volontairement invalides; le flux de migration élimine les occurrences dupliquées et rejette les dates/montants incohérents avant l’agrégat. Le contrôle ne masque pas l’écart : l’ancien et le nouveau périmètre restent comparables et les motifs d’exclusion sont consignés.
2. **Encours:** la formule Excel simulée soustrait les encaissements totaux du financement initial; elle traite donc les intérêts perçus comme du capital remboursé. Le calcul corrigé applique la part de paiement au montant et à la composante capital de chaque échéance, à la date d’arrêté.

Les statuts « réussi » concernent les données, vues et calculs reproductibles exécutés dans SQLite/Python. Ils ne constituent pas une recette visuelle d’un PBIX; les interactions Power BI nécessitent Desktop et restent identifiées comme telles.

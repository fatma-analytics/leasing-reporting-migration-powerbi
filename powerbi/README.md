# Pack de reconstruction Power BI

> **État du livrable :** le dépôt contient le modèle SQL, le dictionnaire des relations, le DAX, une requête Power Query indicative et cinq maquettes PNG. Il ne contient **pas** de fichier natif `Reporting_Leasing.pbix` : Power BI Desktop n’est pas disponible dans cet environnement Linux. Les PNG sont des rendus depuis les données synthétiques, et non des captures de Power BI. Aucun binaire factice n’est fourni.

## Modèle cible

Le modèle est en étoile à plusieurs faits. Les relations sont à sens unique, de la dimension vers le fait, cardinalité 1 → *. Les tables SQL et les vues `v_` sont créées par `python scripts/build_project.py` dans `data/leasing_demo.sqlite`.

| Table Power BI | Rôle / grain | Clés et contenu |
|---|---|---|
| `FactContrats` (`contrats`) | Un contrat accepté | `contrat_id`, client, bien, produit, date et montant financé |
| `FactEcheances` (`echeances`) | Une échéance contractuelle | `echeance_id`, contrat, dates, montant dû, capital et intérêt |
| `FactPaiements` (`paiements`) | Un paiement accepté | `paiement_id`, échéance, date et montant payé |
| `FactProduction` (`v_production_mensuelle`) | Un mois × produit × territoire | Nombre de contrats et montant de production agrégés |
| `FactEncours` (`v_encours`) | Un contrat × un mois | Solde de capital après amortissement, attributs de portefeuille |
| `FactImpayes` (`v_impayes`) | Une échéance échue partiellement ou non payée au snapshot | Reste à payer, retard et tranche |
| `DimClient` (`clients`) | Un client fictif | Type, secteur, territoire |
| `DimBien` (`biens`) | Un bien financé | Catégorie, marque, valeur, fournisseur |
| `DimTerritoire` (`dim_territoire`) | Un territoire ultramarin ou hexagonal | Île-de-France, Guadeloupe, Martinique, Réunion, Guyane |
| `DimMois` (`dim_mois`) | Un mois de calendrier | Mois, début/fin, année et numéro du mois |

Relations recommandées : `DimClient[client_id]` vers les faits contenant `client_id`; `DimBien[bien_id]` vers `FactContrats` et `FactEncours`; `DimTerritoire[territoire_nom]` vers les faits de production/encours/impayés (un seul chemin actif par fait); `DimMois[mois]` vers les clés `mois_production`/`mois`/`mois_echeance`; `FactContrats[contrat_id]` vers une dimension de contrat mince (ou table de correspondance distincte) avant de filtrer les faits échéance/paiement. Ne pas créer de relation plusieurs-à-plusieurs ni de filtre bidirectionnel sans besoin validé. Les chemins réels dépendent des vues exposées; contrôler l’absence d’ambiguïté dans la vue Modèle.

Pour une modélisation propre des paiements, agréger d’abord `FactPaiements` par `echeance_id` et date d’arrêté; ne pas relier deux faits plusieurs-à-plusieurs. `v_encours` et `v_impayes` préparent déjà ces agrégats pour les visuels. La date d’arrêté de démo est le 31/03/2026; la rendre paramétrable avant tout usage opérationnel.

## Mesures DAX

Voir [`Measures.dax`](Measures.dax). Les noms de tables y sont les alias de la table ci-dessus; adapter les noms si Power Query renomme les objets. `DimMois[date_debut]` doit être typée Date et marquée comme table de dates. Les filtres des pages doivent être testés avec les cinq territoires.

## Recréation locale

1. Installer Power BI Desktop (Windows) et créer un rapport vierge.
2. Créer un DSN ODBC SQLite nommé `LeasingDemo` pointant vers `data/leasing_demo.sqlite`, ou remplacer cette connexion par le connecteur DB2/Oracle de l’environnement cible.
3. Charger les dimensions, faits et vues nettoyées; ne pas charger les tables `stg_` dans les visuels de gestion.
4. Créer les relations et mesures, puis les cinq pages décrites dans le README racine.
5. Valider les 15 cas du classeur de recette, notamment les cas marqués « Desktop ».
6. Enregistrer le fichier natif sous `powerbi/Reporting_Leasing.pbix`, exporter les cinq captures depuis Power BI Desktop, puis mettre à jour le README.

`powerbi/PowerQuery.m` fournit un point de départ ODBC; il nécessite un pilote SQLite compatible installé localement. Pour DB2/Oracle, remplacer le DSN par le connecteur certifié de l’entreprise et garder les règles métier des vues.

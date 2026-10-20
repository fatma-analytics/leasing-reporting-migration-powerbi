# Analyse de l’existant

## Périmètre et hypothèses

Ce projet est un cas d’école de migration pour une société de financement locatif fictive. Les classeurs `legacy_reports/` sont des **reproductions synthétiques au format Excel** de reportings auparavant décrits comme Excel et états de type Business Objects. SAP BusinessObjects n’étant pas disponible en open source dans ce dépôt, aucun univers, document ou capture Business Objects authentique n’est prétendu. Les valeurs proviennent exclusivement du jeu synthétique décrit dans `data/manifest.json`.

La date d’arrêté utilisée pour les tests est le 31 mars 2026. Les « limites constatées » ci-dessous sont les risques simulés par le cas d’école, pas un audit de BRED Cofilease ni d’un client réel.

## 1. État de production mensuelle — export de type BO

**Indicateurs et règles reproduites.** Production mensuelle = nombre de contrats signés sur le mois; montant de production = somme des montants financés à la signature. Les axes de ventilation sont le produit (LOA, LLD, crédit-bail) et le territoire du client. L’export `Etat_BO_Production_Mensuelle.xlsx` représente le périmètre brut avant les contrôles afin de rendre visibles les écarts de qualité.

**Limites modélisées.** Export tabulaire statique, retraitement manuel des identifiants et absence de journal de rejets. Dans le scénario de décembre 2025, crédit-bail, Île-de-France, le staging brut produit 19 contrats et 1 746 243,04 EUR; l’agrégat nettoyé en retient 16 et 1 694 763,44 EUR. L’écart est imputable aux copies et lignes invalides volontairement injectées; il est documenté dans la recette, pas masqué.

**Correspondance cible.** `v_production_mensuelle` porte le grain mois × produit × territoire. Dans Power BI, le graphique mensuel, les segments produit/territoire/catégorie/apporteur et les mesures `Production Mois`, `Production YTD` et `Variation M-1 %` remplacent le filtre/export manuel.

## 2. Reporting Excel d’encours

**Indicateurs et règles reproduites.** Encours par catégorie de bien, contrat et territoire au 31/03/2026. La mesure métier cible est le principal restant dû, soit montant financé diminué du capital remboursé calculé sur l’échéancier amortissable.

**Limites modélisées.** L’onglet « TCD Encours » est une synthèse statique de style TCD (ce n’est pas un objet TCD Excel natif). Le calcul hérité simulé retranche le total des paiements, intérêts inclus, au capital initial; cette approximation sous-estime l’encours. Le fichier expose l’ancienne valeur et la valeur SQL corrigée côte à côte afin de tracer l’écart.

**Correspondance cible.** `v_encours`, au grain contrat × mois, consolide le capital restant, la catégorie, le territoire, le produit et le statut. Les visuels de portefeuille et les mesures `Encours Total` / `Variation M-1 %` remplacent les formules copiées de feuille en feuille.

## 3. Suivi des impayés Excel

**Indicateurs et règles reproduites.** Échéances échues non réglées intégralement, reste à payer (montant dû moins les paiements admis), nombre d’échéances et répartition en tranches 0–30, 31–60, 61–90 et >90 jours de retard. Le taux de démo est le reste à payer rapporté au total des échéances échues au même arrêté.

**Limites modélisées.** Extraction figée, actualisation manuelle, risque d’oublier des paiements partiels et règles d’ancienneté peu auditables. La date d’arrêté et la formule sont exposées explicitement dans les feuilles de synthèse et de détail.

**Correspondance cible.** `v_impayes` conserve le détail des échéances en retard, le reste à payer, le nombre de jours et la tranche. La page de surveillance remplace les listes manuelles par des filtres territoriaux, un classement des contrats à risque et une mise en couleur par seuil. La page Qualité affiche les lignes rejetées séparément de la mesure métier.

## Principes de migration

1. Conserver les fichiers sources bruts (`stg_`) pour mesurer et expliquer les rejets.
2. Faire les contrôles avant insertion dans les tables normalisées contraintes.
3. Dédupliquer par clé de contrat, exclure les contrats dont les dates sont incohérentes ou dont le financement est négatif, retirer les échéances orphelines/négatives, puis écarter les paiements supérieurs au montant dû.
4. Garder un contrôle et une traçabilité des lignes écartées; les rejets ne sont pas silencieusement réécrits comme données valides.
5. Comparer les mesures après alignement du périmètre, du grain, de la date d’arrêté et de la règle d’encours.

Le prototype utilise SQLite pour la reproductibilité locale. Les types, jointures, agrégations, `CASE`, `COALESCE`, clés et règles métier privilégient un SQL portable vers PostgreSQL/DB2/Oracle. Le DDL, les types de dates et la syntaxe `CREATE VIEW IF NOT EXISTS` nécessitent des ajustements mineurs propres au SGBD cible; aucun plug-and-play DB2/Oracle n’est revendiqué.

// Modèle Power Query (M) indicatif — nécessite un pilote ODBC SQLite et un DSN nommé LeasingDemo.
// Les noms d'objets correspondent à la base générée dans data/leasing_demo.sqlite.
// Adapter le DSN/driver à DB2 ou Oracle dans l'environnement d'entreprise.

let
    Source = Odbc.DataSource("dsn=LeasingDemo", [HierarchicalNavigation=true]),
    Database = Source{[Name="LeasingDemo", Kind="Database"]}[Data],
    Contrats = Database{[Name="contrats", Kind="Table"]}[Data]
in
    Contrats

// Créer une requête par table/vue en adaptant la dernière ligne :
// Database{[Name="clients", Kind="Table"]}[Data]
// Database{[Name="biens", Kind="Table"]}[Data]
// Database{[Name="echeances", Kind="Table"]}[Data]
// Database{[Name="paiements", Kind="Table"]}[Data]
// Database{[Name="v_production_mensuelle", Kind="View"]}[Data]
// Database{[Name="v_encours", Kind="View"]}[Data]
// Database{[Name="v_impayes", Kind="View"]}[Data]
// Database{[Name="v_controles_qualite", Kind="View"]}[Data]
// Ne charger les tables stg_ que dans une page technique restreinte, jamais comme données de gestion.

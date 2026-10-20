-- Socle relationnel du prototype. Les scripts privilégient types et expressions SQL portables.
-- Staging : conserve les anomalies source sans clés/contraintes afin de les mesurer avant le nettoyage.

CREATE TABLE IF NOT EXISTS dim_territoire (
    territoire_id VARCHAR(12) PRIMARY KEY,
    territoire_nom VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_mois (
    mois VARCHAR(7) PRIMARY KEY,
    date_debut VARCHAR(10) NOT NULL,
    date_fin VARCHAR(10) NOT NULL,
    jour_fin_ordinal INTEGER NOT NULL,
    annee INTEGER NOT NULL,
    numero_mois INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS parametres (
    parametre_id INTEGER PRIMARY KEY,
    date_reference VARCHAR(10) NOT NULL,
    jour_reference_ordinal INTEGER NOT NULL,
    devise VARCHAR(3) NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    client_id VARCHAR(16) PRIMARY KEY,
    type_client VARCHAR(20) NOT NULL CHECK (type_client IN ('particulier', 'professionnel')),
    territoire_id VARCHAR(12) NOT NULL,
    secteur VARCHAR(40) NOT NULL,
    date_entree VARCHAR(10) NOT NULL,
    raison_sociale_fictive VARCHAR(120) NOT NULL,
    FOREIGN KEY (territoire_id) REFERENCES dim_territoire(territoire_id)
);

CREATE TABLE IF NOT EXISTS biens (
    bien_id VARCHAR(16) PRIMARY KEY,
    categorie VARCHAR(20) NOT NULL CHECK (categorie IN ('auto', 'materiel', 'bateau')),
    marque VARCHAR(60) NOT NULL,
    valeur_achat DECIMAL(14,2) NOT NULL CHECK (valeur_achat >= 0),
    fournisseur VARCHAR(80) NOT NULL
);

CREATE TABLE IF NOT EXISTS contrats (
    contrat_id VARCHAR(16) PRIMARY KEY,
    client_id VARCHAR(16) NOT NULL,
    bien_id VARCHAR(16) NOT NULL,
    produit VARCHAR(20) NOT NULL CHECK (produit IN ('LOA', 'LLD', 'crédit-bail')),
    date_debut VARCHAR(10) NOT NULL,
    date_fin_prevue VARCHAR(10) NOT NULL,
    duree_mois INTEGER NOT NULL CHECK (duree_mois > 0),
    montant_finance DECIMAL(14,2) NOT NULL CHECK (montant_finance > 0),
    taux_annuel DECIMAL(8,5) NOT NULL CHECK (taux_annuel >= 0),
    statut VARCHAR(20) NOT NULL CHECK (statut IN ('actif', 'soldé', 'contentieux')),
    apporteur VARCHAR(60) NOT NULL,
    mois_production VARCHAR(7) NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(client_id),
    FOREIGN KEY (bien_id) REFERENCES biens(bien_id)
);

CREATE TABLE IF NOT EXISTS echeances (
    echeance_id VARCHAR(20) PRIMARY KEY,
    contrat_id VARCHAR(16) NOT NULL,
    date_echeance VARCHAR(10) NOT NULL,
    date_echeance_ordinal INTEGER NOT NULL,
    mois_echeance VARCHAR(7) NOT NULL,
    montant_du DECIMAL(14,2) NOT NULL CHECK (montant_du > 0),
    montant_capital DECIMAL(14,2) NOT NULL CHECK (montant_capital >= 0),
    montant_interet DECIMAL(14,2) NOT NULL CHECK (montant_interet >= 0),
    FOREIGN KEY (contrat_id) REFERENCES contrats(contrat_id)
);

CREATE TABLE IF NOT EXISTS paiements (
    paiement_id VARCHAR(20) PRIMARY KEY,
    echeance_id VARCHAR(20) NOT NULL,
    date_paiement VARCHAR(10) NOT NULL,
    montant_paye DECIMAL(14,2) NOT NULL CHECK (montant_paye > 0),
    FOREIGN KEY (echeance_id) REFERENCES echeances(echeance_id)
);

-- Tables brutes de contrôle : mêmes noms/colonnes que les fichiers CSV.
-- Pas de clés uniques ou de clés étrangères par conception.
CREATE TABLE IF NOT EXISTS stg_contrats (
    contrat_id VARCHAR(16), client_id VARCHAR(16), bien_id VARCHAR(16), produit VARCHAR(20),
    date_debut VARCHAR(10), date_fin_prevue VARCHAR(10), date_debut_ordinal INTEGER,
    duree_mois INTEGER, montant_finance DECIMAL(14,2), taux_annuel DECIMAL(8,5),
    statut VARCHAR(20), apporteur VARCHAR(60), mois_production VARCHAR(7)
);
CREATE TABLE IF NOT EXISTS stg_echeances (
    echeance_id VARCHAR(20), contrat_id VARCHAR(16), date_echeance VARCHAR(10),
    date_echeance_ordinal INTEGER, mois_echeance VARCHAR(7), montant_du DECIMAL(14,2),
    montant_capital DECIMAL(14,2), montant_interet DECIMAL(14,2)
);
CREATE TABLE IF NOT EXISTS stg_paiements (
    paiement_id VARCHAR(20), echeance_id VARCHAR(20), date_paiement VARCHAR(10), montant_paye DECIMAL(14,2)
);

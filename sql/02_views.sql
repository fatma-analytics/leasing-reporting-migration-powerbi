-- Les vues sont calculées sur le périmètre nettoyé (tables sans préfixe stg_).
-- Les dates sont conservées au format ISO YYYY-MM-DD pour les comparaisons portables.

CREATE VIEW IF NOT EXISTS v_production_mensuelle AS
SELECT
    c.mois_production,
    c.produit,
    t.territoire_nom AS territoire,
    COUNT(*) AS nb_contrats,
    SUM(c.montant_finance) AS montant_production
FROM contrats c
JOIN clients cl ON cl.client_id = c.client_id
JOIN dim_territoire t ON t.territoire_id = cl.territoire_id
GROUP BY c.mois_production, c.produit, t.territoire_nom;

-- Encours calculé par mois sur la base du capital financé diminué du capital payé.
-- Le paiement cumulé par échéance est plafonné au montant dû : un surpaiement
-- détecté au staging ne crée jamais un encours négatif dans le modèle.
CREATE VIEW IF NOT EXISTS v_encours AS
WITH paiement_echeance_mois AS (
    SELECT
        e.echeance_id,
        e.contrat_id,
        e.mois_echeance,
        e.date_echeance,
        e.montant_du,
        e.montant_capital,
        m.mois,
        m.date_fin,
        COALESCE(SUM(p.montant_paye), 0) AS montant_paye_cumule
    FROM echeances e
    JOIN dim_mois m ON e.date_echeance <= m.date_fin
    LEFT JOIN paiements p
        ON p.echeance_id = e.echeance_id
       AND p.date_paiement <= m.date_fin
    GROUP BY e.echeance_id, e.contrat_id, e.mois_echeance,
             e.date_echeance, e.montant_du, e.montant_capital,
             m.mois, m.date_fin
), capital_rembourse_mois AS (
    SELECT
        contrat_id,
        mois,
        SUM(montant_capital *
            CASE
                WHEN montant_paye_cumule >= montant_du THEN 1.0
                ELSE montant_paye_cumule / NULLIF(montant_du, 0)
            END
        ) AS capital_rembourse
    FROM paiement_echeance_mois
    GROUP BY contrat_id, mois
)
SELECT
    c.contrat_id,
    m.mois,
    c.client_id,
    c.bien_id,
    c.produit,
    t.territoire_nom AS territoire,
    b.categorie,
    c.statut,
    c.montant_finance - COALESCE(r.capital_rembourse, 0) AS encours_capital
FROM contrats c
JOIN clients cl ON cl.client_id = c.client_id
JOIN dim_territoire t ON t.territoire_id = cl.territoire_id
JOIN biens b ON b.bien_id = c.bien_id
JOIN dim_mois m ON m.mois >= c.mois_production
LEFT JOIN capital_rembourse_mois r
    ON r.contrat_id = c.contrat_id AND r.mois = m.mois;

CREATE VIEW IF NOT EXISTS v_impayes AS
SELECT
    e.echeance_id,
    e.contrat_id,
    c.client_id,
    cl.territoire_id,
    t.territoire_nom AS territoire,
    b.categorie,
    c.produit,
    c.statut,
    e.date_echeance,
    e.montant_du,
    COALESCE(SUM(p.montant_paye), 0) AS montant_paye,
    e.montant_du - COALESCE(SUM(p.montant_paye), 0) AS reste_a_payer,
    pr.jour_reference_ordinal - e.date_echeance_ordinal AS retard_jours,
    CASE
        WHEN pr.jour_reference_ordinal - e.date_echeance_ordinal BETWEEN 0 AND 30 THEN '0-30 jours'
        WHEN pr.jour_reference_ordinal - e.date_echeance_ordinal BETWEEN 31 AND 60 THEN '31-60 jours'
        WHEN pr.jour_reference_ordinal - e.date_echeance_ordinal BETWEEN 61 AND 90 THEN '61-90 jours'
        ELSE '>90 jours'
    END AS tranche_retard
FROM echeances e
JOIN contrats c ON c.contrat_id = e.contrat_id
JOIN clients cl ON cl.client_id = c.client_id
JOIN dim_territoire t ON t.territoire_id = cl.territoire_id
JOIN biens b ON b.bien_id = c.bien_id
CROSS JOIN parametres pr
LEFT JOIN paiements p ON p.echeance_id = e.echeance_id AND p.date_paiement <= pr.date_reference
WHERE e.date_echeance < pr.date_reference
GROUP BY e.echeance_id, e.contrat_id, c.client_id, cl.territoire_id,
         t.territoire_nom, b.categorie, c.produit, c.statut, e.date_echeance,
         e.montant_du, e.date_echeance_ordinal, pr.jour_reference_ordinal
HAVING e.montant_du - COALESCE(SUM(p.montant_paye), 0) > 0;

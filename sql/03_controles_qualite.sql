-- Exécuter sur les tables stg_ avant nettoyage. Chaque SELECT renvoie un contrôle
-- et son nombre de lignes suspectes. L'utilisation de EXISTS et CASE reste portable.

CREATE VIEW IF NOT EXISTS v_controles_qualite AS
SELECT 'CONTRATS_DOUBLONS' AS controle, COUNT(*) AS anomalies,
       'Lignes appartenant à une clé contrat dupliquée, copie originale incluse.' AS description
FROM stg_contrats s
WHERE EXISTS (
    SELECT 1 FROM stg_contrats d
    WHERE d.contrat_id = s.contrat_id
    GROUP BY d.contrat_id HAVING COUNT(*) > 1
)
UNION ALL
SELECT 'ECHEANCES_ORPHELINES', COUNT(*), 'Échéances dont le contrat est absent du staging.'
FROM stg_echeances e
WHERE NOT EXISTS (SELECT 1 FROM stg_contrats c WHERE c.contrat_id = e.contrat_id)
UNION ALL
SELECT 'CONTRATS_DATES_INCOHERENTES', COUNT(*), 'Date de fin prévue antérieure à la date de début.'
FROM stg_contrats
WHERE date_fin_prevue < date_debut
UNION ALL
SELECT 'CONTRATS_MONTANTS_NEGATIFS', COUNT(*), 'Montant financé négatif ou nul.'
FROM stg_contrats
WHERE montant_finance <= 0
UNION ALL
SELECT 'ECHEANCES_MONTANTS_NEGATIFS', COUNT(*), 'Montant dû négatif ou nul.'
FROM stg_echeances
WHERE montant_du <= 0
UNION ALL
SELECT 'PAIEMENTS_SUPERIEURS_AU_DU', COUNT(*), 'Paiement unitaire supérieur au montant dû de son échéance.'
FROM stg_paiements p
WHERE p.montant_paye > COALESCE((
    SELECT e.montant_du FROM stg_echeances e WHERE e.echeance_id = p.echeance_id
), 0)
UNION ALL
SELECT 'PAIEMENTS_ECHEANCE_ABSENTE', COUNT(*), 'Paiements dont l’échéance source est absente.'
FROM stg_paiements p
WHERE NOT EXISTS (SELECT 1 FROM stg_echeances e WHERE e.echeance_id = p.echeance_id);

-- Exemples de lecture autonome :
-- SELECT controle, anomalies FROM v_controles_qualite ORDER BY controle;
-- SELECT contrat_id, COUNT(*) AS occurrences FROM stg_contrats GROUP BY contrat_id HAVING COUNT(*) > 1;
-- SELECT e.echeance_id FROM stg_echeances e WHERE NOT EXISTS
--   (SELECT 1 FROM stg_contrats c WHERE c.contrat_id = e.contrat_id);
-- SELECT contrat_id FROM stg_contrats WHERE date_fin_prevue < date_debut;
-- SELECT paiement_id, echeance_id, montant_paye FROM stg_paiements
--   WHERE montant_paye > (SELECT montant_du FROM stg_echeances e WHERE e.echeance_id = stg_paiements.echeance_id);

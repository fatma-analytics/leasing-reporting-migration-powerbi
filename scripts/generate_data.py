#!/usr/bin/env python3
"""Generate deterministic, explicitly synthetic leasing data and controlled anomalies."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

REFERENCE_DATE = date(2026, 3, 31)
START_MONTH = "2024-04"
END_MONTH = "2026-03"
SEED = 20260331
TERRITORIES = ["Île-de-France", "Guadeloupe", "Martinique", "Réunion", "Guyane"]


def month_add(d: date, months: int) -> date:
    month0 = d.month - 1 + months
    year = d.year + month0 // 12
    month = month0 % 12 + 1
    day = min(d.day, pd.Timestamp(year=year, month=month, day=1).days_in_month)
    return date(year, month, day)


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def month_end(d: date) -> date:
    return (pd.Timestamp(d) + pd.offsets.MonthEnd(0)).date()


def iso(d: date) -> str:
    return d.isoformat()


def make_data(out: Path, seed: int = SEED, n_contracts: int = 2000) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    fake = Faker("fr_FR")
    Faker.seed(seed)
    ref_ord = REFERENCE_DATE.toordinal()

    # Dimensions: one synthetic customer per account, independent from real people.
    n_clients = 1500
    territory = rng.choice(TERRITORIES, n_clients, p=[0.67, 0.09, 0.08, 0.10, 0.06])
    clients = pd.DataFrame({
        "client_id": [f"CLI-{i:05d}" for i in range(1, n_clients + 1)],
        "type_client": rng.choice(["particulier", "professionnel"], n_clients, p=[0.69, 0.31]),
        "territoire": territory,
        "secteur": [rng.choice(["Transport", "BTP", "Santé", "Commerce", "Agriculture", "Services", "Particulier"])
                    if t == "professionnel" else "Particulier" for t in territory],
        "date_entree": [iso(date(2018, 1, 1) + pd.Timedelta(days=int(x)))
                        for x in rng.integers(0, 3000, n_clients)],
        "raison_sociale_fictive": [fake.company() if rng.random() < 0.31 else fake.name() for _ in range(n_clients)],
    })

    categories = rng.choice(["auto", "materiel", "bateau"], n_contracts, p=[0.61, 0.31, 0.08])
    brand_map = {
        "auto": ["Renault", "Peugeot", "Toyota", "Volkswagen", "Citroën", "Dacia"],
        "materiel": ["Caterpillar", "Manitou", "JCB", "John Deere", "Komatsu"],
        "bateau": ["Beneteau", "Jeanneau", "Zodiac", "Quicksilver", "Groupe Fountaine"],
    }
    vendors = ["Hexa Distribution", "Océan Équipements", "Caraïbe Mobilité", "Nord-Sud Auto", "Atlas Pro"]
    biens = pd.DataFrame({
        "bien_id": [f"BIE-{i:05d}" for i in range(1, n_contracts + 1)],
        "categorie": categories,
        "marque": [rng.choice(brand_map[c]) for c in categories],
        "valeur_achat": [round(float(rng.uniform(11_000, 85_000) if c == "auto" else
                                            rng.uniform(12_000, 220_000) if c == "materiel" else
                                            rng.uniform(25_000, 320_000)), 2) for c in categories],
        "fournisseur": rng.choice(vendors, n_contracts),
    })

    # Generate an amortizing monthly schedule for every contract.
    month_starts = pd.date_range(f"{START_MONTH}-01", f"{END_MONTH}-01", freq="MS")
    contract_rows: list[dict] = []
    due_rows: list[dict] = []
    pay_rows: list[dict] = []
    due_seq = 1
    pay_seq = 1

    for i in range(n_contracts):
        cid = f"CTR-{i+1:05d}"
        client_id = f"CLI-{int(rng.integers(1, n_clients+1)):05d}"
        asset = biens.iloc[i]
        start_month = pd.Timestamp(rng.choice(month_starts)).date()
        start_date = start_month + pd.Timedelta(days=int(rng.integers(0, min(27, month_end(start_month).day-1))))
        start_date = start_date.date() if hasattr(start_date, "date") else start_date
        duration = int(rng.choice([12, 18, 24, 30, 36, 48, 60], p=[0.07, 0.07, 0.26, 0.10, 0.29, 0.13, 0.08]))
        end_date = month_add(start_date, duration)
        product = {"auto": rng.choice(["LOA", "LLD"], p=[0.61, 0.39]),
                   "materiel": "crédit-bail", "bateau": "LOA"}[asset.categorie]
        financed = round(float(asset.valeur_achat * rng.uniform(0.70, 0.96)), 2)
        annual_rate = round(float(rng.uniform(0.025, 0.089)), 5)
        monthly_rate = annual_rate / 12
        payment = financed * monthly_rate / (1 - (1 + monthly_rate) ** (-duration)) if monthly_rate else financed / duration
        remaining = financed

        # Generate clean installment and payment rows first.
        for k in range(1, duration + 1):
            due_date = month_add(start_date, k)
            interest = round(remaining * monthly_rate, 2)
            principal = round(payment - interest, 2)
            if k == duration:
                principal = round(remaining, 2)
                installment = round(principal + interest, 2)
            else:
                installment = round(principal + interest, 2)
            principal = min(principal, remaining)
            remaining = max(0.0, round(remaining - principal, 2))
            if due_date > REFERENCE_DATE + pd.Timedelta(days=90):
                continue
            eid = f"ECH-{due_seq:07d}"
            due_seq += 1
            due_ord = due_date.toordinal()
            due_rows.append({
                "echeance_id": eid, "contrat_id": cid, "date_echeance": iso(due_date),
                "date_echeance_ordinal": due_ord, "mois_echeance": f"{due_date.year:04d}-{due_date.month:02d}",
                "montant_du": installment, "montant_capital": principal, "montant_interet": interest,
            })
            if due_date <= REFERENCE_DATE:
                risk = float(rng.random())
                if risk < 0.073:
                    paid_fraction = 0.0
                elif risk < 0.095:
                    paid_fraction = float(rng.uniform(0.25, 0.80))
                else:
                    paid_fraction = 1.0
                if paid_fraction > 0:
                    paid = round(installment * paid_fraction, 2)
                    if paid_fraction == 1.0:
                        # Payment is on/before due date to retain a realistic paid history.
                        pay_date = due_date - pd.Timedelta(days=int(rng.integers(0, 18)))
                    else:
                        pay_date = due_date + pd.Timedelta(days=int(rng.integers(1, 45)))
                    pay_date = pay_date.date() if hasattr(pay_date, "date") else pay_date
                    pay_rows.append({"paiement_id": f"PAY-{pay_seq:07d}", "echeance_id": eid,
                                     "date_paiement": iso(pay_date), "montant_paye": paid})
                    pay_seq += 1

        # Status at the project snapshot; derive from maturity and persistent arrears.
        end_ord = end_date.toordinal()
        if end_date <= REFERENCE_DATE and rng.random() < 0.82:
            status = "soldé"
        else:
            status = "actif"
        if rng.random() < 0.045:
            status = "contentieux"
        contract_rows.append({
            "contrat_id": cid, "client_id": client_id, "bien_id": asset.bien_id,
            "produit": product, "date_debut": iso(start_date), "date_fin_prevue": iso(end_date),
            "date_debut_ordinal": start_date.toordinal(), "duree_mois": duration,
            "montant_finance": financed, "taux_annuel": annual_rate, "statut": status,
            "apporteur": rng.choice(["Réseau direct", "Courtage", "Partenaire constructeur", "Agence ultramarine"]),
            "mois_production": f"{start_date.year:04d}-{start_date.month:02d}",
        })

    clients["type_client"] = clients["type_client"].astype(str)
    biens = biens.copy()
    contrats_clean = pd.DataFrame(contract_rows)
    echeances_clean = pd.DataFrame(due_rows)
    paiements_clean = pd.DataFrame(pay_rows)

    # Inject approximately 1-2% deliberate defects per affected source table.
    n_dup = max(1, round(n_contracts * 0.01))
    duplicates = contrats_clean.sample(n=n_dup, random_state=seed).copy()
    raw_contracts = pd.concat([contrats_clean, duplicates], ignore_index=True)
    n_bad_date = max(1, round(n_contracts * 0.01))
    bad_date_idx = rng.choice(contrats_clean.index.to_numpy(), size=n_bad_date, replace=False)
    for idx in bad_date_idx:
        bad_start = date.fromisoformat(contrats_clean.loc[idx, "date_debut"])
        raw_contracts.loc[idx, "date_fin_prevue"] = iso(bad_start - timedelta(days=1))

    n_neg_contract = max(1, round(n_contracts * 0.01))
    neg_contract_idx = rng.choice(np.setdiff1d(contrats_clean.index.to_numpy(), bad_date_idx), size=n_neg_contract, replace=False)
    raw_contracts.loc[neg_contract_idx, "montant_finance"] = -raw_contracts.loc[neg_contract_idx, "montant_finance"].abs()

    raw_dues = echeances_clean.copy()
    n_orphan = max(1, round(len(raw_dues) * 0.01))
    orphan_idx = rng.choice(raw_dues.index.to_numpy(), size=n_orphan, replace=False)
    orphans = raw_dues.loc[orphan_idx].copy()
    orphans["echeance_id"] = [f"ECH-ORP-{i:05d}" for i in range(1, n_orphan + 1)]
    orphans["contrat_id"] = [f"CTR-ORP-{i:05d}" for i in range(1, n_orphan + 1)]
    raw_dues = pd.concat([raw_dues, orphans], ignore_index=True)
    n_neg_due = max(1, round(len(raw_dues) * 0.005))
    neg_due_idx = rng.choice(raw_dues.index.to_numpy(), size=n_neg_due, replace=False)
    raw_dues.loc[neg_due_idx, "montant_du"] = -raw_dues.loc[neg_due_idx, "montant_du"].abs()

    raw_payments = paiements_clean.copy()
    eligible = raw_payments.merge(raw_dues[["echeance_id", "montant_du"]], on="echeance_id", how="inner")
    # At most one payment per installment is produced initially; corrupt only a sampled subset.
    n_overpay = max(1, round(len(raw_payments) * 0.01))
    overpay_ids = rng.choice(raw_payments.index.to_numpy(), size=min(n_overpay, len(raw_payments)), replace=False)
    due_lookup = echeances_clean.set_index("echeance_id")["montant_du"]
    for idx in overpay_ids:
        eid = raw_payments.loc[idx, "echeance_id"]
        raw_payments.loc[idx, "montant_paye"] = round(float(due_lookup[eid]) * 1.25, 2)

    out.mkdir(parents=True, exist_ok=True)
    tables = {
        "clients": clients,
        "biens": biens,
        "contrats": raw_contracts,
        "echeances": raw_dues,
        "paiements": raw_payments,
    }
    for name, frame in tables.items():
        frame.to_csv(out / f"{name}.csv", index=False, encoding="utf-8")

    expected = pd.DataFrame([
        {"controle": "contrats_doublons", "anomalies_injectees": n_dup,
         "description": "Copies supplémentaires de contrats existants."},
        {"controle": "contrats_dates_incoherentes", "anomalies_injectees": n_bad_date,
         "description": "Date de fin prévue antérieure à la date de début."},
        {"controle": "contrats_montants_negatifs", "anomalies_injectees": n_neg_contract,
         "description": "Montant financé négatif."},
        {"controle": "echeances_orphelines", "anomalies_injectees": n_orphan,
         "description": "Échéances rattachées à un identifiant de contrat absent."},
        {"controle": "echeances_montants_negatifs", "anomalies_injectees": n_neg_due,
         "description": "Montant dû négatif."},
        {"controle": "paiements_superieurs_au_du", "anomalies_injectees": len(overpay_ids),
         "description": "Paiement supérieur au montant dû de l’échéance."},
    ])
    expected.to_csv(out / "expected_anomalies.csv", index=False, encoding="utf-8")
    manifest = {
        "synthetic": True,
        "seed": seed,
        "reference_date": iso(REFERENCE_DATE),
        "history_start_month": START_MONTH,
        "history_end_month": END_MONTH,
        "contracts_generated": n_contracts,
        "note": "Toutes les identités, entreprises et transactions sont fictives; les anomalies sont injectées intentionnellement.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return tables


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--contracts", type=int, default=2000)
    args = parser.parse_args()
    tables = make_data(args.out, args.seed, args.contracts)
    print("Données SYNTHÉTIQUES générées (aucune donnée client réelle).")
    for name, frame in tables.items():
        print(f"{name}: {len(frame):,} lignes, {len(frame.columns)} colonnes")
    print(f"Référence métier : {REFERENCE_DATE.isoformat()} ; période : {START_MONTH} à {END_MONTH}")


if __name__ == "__main__":
    main()

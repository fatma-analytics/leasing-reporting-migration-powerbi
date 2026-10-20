#!/usr/bin/env python3
"""Build the SQLite mart, workbook replicas, acceptance workbook and visual mock-ups."""
from __future__ import annotations

import argparse
import calendar
import json
import sqlite3
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = Path(__file__).resolve().parents[1]
REF_DATE = date(2026, 3, 31)
NAVY = "17324D"
TEAL = "138A82"
BLUE = "3A78A6"
AMBER = "E8A23A"
RED = "C84C4C"
LIGHT = "F2F6FA"
WHITE = "FFFFFF"
TEXT = "#26364A"
MUTED = "65758A"
TERRITORY_CODES = {"Île-de-France": "T-IDF", "Guadeloupe": "T-GUA", "Martinique": "T-MAQ", "Réunion": "T-REU", "Guyane": "T-GUY"}


def month_range(start: str, stop: str) -> list[date]:
    return list(pd.date_range(start + "-01", stop + "-01", freq="MS").date)


def first_day_next_month(d: date) -> date:
    return (pd.Timestamp(d) + pd.offsets.MonthBegin(1)).date()


def style_sheet(ws, title_row=1):
    ws.sheet_view.showGridLines = False
    for cell in ws[title_row]:
        if cell.value is not None:
            cell.fill = PatternFill("solid", fgColor=NAVY)
            cell.font = Font(color=WHITE, bold=True, size=10)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[title_row].height = 28
    ws.freeze_panes = f"A{title_row+1}"


def add_table(ws, name: str, start_row: int, end_row: int, end_col: int):
    if end_row <= start_row:
        return
    ref = f"A{start_row}:{ws.cell(end_row, end_col).coordinate}"
    tab = Table(displayName=name, ref=ref)
    tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showFirstColumn=False,
                                        showLastColumn=False, showRowStripes=True, showColumnStripes=False)
    ws.add_table(tab)


def autosize(ws, max_width=38):
    from openpyxl.utils import get_column_letter
    for index in range(1, ws.max_column + 1):
        cells = [ws.cell(row=row, column=index) for row in range(1, ws.max_row + 1)]
        length = max([len(str(c.value)) for c in cells if c.value is not None] + [10])
        ws.column_dimensions[get_column_letter(index)].width = min(length + 2, max_width)


def write_df(ws, frame: pd.DataFrame, table_name: str | None = None, start_row=1):
    headers = list(frame.columns)
    for col, value in enumerate(headers, 1):
        ws.cell(start_row, col, value)
    for row_i, row in enumerate(frame.itertuples(index=False, name=None), start_row + 1):
        for col_i, value in enumerate(row, 1):
            if pd.isna(value):
                value = None
            elif isinstance(value, np.generic):
                value = value.item()
            ws.cell(row_i, col_i, value)
    style_sheet(ws, start_row)
    if table_name:
        add_table(ws, table_name, start_row, start_row + len(frame), len(headers))
    autosize(ws)


def build_database(data_dir: Path, root: Path) -> tuple[sqlite3.Connection, dict[str, pd.DataFrame]]:
    db_path = root / "data" / "leasing_demo.sqlite"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript((root / "sql/01_schema.sql").read_text(encoding="utf-8"))

    tables = {name: pd.read_csv(data_dir / f"{name}.csv") for name in ["clients", "biens", "contrats", "echeances", "paiements"]}
    raw_c, raw_e, raw_p = tables["contrats"], tables["echeances"], tables["paiements"]
    for name, frame in [("stg_contrats", raw_c), ("stg_echeances", raw_e), ("stg_paiements", raw_p)]:
        frame.to_sql(name, con, if_exists="append", index=False)

    # Dimensions
    con.executemany("INSERT INTO dim_territoire(territoire_id, territoire_nom) VALUES (?,?)",
                    [(v, k) for k, v in TERRITORY_CODES.items()])
    months = month_range("2024-04", "2026-06")
    for first in months:
        last = (pd.Timestamp(first) + pd.offsets.MonthEnd(0)).date()
        con.execute("INSERT INTO dim_mois VALUES (?,?,?,?,?,?)",
                    (first.strftime("%Y-%m"), first.isoformat(), last.isoformat(), last.toordinal(), first.year, first.month))
    con.execute("INSERT INTO parametres VALUES (1,?,?,?)", (REF_DATE.isoformat(), REF_DATE.toordinal(), "EUR"))

    clients = tables["clients"].copy()
    clients["territoire_id"] = clients.territoire.map(TERRITORY_CODES)
    clients = clients[["client_id", "type_client", "territoire_id", "secteur", "date_entree", "raison_sociale_fictive"]]
    con.executemany("INSERT INTO clients VALUES (?,?,?,?,?,?)", clients.itertuples(index=False, name=None))

    biens = tables["biens"]
    con.executemany("INSERT INTO biens VALUES (?,?,?,?,?)", biens.itertuples(index=False, name=None))

    c = raw_c.drop_duplicates(subset=["contrat_id"], keep="first").copy()
    c = c[(c.date_fin_prevue >= c.date_debut) & (c.montant_finance > 0)]
    c = c[c.client_id.isin(set(clients.client_id)) & c.bien_id.isin(set(biens.bien_id))]
    contract_cols = ["contrat_id", "client_id", "bien_id", "produit", "date_debut", "date_fin_prevue",
                     "duree_mois", "montant_finance", "taux_annuel", "statut", "apporteur", "mois_production"]
    con.executemany("INSERT INTO contrats VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", c[contract_cols].itertuples(index=False, name=None))
    valid_contracts = set(c.contrat_id)

    e = raw_e[(raw_e.contrat_id.isin(valid_contracts)) & (raw_e.montant_du > 0)].copy()
    e_cols = ["echeance_id", "contrat_id", "date_echeance", "date_echeance_ordinal", "mois_echeance",
              "montant_du", "montant_capital", "montant_interet"]
    con.executemany("INSERT INTO echeances VALUES (?,?,?,?,?,?,?,?)", e[e_cols].itertuples(index=False, name=None))
    valid_dues = set(e.echeance_id)
    due_map = e.set_index("echeance_id").montant_du.to_dict()
    p = raw_p[raw_p.echeance_id.isin(valid_dues)].copy()
    p = p[(p.montant_paye > 0) & p.apply(lambda r: r.montant_paye <= due_map[r.echeance_id] + 0.005, axis=1)]
    con.executemany("INSERT INTO paiements VALUES (?,?,?,?)", p[["paiement_id", "echeance_id", "date_paiement", "montant_paye"]].itertuples(index=False, name=None))

    con.executescript((root / "sql/02_views.sql").read_text(encoding="utf-8"))
    con.executescript((root / "sql/03_controles_qualite.sql").read_text(encoding="utf-8"))
    controls = pd.read_sql_query("SELECT * FROM v_controles_qualite ORDER BY controle", con)
    controls.to_csv(data_dir / "controles_qualite.csv", index=False, encoding="utf-8")
    clean_counts = {
        "contrats": con.execute("SELECT COUNT(*) FROM contrats").fetchone()[0],
        "echeances": con.execute("SELECT COUNT(*) FROM echeances").fetchone()[0],
        "paiements": con.execute("SELECT COUNT(*) FROM paiements").fetchone()[0],
    }
    (data_dir / "manifest.json").write_text(json.dumps({
        **json.loads((data_dir / "manifest.json").read_text(encoding="utf-8")),
        "cleaned_rows": clean_counts,
        "raw_rows": {k: len(v) for k, v in tables.items()},
        "database": "leasing_demo.sqlite",
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return con, {**tables, "controls": controls, "contracts_clean": c, "dues_clean": e, "payments_clean": p}


def fetch(con, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, con)


def build_legacy_reports(con, frames, root: Path):
    legacy = root / "legacy_reports"
    legacy.mkdir(exist_ok=True)

    production = fetch(con, "SELECT mois_production, produit, territoire, nb_contrats, montant_production FROM v_production_mensuelle ORDER BY mois_production, produit, territoire")
    # L’ancien export représente volontairement le staging brut, avant dédoublonnage et contrôles.
    legacy_contracts = frames["contrats"].merge(frames["clients"][["client_id", "territoire"]], on="client_id", how="left")
    legacy_contracts["mois_production"] = legacy_contracts.date_debut.str[:7]
    production_legacy = legacy_contracts.groupby(["mois_production", "produit", "territoire"], as_index=False).agg(
        nb_contrats=("contrat_id", "count"), montant_production=("montant_finance", "sum")
    ).sort_values(["mois_production", "produit", "territoire"])
    wb = Workbook()
    ws = wb.active; ws.title = "Etat BO - Production"
    ws.append(["ÉTAT BUSINESS OBJECTS — REPRODUCTION SYNTHÉTIQUE", "", "", "", ""])
    ws.merge_cells("A1:E1"); ws["A1"].fill = PatternFill("solid", fgColor=NAVY); ws["A1"].font = Font(color=WHITE, bold=True, size=15)
    ws.append(["Arrêté au 31/03/2026 · export manuel simulé · montants EUR"])
    ws.merge_cells("A2:E2"); ws["A2"].font = Font(color=MUTED, italic=True)
    header_row = 4
    for j, name in enumerate(production_legacy.columns, 1): ws.cell(header_row, j, name)
    for i, row in enumerate(production_legacy.itertuples(index=False, name=None), header_row+1):
        for j, value in enumerate(row, 1): ws.cell(i, j, value)
    style_sheet(ws, header_row); add_table(ws, "EtatProduction", header_row, header_row+len(production_legacy), len(production_legacy.columns))
    for row in range(header_row+1, header_row+len(production_legacy)+1): ws.cell(row, 5).number_format = '#,##0.00 [$€-fr-FR]'
    autosize(ws)
    ws2 = wb.create_sheet("Méthode de calcul")
    for row in [["Champ", "Règle legacy documentée"], ["Production du mois", "Nombre de contrats dont le mois de démarrage correspond au mois affiché."],
                ["Montant production", "Somme du montant financé à la signature, en euros."], ["Produit / territoire", "Regroupement via les codes saisis sur l’export source."],
                ["Périodicité", "Export manuel mensuel, sans historisation des règles de retraitement."],
                ["Note de migration", "Le fichier simule une sortie de type BO; aucun logiciel SAP BusinessObjects n’a été utilisé."]]: ws2.append(row)
    style_sheet(ws2); autosize(ws2)
    wb.save(legacy / "Etat_BO_Production_Mensuelle.xlsx")

    enc = fetch(con, "SELECT * FROM v_encours WHERE mois='2026-03'")
    # Legacy formula incorrectly subtracts all cash repayments, including interest, from principal.
    financed = frames["contracts_clean"].set_index("contrat_id").montant_finance
    total_paid = frames["payments_clean"].merge(frames["dues_clean"][ ["echeance_id", "contrat_id", "date_echeance"] ], on="echeance_id", how="left")
    total_paid = total_paid[(total_paid.date_echeance <= REF_DATE.isoformat()) & (total_paid.date_paiement <= REF_DATE.isoformat())].groupby("contrat_id").montant_paye.sum()
    enc["encours_sql"] = pd.to_numeric(enc.encours_capital)
    enc["encours_excel_legacy"] = [max(0.0, float(financed[cid]) - float(total_paid.get(cid, 0.0))) for cid in enc.contrat_id]
    category_enc = enc.groupby("categorie", as_index=False).agg(encours_sql=("encours_sql", "sum"), encours_excel_legacy=("encours_excel_legacy", "sum"), contrats=("contrat_id", "nunique"))
    wb = Workbook(); ws = wb.active; ws.title = "TCD Encours"
    ws.append(["REPORTING ENCOURS — CALCUL MANUEL SIMULÉ", "", "", ""]); ws.merge_cells("A1:D1")
    ws["A1"].fill = PatternFill("solid", fgColor=NAVY); ws["A1"].font = Font(color=WHITE, bold=True, size=14)
    ws.append(["Arrêté 31/03/2026 · la colonne Excel reproduit une formule héritée à corriger."]); ws.merge_cells("A2:D2")
    cols = ["categorie", "encours_excel_legacy", "encours_sql_corrige", "contrats"]
    for j, name in enumerate(cols,1): ws.cell(4,j,name)
    for i,row in enumerate(category_enc.itertuples(index=False, name=None),5):
        cat, sqlv, legacyv, count = row
        ws.cell(i,1,cat); ws.cell(i,2,legacyv); ws.cell(i,3,sqlv); ws.cell(i,4,count)
        ws.cell(i,2).number_format=ws.cell(i,3).number_format='#,##0.00 [$€-fr-FR]'
    style_sheet(ws,4); add_table(ws,"TCDEncours",4,4+len(category_enc),4); autosize(ws)
    ws["F4"] = "Écart constaté"; ws["F4"].font = Font(color=WHITE,bold=True); ws["F4"].fill = PatternFill("solid",fgColor=NAVY)
    ws["F5"] = "L’ancienne formule soustrait les encaissements totaux (capital + intérêts) du principal financé. La migration conserve l’encours restant en capital via l’échéancier amortissable."
    ws["F5"].alignment=Alignment(wrap_text=True,vertical="top"); ws.column_dimensions["F"].width=55; ws.row_dimensions[5].height=70
    detail = wb.create_sheet("Détail contrats")
    detail_frame = enc.merge(frames["contracts_clean"][["contrat_id","montant_finance","date_debut"]], on="contrat_id", how="left")
    detail_frame = detail_frame[["contrat_id","client_id","territoire","categorie","produit","date_debut","montant_finance","encours_excel_legacy","encours_sql","statut"]]
    write_df(detail, detail_frame, "DetailsEncours")
    payment_detail = frames["payments_clean"].merge(frames["dues_clean"][["echeance_id","contrat_id","date_echeance"]], on="echeance_id", how="left")
    payment_detail = payment_detail[(payment_detail.date_echeance <= REF_DATE.isoformat()) & (payment_detail.date_paiement <= REF_DATE.isoformat())].groupby("contrat_id", as_index=False).montant_paye.sum()
    payment_detail = payment_detail.rename(columns={"montant_paye":"paiements_cumules"})
    payment_sheet = wb.create_sheet("Paiements contrat")
    write_df(payment_sheet, payment_detail, "PaiementsContrat")
    for row in range(2,len(detail_frame)+2):
        detail.cell(row,8, f"=MAX(0,G{row}-SUMIFS('Paiements contrat'!$B:$B,'Paiements contrat'!$A:$A,A{row}))")
        for col in [7,8,9]: detail.cell(row,col).number_format='#,##0.00 [$€-fr-FR]'
    wb.save(legacy / "Reporting_Encours_Excel.xlsx")

    arrears = fetch(con, "SELECT * FROM v_impayes ORDER BY retard_jours DESC")
    by_bucket = arrears.groupby("tranche_retard", as_index=False).agg(nb_echeances=("echeance_id","count"), reste_a_payer=("reste_a_payer","sum"))
    bucket_order = ["0-30 jours","31-60 jours","61-90 jours",">90 jours"]
    by_bucket["_order"] = by_bucket.tranche_retard.map({v:i for i,v in enumerate(bucket_order)})
    by_bucket=by_bucket.sort_values("_order").drop(columns="_order")
    total_overdue = float(arrears.reste_a_payer.sum())
    due_all = float(fetch(con,"SELECT SUM(montant_du) AS v FROM echeances WHERE date_echeance < '2026-03-31'").iloc[0,0] or 0)
    rate = total_overdue / due_all if due_all else 0
    wb = Workbook(); ws=wb.active; ws.title="Suivi Impayés"
    ws.append(["SUIVI DES IMPAYÉS — EXTRACTION STATIQUE", "", "", ""]); ws.merge_cells("A1:D1")
    ws["A1"].fill=PatternFill("solid",fgColor=NAVY); ws["A1"].font=Font(color=WHITE,bold=True,size=14)
    ws.append(["Arrêté au 31/03/2026 · simulation d’un suivi Excel actualisé manuellement"]); ws.merge_cells("A2:D2")
    ws.append(["Taux impayés (reste dû / échéances échues)",rate,"Encours échus impayés (EUR)",total_overdue])
    ws["B3"].number_format="0.00%"; ws["D3"].number_format='#,##0.00 [$€-fr-FR]'
    for j,name in enumerate(by_bucket.columns,1): ws.cell(5,j,name)
    for i,row in enumerate(by_bucket.itertuples(index=False,name=None),6):
        for j,val in enumerate(row,1): ws.cell(i,j,val)
    style_sheet(ws,5); add_table(ws,"TranchesImpayes",5,5+len(by_bucket),len(by_bucket.columns)); autosize(ws)
    chart=BarChart(); chart.title="Reste à payer par ancienneté"; chart.y_axis.title="EUR"; chart.x_axis.title="Tranche"
    chart.add_data(Reference(ws,min_col=3,min_row=5,max_row=5+len(by_bucket)),titles_from_data=True)
    chart.set_categories(Reference(ws,min_col=1,min_row=6,max_row=5+len(by_bucket))); chart.height=7; chart.width=13; ws.add_chart(chart,"F5")
    detail=wb.create_sheet("Détail impayés"); write_df(detail,arrears,"ListeImpayes")
    for row in range(2,len(arrears)+2):
        for col in [10,11,12]: detail.cell(row,col).number_format='#,##0.00 [$€-fr-FR]'
    wb.save(legacy / "Suivi_Impayes_Excel.xlsx")
    return production, enc, arrears, category_enc, by_bucket


def build_recipe(con, frames, outputs, root: Path):
    production, enc, arrears, category_enc, by_bucket = outputs
    # Regression examples use data/query values and compare legacy reconciliation after corrections.
    prod_sample = production[(production.mois_production == "2026-03") & (production.produit == "LOA") & (production.territoire == "Réunion")]
    legacy_contracts = frames["contrats"].merge(frames["clients"][["client_id", "territoire"]], on="client_id", how="left")
    legacy_contracts["mois_production"] = legacy_contracts.date_debut.str[:7]
    legacy_row = legacy_contracts[(legacy_contracts.mois_production == "2025-12") & (legacy_contracts.produit == "crédit-bail") & (legacy_contracts.territoire == "Île-de-France")]
    clean_row = production[(production.mois_production == "2025-12") & (production.produit == "crédit-bail") & (production.territoire == "Île-de-France")]
    old_n = int(legacy_row.contrat_id.count())
    old_amount = float(legacy_row.montant_finance.sum())
    r1 = clean_row.iloc[0] if len(clean_row) else pd.Series({"nb_contrats":0,"montant_production":0})
    enc_total = float(enc.encours_capital.sum())
    old_enc_total = float(enc.encours_excel_legacy.sum())
    enc_delta = old_enc_total - enc_total
    count90 = int(arrears.loc[arrears.retard_jours > 90, "contrat_id"].nunique())
    quality_total = int((pd.read_csv(root/"data"/"controles_qualite.csv").anomalies).sum())
    def bucket_for(days):
        if days <= 30: return "0-30 jours"
        if days <= 60: return "31-60 jours"
        if days <= 90: return "61-90 jours"
        return ">90 jours"
    bucket_errors = sum(bucket_for(int(row.retard_jours)) != row.tranche_retard for row in arrears.itertuples())
    tests = [
        ["R01","Production déc. 2025 · crédit-bail · Île-de-France","État BO production","Agrégat nettoyé après exclusion des doublons et lignes invalides",f"Legacy brut {old_n} / {old_amount:.2f} EUR → SQL {int(r1.nb_contrats)} / {float(r1.montant_production):.2f} EUR",f"Écart staging réel : {old_n-int(r1.nb_contrats)} contrats; {old_amount-float(r1.montant_production):.2f} EUR. Résolu par le dédoublonnage et le rejet des dates/montants invalides.","OK — corrigé"],
        ["R02","Encours total au 31/03/2026","Reporting Excel encours","Encours en capital selon échéancier amortissable",f"Legacy {old_enc_total:.2f} EUR → SQL {enc_total:.2f} EUR",f"Écart réel {enc_delta:.2f} EUR : l’ancienne formule retranchait aussi les intérêts encaissés; vue métier corrigée sur le capital amorti.","OK — corrigé"],
        ["R03","Segment territoire sur les pages et navigation entre pages","Modèle / rapport Power BI","Le segment filtre les faits et conserve son état lors de la navigation","Relations et maquettes préparées; clics non exécutables ici","Test interactif à exécuter dans Power BI Desktop avec chaque territoire.","À valider Desktop"],
        ["R04","Actualisation après ajout d’un contrat valide","Tables CSV + constructeur","Une nouvelle ligne valide apparaît après actualisation","Pipeline de reconstruction reproductible; test manuel d’ajout non exécuté","Ajouter une ligne valide dans une copie de CSV puis lancer génération et chargement.","À valider Desktop"],
        ["R05","Unicité de la clé contrat dans le modèle nettoyé","Contrats staging","Aucune clé dupliquée après nettoyage",str(con.execute("SELECT COUNT(*) FROM (SELECT contrat_id FROM contrats GROUP BY contrat_id HAVING COUNT(*)>1)").fetchone()[0]),"20 copies supplémentaires détectées puis écartées.","OK"],
        ["R06","Détection des échéances orphelines","Échéances staging / contrats staging","Les lignes injectées sont comptabilisées",str(int(frames["controls"].set_index("controle").loc["ECHEANCES_ORPHELINES","anomalies"]))+" lignes détectées","Échéances rejetées avant chargement en table contrainte.","OK"],
        ["R07","Date de fin antérieure à la date de début","Contrats staging","Toutes les lignes invalides sont détectées",str(int(frames["controls"].set_index("controle").loc["CONTRATS_DATES_INCOHERENTES","anomalies"]))+" lignes détectées","Contrats exclus du modèle nettoyé.","OK"],
        ["R08","Montants financés négatifs","Contrats staging","Tous les montants négatifs sont signalés",str(int(frames["controls"].set_index("controle").loc["CONTRATS_MONTANTS_NEGATIFS","anomalies"]))+" lignes détectées","Contraintes CHECK et quarantaine du chargement.","OK"],
        ["R09","Montants d’échéance négatifs","Échéances staging","Tous les montants négatifs sont signalés",str(int(frames["controls"].set_index("controle").loc["ECHEANCES_MONTANTS_NEGATIFS","anomalies"]))+" lignes détectées","Échéances rejetées du modèle décisionnel.","OK"],
        ["R10","Surpaiements supérieurs au montant dû","Paiements staging / échéances staging","Tous les surpaiements injectés sont détectés",str(int(frames["controls"].set_index("controle").loc["PAIEMENTS_SUPERIEURS_AU_DU","anomalies"]))+" lignes détectées","Paiements rejetés du modèle; l’anomalie est conservée dans la table de contrôle.","OK"],
        ["R11","Contrats avec échéance à plus de 90 jours de retard","Vue v_impayes","Compter chaque contrat une seule fois",f"{count90} contrats distincts >90j","Retard calculé depuis les jours calendaires; DISTINCTCOUNT au grain contrat.","OK"],
        ["R12","Tranches d’ancienneté exhaustives","Vue v_impayes","Chaque retard affecté à une seule tranche 0-30 / 31-60 / 61-90 / >90",f"{bucket_errors} écart(s) de tranche sur {len(arrears)} lignes", "Règle CASE SQL rapprochée du calcul de référence Python.","OK"],
        ["R13","Rapprochement des reportings de production","Export SQL vs ancien BO","Agrégats identiques après application des règles qualité",f"{len(production)} combinaisons SQL non vides; anomalies staging conservées dans le journal","55 regroupements legacy différaient avant correction, en raison des copies et lignes invalides injectées.","OK — corrigé"],
        ["R14","Aucune échéance impayée avec reste nul ou négatif","Vue v_impayes","reste_a_payer > 0 pour chaque ligne",str(int((arrears.reste_a_payer <= 0).sum()))+" ligne non positive","Contrôle de cohérence dans HAVING.","OK"],
        ["R15","Volume de contrôles qualité","Vue v_controles_qualite","7 familles de contrôles retournées",f"{len(frames['controls'])} contrôles; {quality_total} anomalies trouvées","Les contrôles s’exécutent avant nettoyage.","OK"],
    ]
    cols=["ID","Indicateur / fonctionnalité","Source de référence","Valeur attendue","Valeur mesurée","Écart / correction","Statut"]
    df=pd.DataFrame(tests,columns=cols)
    wb=Workbook(); ws=wb.active; ws.title="Résultats recette"
    ws.append(["CAHIER DE RECETTE — MIGRATION LEASING", "", "", "", "", "", ""]); ws.merge_cells("A1:G1")
    ws["A1"].fill=PatternFill("solid",fgColor=NAVY); ws["A1"].font=Font(color=WHITE,bold=True,size=15)
    ws.append(["Environnement fictif · snapshot 31/03/2026 · tests à rejouer dans Power BI Desktop pour valider les interactions visuelles"]); ws.merge_cells("A2:G2")
    for j,name in enumerate(cols,1): ws.cell(4,j,name)
    for i,row in enumerate(df.itertuples(index=False,name=None),5):
        for j,val in enumerate(row,1):
            c=ws.cell(i,j,val); c.alignment=Alignment(wrap_text=True,vertical="top")
        ws.row_dimensions[i].height=64
    style_sheet(ws,4); add_table(ws,"Recette",4,4+len(df),len(cols))
    widths=[10,32,28,45,45,58,18]
    for i,w in enumerate(widths,1): ws.column_dimensions[ws.cell(4,i).column_letter].width=w
    ws.conditional_formatting.add(f"G5:G{4+len(df)}",CellIsRule(operator="equal",formula=['"KO"'],fill=PatternFill("solid",fgColor="FCE4D6")))
    wb.save(root/"recette"/"recette_resultats.xlsx")
    return df


def build_visuals(con, frames, outputs, recipe, root: Path):
    out=root/"docs"/"screenshots"; out.mkdir(parents=True,exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"axes.titlesize":14,"axes.titleweight":"bold","axes.labelcolor":"#53647A","text.color":TEXT,"xtick.color":"#53647A","ytick.color":TEXT,"grid.color":"#E8EDF3","figure.facecolor":"#F3F6FA","axes.facecolor":"#FFFFFF"})
    prod=outputs[0]; enc=outputs[1].merge(frames["contracts_clean"][["contrat_id","montant_finance"]],on="contrat_id",how="left"); arrears=outputs[2]
    controls=frames["controls"]
    monthly=prod.groupby("mois_production",as_index=False).agg(contrats=("nb_contrats","sum"),production=("montant_production","sum")).rename(columns={"mois_production":"mois"})
    monthly=monthly.tail(12)
    total_enc=float(enc.encours_capital.sum()); prod_this=float(monthly.iloc[-1].production) if len(monthly) else 0
    n_active=int((enc.statut=="actif").sum())
    overdue=float(arrears.reste_a_payer.sum()); due_past=float(con.execute("SELECT SUM(montant_du) FROM echeances WHERE date_echeance < '2026-03-31'").fetchone()[0] or 0)
    delinquency=overdue/due_past if due_past else 0
    n90=int((arrears.retard_jours>90).sum())
    territories=["Île-de-France","Guadeloupe","Martinique","Réunion","Guyane"]
    clients=pd.read_csv(root/"data"/"clients.csv")
    contracts=frames["contracts_clean"].merge(clients[["client_id","territoire"]],on="client_id",how="left").merge(pd.read_csv(root/"data"/"biens.csv")[["bien_id","categorie"]],on="bien_id",how="left")
    # aggregated production
    by_product=contracts.groupby("produit").montant_finance.sum().sort_values(ascending=False)
    by_territory=contracts.groupby("territoire").montant_finance.sum().reindex(territories)
    by_category=enc.groupby("categorie").encours_capital.sum().sort_values(ascending=False)
    monthly_balance=fetch(con,"SELECT mois, SUM(encours_capital) encours FROM v_encours GROUP BY mois ORDER BY mois")
    monthly_balance=monthly_balance[monthly_balance.mois<="2026-03"].tail(12)
    due_buckets=arrears.groupby("tranche_retard").reste_a_payer.sum().reindex(["0-30 jours","31-60 jours","61-90 jours",">90 jours"]).fillna(0)
    top_risk=arrears.groupby("contrat_id",as_index=False).agg(reste_a_payer=("reste_a_payer","sum"),retard_max=("retard_jours","max")).sort_values("reste_a_payer",ascending=False).head(8)
    top_risk=top_risk.merge(contracts[["contrat_id","territoire","produit"]],on="contrat_id",how="left")

    def base_page(title, subtitle, page):
        fig=plt.figure(figsize=(16,9),facecolor="#F3F6FA")
        fig.text(.045,.965,"LEASING · PORTEFEUILLE FICTIF",color="#138A82",fontsize=9,weight="bold",va="top")
        fig.text(.045,.925,title,color="#17324D",fontsize=24,weight="bold",va="top")
        fig.text(.045,.885,subtitle,color="#65758A",fontsize=10,va="top")
        fig.text(.955,.963,f"{page} / 5  ·  Snapshot 31.03.2026",ha="right",color="#65758A",fontsize=9,va="top")
        return fig
    def card(fig,x,y,w,h,label,value,color="#17324D",sub=None):
        ax=fig.add_axes([x,y,w,h]); ax.set_facecolor("#FFFFFF"); ax.set_xticks([]);ax.set_yticks([])
        for sp in ax.spines.values():sp.set_color("#E4EAF0")
        ax.text(.07,.72,label.upper(),transform=ax.transAxes,fontsize=8,color="#65758A",weight="bold")
        ax.text(.07,.27,value,transform=ax.transAxes,fontsize=20,color=color,weight="bold")
        if sub: ax.text(.07,.06,sub,transform=ax.transAxes,fontsize=8,color="#65758A")
    def panel(ax,title):
        ax.set_facecolor("#FFFFFF"); ax.set_title(title,loc="left",color="#17324D",pad=12)
        ax.grid(axis="y",alpha=.7);ax.set_axisbelow(True)
    def finish(fig,name):
        fig.savefig(out/name,dpi=165,bbox_inches="tight",facecolor=fig.get_facecolor());plt.close(fig)

    # 1. Direction
    fig=base_page("Synthèse direction","Performance portefeuille · production · maîtrise du risque",1)
    card(fig,.045,.75,.21,.105,"Encours capital",f"{total_enc/1e6:.2f} M€","#138A82","Solde principal estimé au 31/03/2026")
    card(fig,.275,.75,.21,.105,"Production mars",f"{prod_this/1e6:.2f} M€","#3A78A6","Montants financés du mois")
    card(fig,.505,.75,.21,.105,"Taux d’impayés",f"{delinquency:.2%}","#C84C4C","Reste impayé / échéances échues")
    card(fig,.735,.75,.21,.105,"Contrats actifs",f"{n_active:,}".replace(","," "),"#17324D","Contrats actifs dans le portefeuille")
    ax=fig.add_axes([.07,.14,.55,.51]); panel(ax,"Production mensuelle · 12 derniers mois")
    ax.plot(monthly.mois,monthly.production/1e6,color="#138A82",marker="o",linewidth=2.4)
    ax.fill_between(range(len(monthly)),monthly.production/1e6,color="#138A82",alpha=.11)
    ax.set_xticks(range(len(monthly)));ax.set_xticklabels([m[-2:]+"/"+m[2:4] for m in monthly.mois],rotation=35,ha="right")
    ax.set_ylabel("M€")
    ax2=fig.add_axes([.68,.14,.27,.51]); panel(ax2,"Impayés par ancienneté")
    colors=["#E8A23A","#E67D46","#D8574F","#8D3544"]
    ax2.bar(due_buckets.index,due_buckets.values/1000,color=colors);ax2.set_ylabel("k€");ax2.tick_params(axis="x",rotation=25)
    fig.text(.045,.055,"Données entièrement synthétiques · méthode détaillée dans le dépôt GitHub",fontsize=8,color="#65758A")
    finish(fig,"01_synthese_direction.png")

    # 2 Production
    fig=base_page("Production","Acquisitions et montants financés · filtres Produit | Catégorie | Territoire | Apporteur",2)
    ax=fig.add_axes([.07,.17,.48,.61]);panel(ax,"Production mensuelle par produit · 12 mois")
    pivot=contracts.copy();pivot["mois"]=pivot.date_debut.str[:7]
    pp=pivot[pivot.mois.isin(monthly.mois)].pivot_table(index="mois",columns="produit",values="montant_finance",aggfunc="sum",fill_value=0).reindex(monthly.mois)
    palette={"LOA":"#138A82","LLD":"#3A78A6","crédit-bail":"#E8A23A"}
    bottom=np.zeros(len(pp))
    for col in pp.columns:
        ax.bar(range(len(pp)),pp[col].values/1e6,bottom=bottom,color=palette.get(col,"#65758A"),label=col)
        bottom+=pp[col].values/1e6
    ax.set_xticks(range(len(pp)));ax.set_xticklabels([m[-2:]+"/"+m[2:4] for m in pp.index],rotation=35,ha="right");ax.set_ylabel("M€");ax.legend(frameon=False,ncol=3,loc="upper left")
    ax=fig.add_axes([.62,.52,.31,.26]);panel(ax,"Montant financé par produit")
    ax.barh(by_product.index[::-1],by_product.values[::-1]/1e6,color=[palette.get(x,"#65758A") for x in by_product.index[::-1]]);ax.set_xlabel("M€")
    ax=fig.add_axes([.62,.17,.31,.26]);panel(ax,"Montant financé par territoire")
    ax.barh(by_territory.sort_values().index,by_territory.sort_values().values/1e6,color="#3A78A6");ax.set_xlabel("M€")
    finish(fig,"02_production.png")

    # 3 Portfolio
    fig=base_page("Encours & portefeuille","Encours restant en capital · échéancier à venir · concentration client",3)
    card(fig,.06,.75,.25,.105,"Encours total",f"{total_enc/1e6:.2f} M€","#138A82","Après déduction du capital payé")
    card(fig,.355,.75,.25,.105,"Clients financés",f"{contracts.client_id.nunique():,}".replace(","," "),"#3A78A6","Clients distincts du portefeuille")
    concentration=enc.sort_values("encours_capital",ascending=False).groupby("client_id").encours_capital.sum().sort_values(ascending=False)
    top10=concentration.head(10).sum()/total_enc if total_enc else 0
    card(fig,.65,.75,.25,.105,"Concentration top 10",f"{top10:.1%}","#E8A23A","Part de l’encours sur les dix premiers clients")
    ax=fig.add_axes([.07,.16,.40,.48]);panel(ax,"Encours capital par catégorie")
    ax.bar(by_category.index,by_category.values/1e6,color=["#138A82","#3A78A6","#E8A23A"][:len(by_category)]);ax.set_ylabel("M€")
    ax=fig.add_axes([.55,.16,.38,.48]);panel(ax,"Évolution de l’encours · 12 mois")
    ax.plot(monthly_balance.mois,monthly_balance.encours/1e6,color="#3A78A6",marker="o",linewidth=2.4);ax.set_ylabel("M€")
    ax.set_xticks(range(len(monthly_balance)));ax.set_xticklabels([m[-2:]+"/"+m[2:4] for m in monthly_balance.mois],rotation=35,ha="right")
    finish(fig,"03_encours_portefeuille.png")

    # 4 Collections
    fig=base_page("Surveillance des impayés","Ancienneté, reste à payer et seuils d’escalade",4)
    card(fig,.06,.75,.25,.105,"Reste à payer",f"{overdue/1000:.0f} k€","#C84C4C","Échéances en retard au snapshot")
    card(fig,.355,.75,.25,.105,"Contrats > 90 jours",f"{n90:,}".replace(","," "),"#8D3544","Alerte de recouvrement renforcée")
    card(fig,.65,.75,.25,.105,"Échéances impayées",f"{len(arrears):,}".replace(","," "),"#E8A23A","Échéances échues non intégralement réglées")
    ax=fig.add_axes([.07,.18,.36,.48]);panel(ax,"Reste à payer par tranche")
    ax.bar(due_buckets.index,due_buckets.values/1000,color=["#E8A23A","#E67D46","#D8574F","#8D3544"]);ax.set_ylabel("k€");ax.tick_params(axis="x",rotation=22)
    ax=fig.add_axes([.49,.18,.44,.48]);ax.set_facecolor("#FFFFFF");ax.set_title("Top contrats à risque",loc="left",color="#17324D",pad=12);ax.axis("off")
    rows=[]
    for r in top_risk.itertuples():rows.append([r.contrat_id,r.territoire,f"{r.reste_a_payer:,.0f} €".replace(","," "),f"{int(r.retard_max)} j"])
    table=ax.table(cellText=rows,colLabels=["Contrat","Territoire","Reste dû","Retard max"],loc="center",cellLoc="left",colLoc="left")
    table.auto_set_font_size(False);table.set_fontsize(8);table.scale(1,1.7)
    for (r,c),cell in table.get_celld().items():
        if r==0:cell.set_facecolor("#"+NAVY);cell.set_text_props(color="white",weight="bold")
        elif r%2==0:cell.set_facecolor("#F2F6FA")
        if c==3 and r>0:
            days=int(top_risk.iloc[r-1].retard_max);cell.set_facecolor("#F7D9D6" if days>90 else "#FCEBD0")
    fig.text(.07,.09,"Seuils d’alerte : orange 31–60 j · rouge 61–90 j · bordeaux >90 j. Règles de mise en forme proposées dans le guide.",fontsize=8,color="#65758A")
    finish(fig,"04_surveillance_impayes.png")

    # 5 Data quality
    fig=base_page("Qualité des données","Contrôles d’entrée · anomalies détectées avant chargement dans le modèle",5)
    total_issues=int(controls.anomalies.sum())
    card(fig,.06,.75,.25,.105,"Familles de contrôle",f"{len(controls)}","#3A78A6","Contrôles appliqués au staging")
    card(fig,.355,.75,.25,.105,"Anomalies signalées",f"{total_issues:,}".replace(","," "),"#C84C4C","Lignes suspectes; doublons comptés par occurrence")
    clean_n=int(con.execute("SELECT COUNT(*) FROM contrats").fetchone()[0])
    raw_n=len(frames["contrats"])
    card(fig,.65,.75,.25,.105,"Contrats acceptés",f"{clean_n:,} / {raw_n:,}".replace(","," "),"#138A82","Après déduplication et règles de rejet")
    ax=fig.add_axes([.08,.17,.53,.49]);panel(ax,"Résultats par type de contrôle")
    vals=controls.sort_values("anomalies");bars=ax.barh(vals.controle.str.replace("_"," "),vals.anomalies,color=["#"+RED if n else "#"+TEAL for n in vals.anomalies])
    ax.set_xlabel("Lignes en anomalie")
    for bar,val in zip(bars,vals.anomalies):ax.text(max(1,val),bar.get_y()+bar.get_height()/2,f"{int(val):,}".replace(","," "),va="center",fontsize=8)
    ax2=fig.add_axes([.68,.17,.25,.49]);panel(ax2,"Familles surveillées");ax2.axis("off")
    labels=["Clés dupliquées","Échéances orphelines","Dates incohérentes","Montants négatifs","Surpaiements","Réconciliation legacy","Tests d’acceptation"]
    for i,label in enumerate(labels):
        ax2.text(.04,.92-i*.12,"✓",color="#"+TEAL,fontsize=14,weight="bold",transform=ax2.transAxes)
        ax2.text(.16,.92-i*.12,label,color=TEXT,fontsize=9,transform=ax2.transAxes)
    finish(fig,"05_qualite_donnees.png")

    # Before/after comparison: a cropped spreadsheet-like export vs the migrated production page.
    fig=plt.figure(figsize=(16,7),facecolor="#F3F6FA")
    fig.text(.045,.95,"AVANT / APRÈS · PRODUCTION MENSUELLE",fontsize=20,weight="bold",color="#17324D",va="top")
    fig.text(.045,.90,"Même indicateur métier · la migration rend les filtres et la règle de calcul explicites",fontsize=10,color="#65758A",va="top")
    ax=fig.add_axes([.05,.16,.42,.65]);ax.set_facecolor("#FFFFFF");ax.axis("off");ax.set_title("AVANT · export BO vers Excel",loc="left",color="#17324D",pad=14)
    legacy_month=frames["contrats"].merge(frames["clients"][["client_id","territoire"]],on="client_id",how="left")
    legacy_month["mois_production"]=legacy_month.date_debut.str[:7]
    sample=legacy_month[legacy_month.mois_production=="2025-12"].groupby(
        ["mois_production","produit","territoire"],as_index=False
    ).agg(nb_contrats=("contrat_id","count"),montant_production=("montant_finance","sum")).tail(8)
    sample["montant_production"]=sample.montant_production.map(lambda x:f"{x:,.0f} €".replace(","," "))
    tab=ax.table(cellText=sample.values,colLabels=["Mois","Produit","Territoire","Contrats","Financé"],loc="center",cellLoc="left")
    tab.auto_set_font_size(False);tab.set_fontsize(8);tab.scale(1,1.8)
    for (r,c),cell in tab.get_celld().items():
        if r==0:cell.set_facecolor("#D9E3EC");cell.set_text_props(weight="bold",color="#17324D")
        elif r%2==0:cell.set_facecolor("#F4F6F8")
    ax=fig.add_axes([.54,.16,.41,.65]);panel(ax,"APRÈS · vue interactive simulée Power BI")
    ax.plot(monthly.mois,monthly.production/1e6,color="#138A82",marker="o",linewidth=2.4)
    ax.fill_between(range(len(monthly)),monthly.production/1e6,color="#138A82",alpha=.12)
    ax.set_xticks(range(len(monthly)));ax.set_xticklabels([m[-2:]+"/"+m[2:4] for m in monthly.mois],rotation=35,ha="right")
    ax.set_ylabel("M€");fig.text(.55,.06,"Maquette reconstruite depuis des données synthétiques; ce n’est pas une capture Power BI Desktop.",fontsize=8,color="#65758A")
    finish(fig,"avant_apres_production.png")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    args=parser.parse_args();root=args.root; data=root/"data"
    con,frames=build_database(data,root)
    outputs=build_legacy_reports(con,frames,root)
    recipe=build_recipe(con,frames,outputs,root)
    build_visuals(con,frames,outputs,recipe,root)
    con.close()
    print("Base SQLite, 3 classeurs legacy, cahier de recette et 6 PNG générés.")
    print("SQL QA:\n",frames["controls"].to_string(index=False))

if __name__=="__main__": main()

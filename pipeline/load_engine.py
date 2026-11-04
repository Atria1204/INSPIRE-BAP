"""Load the team engine output (contract v0.2, run in eng_run_manifest.json) into the app database.

The app does not recompute recommendations (handover section 12, "No recalculation"). This script copies the engine
files into eng_* tables and makes the app's per-part columns read from them:

    materials.action / action_qty / action_reason   <- eng_recommendation (demand A, PR PO view ED, X2 at 95%)
    materials.rec_min / rec_max                      <- proposed s / S of X2 (Grade A only, D-24); others keep recorded
    materials.p_stockout / stockout_risk             <- eng_health_flags shortfall probability and risk level
    proposed_actions                                 <- every Reorder, Reduce and Maintain candidate

The app's own earlier values are kept in materials_app for reference.

    python pipeline/load_engine.py [path/to/data/processed/engine]
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parents[1] / "final-caliber26-aetherxinspire" / "data" / "processed" / "engine"
DB = ROOT / "data" / "aether_spare.db"
WORK = ROOT / "data" / "aether_spare_engine.db"
SCN = ("A", "ED")                      # the app shows demand scenario A and the exact-distinct PR PO view
PRIMARY = "SC-A-ED-X2-BO-K20"          # Grade A recommendation row; others use SC-ALL-NA-NA-NA-K0


def read(name):
    return pd.read_csv(SRC / name, dtype={"material_no": str, "supplier_code": str}, keep_default_na=False, low_memory=False)


def num(s):
    return pd.to_numeric(s.replace("", None), errors="coerce")


manifest = json.loads((SRC / "eng_run_manifest.json").read_text(encoding="utf-8"))
assert manifest.get("run_id") and manifest.get("data_label"), "reject run: manifest or data_label missing (handover 6)"
print("run", manifest["run_id"], "contract", manifest.get("spec_version"))

shutil.copyfile(DB, WORK)
con = sqlite3.connect(WORK)

# keep the app's own values once, then always start from them so the script can be re-run
if not con.execute("SELECT name FROM sqlite_master WHERE name='materials_app'").fetchone():
    con.execute("CREATE TABLE materials_app AS SELECT * FROM materials")
    con.execute("CREATE TABLE proposed_actions_app AS SELECT * FROM proposed_actions")

tables = {}
rec_all = read("eng_recommendation.csv"); tables["eng_recommendation"] = rec_all
params = read("eng_proposed_parameters.csv"); tables["eng_proposed_parameters"] = params[(params.demand_scenario == SCN[0]) & (params.pr_view == SCN[1])]
sim = read("eng_scenario_result.csv"); tables["eng_scenario_result"] = sim[(sim.demand_scenario == SCN[0]) & (sim.pr_view == SCN[1])]
tables["eng_health_flags"] = read("eng_health_flags.csv")
tables["eng_material_tier"] = read("eng_material_tier.csv")
sup = read("eng_supply_context.csv"); tables["eng_supply_context"] = sup[sup.pr_view == SCN[1]]
tables["eng_kpi_summary"] = read("eng_kpi_summary.csv")
tables["eng_explanation_facts"] = read("eng_explanation_facts.csv")
fc = read("eng_forecast.csv"); tables["eng_forecast"] = fc[fc.demand_scenario == SCN[0]]
RENAME = {"proposed_S": "proposed_order_up_to", "S_used": "order_up_to_used", "proposed_S_capped_at_recorded_max": "order_up_to_capped_at_recorded_max"}
for name, df in tables.items():
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})
    df.to_sql(name, con, if_exists="replace", index=False)
    print(f"{name}: {len(df):,} rows")
con.execute("DROP TABLE IF EXISTS eng_manifest")
con.execute("CREATE TABLE eng_manifest (key TEXT, value TEXT)")
con.executemany("INSERT INTO eng_manifest VALUES (?,?)", [(k, json.dumps(v) if isinstance(v, (dict, list)) else str(v)) for k, v in manifest.items()])
for t, c in [("eng_recommendation", "material_no"), ("eng_proposed_parameters", "material_no"), ("eng_scenario_result", "material_no"),
             ("eng_health_flags", "material_no"), ("eng_explanation_facts", "material_no"), ("eng_supply_context", "material_no"), ("eng_forecast", "material_no")]:
    con.execute(f"CREATE INDEX IF NOT EXISTS ix_{t} ON {t}({c})")

# one display row per part
rec = rec_all[rec_all.scenario_id.isin([PRIMARY, "SC-ALL-NA-NA-NA-K0"])].copy()
rec["prio"] = (rec.scenario_id == PRIMARY).astype(int)
rec = rec.sort_values("prio", ascending=False).drop_duplicates("material_no")
hf = tables["eng_health_flags"].set_index("material_no")
risk_map = {"High": "HIGH", "Medium": "MEDIUM", "Low": "LOW"}
con.execute("DROP TABLE IF EXISTS eng_primary")
prim = pd.DataFrame({
    "material": rec.material_no, "action": rec.recommended_action, "action_label": rec.action_label,
    "action_qty": num(rec.proposed_Q), "reason": rec.reason, "trigger": rec.trigger_condition,
    "s_point": num(rec.proposed_s), "s_level": num(rec.proposed_S), "risk_level": rec.risk_level, "evidence_class": rec.evidence_class,
    "confidence": rec.confidence, "limitations": rec.limitations, "requires_review": rec.requires_review,
    "consensus_status": rec.consensus_status, "method_class": rec.method_class, "output_class": rec.output_class,
    "scenario_id": rec.scenario_id})
prim["p_short"] = prim.material.map(num(hf["shortfall_probability_max"]))
prim["stock_risk"] = prim.material.map(hf["stockout_risk_level"]).map(risk_map)
prim.to_sql("eng_primary", con, index=False)

con.executescript("""
DELETE FROM materials; INSERT INTO materials SELECT * FROM materials_app;
UPDATE materials SET
  action = (SELECT e.action FROM eng_primary e WHERE e.material = materials.material),
  action_qty = COALESCE((SELECT CASE WHEN e.action = 'REORDER' THEN MAX(0, e.s_level - materials.stock) END FROM eng_primary e WHERE e.material = materials.material), 0),
  action_reason = (SELECT e.reason || ' Trigger: ' || e.trigger || '.' FROM eng_primary e WHERE e.material = materials.material),
  rec_min = COALESCE((SELECT CAST(e.s_point AS INTEGER) FROM eng_primary e WHERE e.material = materials.material AND e.s_point IS NOT NULL), CAST(COALESCE(min_qty, 0) AS INTEGER)),
  rec_max = COALESCE((SELECT CAST(e.s_level AS INTEGER) FROM eng_primary e WHERE e.material = materials.material AND e.s_level IS NOT NULL), CAST(COALESCE(max_qty, 0) AS INTEGER)),
  p_stockout = (SELECT e.p_short FROM eng_primary e WHERE e.material = materials.material),
  stockout_risk = COALESCE((SELECT e.stock_risk FROM eng_primary e WHERE e.material = materials.material), 'NOT ASSESSED'),
  excess_qty = MAX(0, stock - COALESCE(max_qty, 0)) * (COALESCE(max_qty, 0) > 0),
  excess_value_idr = MAX(0, stock - COALESCE(max_qty, 0)) * (COALESCE(max_qty, 0) > 0) * COALESCE(unit_price_idr, 0);
UPDATE materials SET health = COALESCE((SELECT CASE
    WHEN h.flag_potentially_obsolete_candidate = 1 THEN 'dead stock'
    WHEN h.flag_non_moving_by_recorded_issues = 1 THEN 'non-moving'
    WHEN h.flag_slow_moving_by_recorded_issues = 1 THEN 'slow-moving'
    WHEN h.flag_stock_above_recorded_max = 1 THEN 'excess'
    WHEN h.flag_stock_at_or_below_recorded_min = 1 THEN 'below reorder point'
    ELSE 'healthy' END FROM eng_health_flags h WHERE h.material_no = materials.material), health);
UPDATE materials SET forecast_monthly = (SELECT CAST(NULLIF(f.forecast_quantity, '') AS REAL) FROM eng_forecast f
    WHERE f.material_no = materials.material AND f.horizon_basis = 'next_month_rate' AND f.forecast_eligible = 1 LIMIT 1);
DELETE FROM proposed_actions;
""")
cand = prim[prim.action.isin(["REORDER", "REDUCE", "HOLD"])].copy()
order = {"REORDER": 0, "REDUCE": 1, "HOLD": 2}
cand["o"] = cand.action.map(order)
cand = cand.sort_values(["o", "p_short"], ascending=[True, False]).reset_index(drop=True)
types = {"REORDER": "Reorder", "REDUCE": "Reduce", "HOLD": "Maintain"}
con.executemany("INSERT INTO proposed_actions (action_id, material, type, trigger_rule, trigger_values) VALUES (?,?,?,?,?)",
                [(f"E-{i + 1:04d}", r.material, types[r.action], r.reason, r.trigger) for i, r in cand.iterrows()])
con.commit()
print("actions", con.execute("SELECT action, COUNT(*) FROM materials GROUP BY 1").fetchall())
print("proposed_actions", con.execute("SELECT type, COUNT(*) FROM proposed_actions GROUP BY 1").fetchall())
con.execute("VACUUM")
con.close()

dst = sqlite3.connect(DB)
src = sqlite3.connect(WORK)
src.backup(dst)
src.close(); dst.close()
WORK.unlink()
print("loaded into", DB)

"""Second build step (runs after build_db.py): equipment context, INSpire exception flags and proposed actions.

    python pipeline/build_db.py        (calls this file at the end)

Adds to data/aether_spare.db:
- equipment            one row per functional location: category, schematic drawing, counts
- material_component   which drawing component a part belongs to, inferred from its description
- material_flags       INSpire Command Center exception rules per part (Feature Spec 3.1)
- proposed_actions     one proposed action per rule hit (Action Center starts from these)
- kpi                  Command Center KPI values with formula and label
- definitions          DEF-01..DEF-15 register with the team's current answer
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import os
DB = Path(os.getenv("AETHER_DB", ROOT / "data" / "aether_spare.db"))
WINDOW_DAYS = 518

# ---------------- equipment category from the functional-location tag and description (PROPOSED rule)
CATEGORY_RULES = [  # (category, drawing, test on tag, test on description)
    ("Site system", None, r"^SITE_", None),
    ("Piping", None, r"^[A-Z]{2}_\d", r"^PIPE"),
    ("Motor", "motorpump", r"-M$", r"^MOTOR"),
    ("Pump", "pump", r"_PP-\d+[A-Z]?$", r"PUMP"),
    ("Compressor", "compressor", None, r"COMPRESSOR"),
    ("Fan and blower", "blower", None, r"\b(FAN|BLOWER)\b"),
    ("Heat exchanger", "exchanger", r"_HE-", r"EXCHANGER|COOLER|CONDENSER|REBOILER|\bTLE\b|PREHEATER|HEATER"),
    ("Furnace", None, r"_BF-", r"FURNACE|BURNER"),
    ("Safety valve", None, r"_(PRV|PSV|SV)-", r"SAFETY VALVE"),
    ("Control valve", None, r"_([A-Z]{1,2}CV|SDV|XV)-", r"VALVE"),   # control, on-off and shutdown valves (safety valves are caught one rule above)
    ("Vessel and column", None, r"_(VD|CL|TK|DR)-", r"DRUM|COLUMN|SCRUBBER|TANK|VESSEL|TOWER"),
    ("Electrical and I/O", None, r"_(JB|MC)-", r"JUNCTION|MARSHALLING|TERMINAL|SLOT|PANEL"),
    ("Civil structure", None, r"-CST$", r"CONCRETE|STRUCTURE"),
    ("Instrument", None, r"_[A-Z]{2,4}-\d", r"PRESSURE|TEMPERATURE|FLOW|LEVEL|GAUGE|SWITCH|TRANSMITTER|\bDP\b|ANALY"),
]

# ---------------- component placement from the part description (PROPOSED, Feature Spec 3.2)
COMPONENT_RULES = [
    ("bearing", r"\bBEARING"), ("seal", r"\bSEAL|PACKING"), ("coupling", r"COUPLING"),
    ("casing", r"IMPELLER|WEAR RING|CASING|ROTOR|BLADE|DIAPHRAGM"), ("tubes", r"\bTUBE|BUNDLE"),
    ("gasket", r"GASKET"), ("motor", r"MOTOR|WINDING|STATOR|TERMINAL"), ("lube", r"GREASE|\bOIL\b|LUBE"),
]
# drawing component ids each placement maps to (ids from the AETHER preliminary twin drawings)
HOTSPOT = {
    "pump": {"bearing": "bearing", "seal": "seal", "coupling": "coupling", "casing": "casing", "motor": "motor", "gasket": "discharge", "lube": "bearing"},
    "motorpump": {"bearing": "motor_de", "motor": "stator", "coupling": "coupling", "casing": "pump", "seal": "pump", "lube": "motor_de"},
    "compressor": {"bearing": "bearing_de", "coupling": "coupling", "casing": "casing", "motor": "driver", "lube": "lube", "seal": "casing", "gasket": "casing"},
    "exchanger": {"tubes": "tubes", "gasket": "channel", "casing": "shell"},
    "blower": {"bearing": "bearing", "coupling": "coupling", "casing": "housing", "motor": "motor", "lube": "bearing"},
}

DEFINITIONS = [
    ("DEF-01", "PR PO exact duplicates", "Same document line recorded more than once, or real repeated lines?", "Proceeding on assumption", "Treated as copies: distinct rows used; 5,420 removed."),
    ("DEF-02", "Min.Qty, Max.Qty", "Reorder point and maximum level, or other parameters?", "Proceeding on assumption", "Read as reorder point and order-up-to level; 'below Min' is a comparison, not a stockout."),
    ("DEF-03", "Criticality A, B, C, S", "Meaning and rank order of each code.", "Answered by team", "A is the highest; S is a special class (mostly safety items); order used A > S > B > C."),
    ("DEF-04", "MRP Type Non Stock", "Why do 1,683 Non Stock materials hold stock?", "Open", "Flagged, not corrected."),
    ("DEF-05", "PO-Item Amount", "Line total or unit price? Net or gross? Tax?", "Answered by team", "Unit price: it does not grow with quantity (correlation -0.07); as a line total a bearing would cost IDR 28 thousand."),
    ("DEF-06", "PO-Delivery Date", "Promised date? Is a goods-receipt date available?", "Proceeding on assumption", "Promised date. Lead times are 'promised', never 'actual'."),
    ("DEF-07", "Order prefixes 201-209", "Order type for each prefix.", "Open", "Kept as codes."),
    ("DEF-08", "PR-Type, PO prefix, purchasing group", "Meaning of each code.", "Open", "Kept as codes."),
    ("DEF-09", "Notification types N1, N2, N3, N6", "Meaning of each type.", "Proceeding on assumption", "N2 is 100% Emergency priority and is shown as 'emergency notification'."),
    ("DEF-10", "Cycle descriptions", "Confirm the interval mapping (28 spellings).", "Proceeding on assumption", "Mapped to months; used only as an indicative PM signal."),
    ("DEF-11", "Start of cycle", "Anchor date, first due date or last completion?", "Proceeding on assumption", "Read as anchor date; projected PM dates are indicative."),
    ("DEF-12", "Stock snapshot", "Date of the Stock value.", "Proceeding on assumption", "Assumed current at 1 Oct 2026, the day after the last transaction."),
    ("DEF-13", "Plant 1000, prefixes PX, PY, UT", "What each stands for.", "Open", "Kept as codes."),
    ("DEF-14", "Notification Date vs Created On", "Which date is authoritative?", "Proceeding on assumption", "Notification Date used."),
    ("DEF-15", "Units LG, RL, ASS, SHT", "Meaning of each unit.", "Proceeding on assumption", "Length, roll, assembly, sheet; never summed across units."),
]


def classify(tag, desc):
    d = (desc or "").upper()
    for cat, drawing, tag_rx, desc_rx in CATEGORY_RULES:
        if (tag_rx and re.search(tag_rx, tag)) or (desc_rx and re.search(desc_rx, d)):
            return cat, drawing
    return "Other equipment", None


def component_of(desc):
    d = (desc or "").upper()
    for comp, rx in COMPONENT_RULES:
        if re.search(rx, d):
            return comp
    return "other"


def main():
    con = sqlite3.connect(DB)
    fl = pd.read_sql("SELECT funcloc, description, criticality FROM raw_funcloc", con)
    bom = pd.read_sql("SELECT funcloc, material, installed_qty FROM raw_bom", con)
    nt = pd.read_sql("SELECT funcloc, notif_type, priority, order_no FROM raw_notification", con)
    mi = pd.read_sql("SELECT funcloc FROM raw_maintenance_plan", con)
    mat = pd.read_sql("SELECT * FROM materials", con)
    mv = pd.read_sql("SELECT material, order_no, quantity FROM raw_movement", con)
    pp = pd.read_sql("SELECT material, lead_time_days FROM raw_pr_po", con)

    # ---- equipment
    cat = fl.apply(lambda r: classify(r.funcloc, r.description), axis=1, result_type="expand")
    fl["category"], fl["drawing"] = cat[0], cat[1]
    fl["n_materials"] = fl.funcloc.map(bom.groupby("funcloc").material.nunique()).fillna(0).astype(int)
    fl["n_notifications"] = fl.funcloc.map(nt.groupby("funcloc").size()).fillna(0).astype(int)
    fl["n_emergency"] = fl.funcloc.map(nt[nt.notif_type == "N2"].groupby("funcloc").size()).fillna(0).astype(int)
    fl["n_plan_items"] = fl.funcloc.map(mi.groupby("funcloc").size()).fillna(0).astype(int)
    fl.to_sql("equipment", con, index=False, if_exists="replace")

    # ---- material component placement
    mc = mat[["material", "description"]].copy()
    mc["component"] = mc.description.map(component_of)
    mc[["material", "component"]].to_sql("material_component", con, index=False, if_exists="replace")
    pd.DataFrame([(d, c, h) for d, m in HOTSPOT.items() for c, h in m.items()],
                 columns=["drawing", "component", "hotspot"]).to_sql("hotspot_map", con, index=False, if_exists="replace")

    # ---- INSpire exception flags (Feature Spec 3.1, values recounted on our build)
    promised = pp.groupby("material").lead_time_days.median()
    m = mat.set_index("material")
    issued = m.n_issues > 0
    stock_item = m.mrp_type == "Stock Item"
    f = pd.DataFrame(index=m.index)
    f["below_min"] = (stock_item & issued & (m.stock < m.min_qty)).astype(int)
    ltd = (m.total_qty / WINDOW_DAYS) * m.index.map(promised).astype(float)
    f["testable_min"] = (stock_item & issued & m.index.map(promised).notna()).astype(int)
    f["min_below_ltd"] = ((f.testable_min == 1) & (ltd > m.min_qty)).astype(int)
    f["lead_time_demand_simple"] = ltd.round(2)
    f["nonstock_issued"] = ((m.mrp_type == "Non Stock") & issued).astype(int)
    f["idle_stock_item"] = (stock_item & (m.stock > 0) & ~issued).astype(int)

    # ---- abnormal consumption (KQ1): a month above 3x the part's median non-zero month and above mean + 3 sd
    md = pd.read_sql("SELECT material, month, quantity FROM monthly_demand", con)
    ab = {}
    for mat_id, g in md[md.quantity > 0].groupby("material"):
        q = g.quantity
        if len(q) < 3:
            continue
        cut = max(3 * q.median(), q.mean() + 3 * q.std(ddof=0))
        hits = g[g.quantity > cut]
        if len(hits):
            ab[mat_id] = (len(hits), hits.month.max(), float(hits.quantity.max()), float(q.median()))
    f["abnormal_months"] = [ab.get(i, (0,))[0] for i in f.index]
    f["abnormal_last_month"] = [ab.get(i, (0, None))[1] for i in f.index]
    f["abnormal_peak_qty"] = [ab.get(i, (0, None, None))[2] for i in f.index]
    f["abnormal_typical_qty"] = [ab.get(i, (0, None, None, None))[3] for i in f.index]

    # ---- when to reorder (KQ2): days until stock falls to the reorder point at the forecast rate
    daily = m.forecast_monthly / 30.4
    gap = m.stock - m.reorder_point
    days = (gap / daily.where(daily > 0)).clip(lower=0)
    f["days_to_reorder"] = days.round(0)
    f["reorder_by"] = [None if pd.isna(d) else str((pd.Timestamp("2026-10-01") + pd.Timedelta(days=int(d))).date()) for d in days]
    f.reset_index().to_sql("material_flags", con, index=False, if_exists="replace")

    # work-order to BoM match (linked issue rows whose part is in the BoM of the notification's location)
    mv = mv.reset_index().rename(columns={"index": "row_id"})
    linked = mv.merge(nt[["order_no", "funcloc"]].dropna(), on="order_no")   # an order can sit on several notifications
    pairs = set(zip(bom.funcloc, bom.material))
    linked["hit"] = [(fl_, m_) in pairs for fl_, m_ in zip(linked.funcloc, linked.material)]
    per_row = linked.groupby("row_id").hit.any()
    match, linked_rows = int(per_row.sum()), int(len(per_row))
    share_lines_nonstock = mv.material.isin(m.index[m.mrp_type == "Non Stock"]).mean()

    kpi = [
        ("below_min", "Issued Stock Items below Min", int(f.below_min.sum()), None, "Derived",
         "Stock Item, issued in the window, stock < Min. A comparison, not a stockout (DEF-02)."),
        ("min_below_ltd", "Min below promised lead-time demand", int(f.min_below_ltd.sum()), int(f.testable_min.sum()), "Derived",
         "Stock Item, issued, promised interval known: (units issued ÷ 518 days) × median promised interval > Min. Assumes Min is a reorder point (DEF-02)."),
        ("nonstock_issued", "Demand without a stocking policy", int(f.nonstock_issued.sum()), round(float(share_lines_nonstock) * 100, 1), "Observed",
         "Non Stock (no Min/Max) parts issued in the window; second value = share of all issue lines."),
        ("idle_stock_item", "Idle Stock Items", int(f.idle_stock_item.sum()), None, "Observed",
         "Stock Item with stock on hand and no issue May 2025 – Sep 2026."),
        ("wo_bom_match", "Work order to BoM match", match, linked_rows, "Observed",
         "Issue rows whose order is in Notif History and whose part is in that location's BoM, over all such linked rows."),
    ]
    pd.DataFrame(kpi, columns=["key", "name", "value", "value2", "label", "formula"]).to_sql("kpi", con, index=False, if_exists="replace")

    # ---- proposed actions (Action Center starts from these; people move them on)
    acts = []

    def add(material, typ, rule, values):
        acts.append((f"A-{len(acts) + 1:05d}", material, typ, rule, values))

    mm = mat.set_index("material")
    for mid, r in mm.iterrows():
        if r.action == "REORDER":
            add(mid, "Replenish now", "Stock at or below the recommended reorder point",
                f"stock {r.stock:g}, recommended min/max {r.rec_min}/{r.rec_max}, run-out chance {r.p_stockout:.0%}")
        if f.at[mid, "min_below_ltd"]:
            add(mid, "Review Min/Max", "Min below promised lead-time demand",
                f"Min {r.min_qty:g} < lead-time demand {f.at[mid, 'lead_time_demand_simple']:g}; recommended {r.rec_min}/{r.rec_max}")
        if r.mrp_recommendation != "Keep":
            add(mid, "Review stocking decision", r.mrp_recommendation, r.mrp_reason)
        if r.action in ("REDUCE", "NO_ACTION_EVIDENCE"):
            add(mid, "Review excess or idle stock", f"{r.health}; {r.action}",
                f"stock {r.stock:g} vs recommended max {r.rec_max}; above max IDR {r.excess_value_idr:,.0f}")
    pd.DataFrame(acts, columns=["action_id", "material", "type", "trigger_rule", "trigger_values"]).to_sql(
        "proposed_actions", con, index=False, if_exists="replace")

    pd.DataFrame(DEFINITIONS, columns=["def_id", "field", "question", "status", "team_answer"]).to_sql(
        "definitions", con, index=False, if_exists="replace")

    for sql in ["CREATE INDEX IF NOT EXISTS ix_eq ON equipment(funcloc)", "CREATE INDEX IF NOT EXISTS ix_eqc ON equipment(category)",
                "CREATE INDEX IF NOT EXISTS ix_pa ON proposed_actions(material)", "CREATE INDEX IF NOT EXISTS ix_mf ON material_flags(material)",
                "CREATE INDEX IF NOT EXISTS ix_mc ON material_component(material)"]:
        con.execute(sql)
    con.commit()
    con.close()

    print("equipment categories:", fl.category.value_counts().to_dict())
    print("drawings:", fl.drawing.value_counts().to_dict())
    print("kpi:", [(k[0], k[2], k[3]) for k in kpi])
    print("abnormal consumption parts:", int((f.abnormal_months > 0).sum()),
          "| reorder within 30 days (not yet at ROP):", int(((f.days_to_reorder > 0) & (f.days_to_reorder <= 30)).sum()))
    print("proposed actions:", pd.Series([a[2] for a in acts]).value_counts().to_dict())


if __name__ == "__main__":
    main()

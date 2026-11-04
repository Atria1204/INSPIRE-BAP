"""Build the AETHER Spare SQLite database from the six CALIBER 2026 final-case Excel files.

    python pipeline/build_db.py

Runs locally (needs pandas + openpyxl). The web app only reads the resulting data/aether_spare.db,
so the deployed app needs no pandas.

Every derived number is computed here with a stated method. Assumptions live in the `assumptions`
table so the app (and the judges) can see them.
"""
import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
import os
DB = Path(os.getenv("AETHER_DB", ROOT / "data" / "aether_spare.db"))

# ---------------------------------------------------------------- assumptions (shown in the app)
AS_OF = pd.Timestamp("2026-10-01")          # day after the last record in the data (30 Sep 2026)
WINDOW_START = pd.Timestamp("2025-05-01")   # first month of consumption history
FX_TO_IDR = {"IDR": 1, "USD": 18000, "EUR": 20600, "SGD": 14000, "JPY": 115}   # USD set by team; others = 18,000 x cross rate
SERVICE_LEVEL = {"A": 0.99, "S": 0.975, "B": 0.95, "C": 0.90, "-": 0.90}
CRIT_RANK = {"A": 4, "S": 3, "B": 2, "C": 1, "-": 0}   # A highest; S = special (mostly SAFETY items), confirm with plant
ORDER_COST_IDR = 750_000                    # cost of raising one PR/PO
HOLDING_RATE = 0.25                         # carrying cost per year as share of item value
ALPHA = 0.15                                # smoothing constant for SBA / SES
N_SIM = 2000                                # Monte Carlo runs per part for lead-time demand
DEFAULT_LT_DAYS = None                      # filled with the fleet median lead time

ASSUMPTIONS = [
    ("as_of", str(AS_OF.date()), "Analysis date: the day after the last transaction in the data."),
    ("history_window", "2025-05 to 2026-09 (17 months)", "Monthly consumption buckets from Movement Material."),
    ("unit_price", "PO-Item Amount = net price per unit", "Correlation between PR quantity and amount is -0.07, so the amount is read as a unit price."),
    ("fx_to_idr", ", ".join(f"{k} {v:,}" for k, v in FX_TO_IDR.items()), "USD 18,000 set by the team (Nov 2026). EUR, SGD, JPY derived from USD 18,000 using market cross rates (EUR/USD ~1.14, USD/SGD ~1.28, JPY 115 per Google, Nov 2026). Replace with treasury rates."),
    ("criticality", "A > S > B > C", "Highest class of any functional location the part is installed on. A is the highest; S is a special class (most S locations are SAFETY items such as safety valves), placed between A and B until the plant confirms its rule."),
    ("service_level", ", ".join(f"{k} {v:.1%}" for k, v in SERVICE_LEVEL.items() if k != "-"), "Target cycle service level per criticality."),
    ("order_cost", f"IDR {ORDER_COST_IDR:,} per order", "Used in the economic order quantity."),
    ("holding_rate", f"{HOLDING_RATE:.0%} of item value per year", "Carrying cost: capital, storage, insurance, obsolescence."),
    ("forecast", f"SBA (Croston, Syntetos-Boylan) for intermittent and lumpy items, SES for smooth and erratic, alpha {ALPHA}",
     "SES: Brown (1959). Croston (1972). SBA bias correction: Syntetos & Boylan (2005). Standard methods for spare parts with irregular demand."),
    ("unit_price_method", "median of all PO prices of the part in the window", "Prices of the same part vary little (median spread max/min 1.07), so the median is used for planning and valuation."),
    ("mrp_recommendation", "Non Stock used 3+ times in 12 months -> Stock Item; Stock Item never used, class B/C/blank -> Non Stock",
     "Reviews the planning category itself, not only the numbers."),
    ("demand_class", "ADI 1.32 / CV2 0.49 (Syntetos-Boylan)", "Smooth, erratic, intermittent, lumpy."),
    ("lead_time", "PR date to PO delivery date, per material; fleet median when a part was never bought", "From PR PO."),
    ("planned_demand", "PM events in the next 12 months on functional locations where the part is installed",
     "Indicative only: maintenance plans do not list the spare parts they consume."),
    ("reorder_point", f"{N_SIM} Monte Carlo runs of lead-time demand per part; ROP = service-level percentile",
     "Banks & Carson, Discrete-Event System Simulation, Example 2.11 (lead-time demand). Suits irregular demand better than a normal formula."),
    ("value_outlier", "stock value above the 99.9th percentile of priced parts", "Shown separately so a few synthetic records do not dominate totals."),
    ("failure_signal", "Notifications N2 (all Emergency priority) treated as breakdowns", "From Notif History."),
]


def read(name):
    return pd.read_excel(RAW / f"{name}.xlsx")


def cycle_months(text: str) -> float | None:
    """'5 YEARLY' -> 60, '18 MONTHLY' -> 18, '2 WEEK' -> 0.46, 'Yearly' -> 12."""
    t = str(text).upper().strip()
    parts = t.split()
    n = float(parts[0]) if parts and parts[0].replace(".", "").isdigit() else 1.0
    if "YEAR" in t:
        return 12 * n
    if "MONTH" in t:
        return n
    if "WEEK" in t:
        return n * 7 / 30.4
    return None


def classify(adi, cv2):
    if adi is None:
        return "no demand"
    if adi < 1.32:
        return "smooth" if cv2 < 0.49 else "erratic"
    return "intermittent" if cv2 < 0.49 else "lumpy"


def sba(series, alpha=ALPHA):
    """Croston with Syntetos-Boylan bias correction. Returns demand per period."""
    z = p = None
    q = 1
    for x in series:
        if x > 0:
            if z is None:
                z, p = x, q
            else:
                z = z + alpha * (x - z)
                p = p + alpha * (q - p)
            q = 1
        else:
            q += 1
    if z is None:
        return 0.0
    return (1 - alpha / 2) * z / p


def ses(series, alpha=ALPHA):
    level = series[0]
    for x in series[1:]:
        level = level + alpha * (x - level)
    return level


RNG = np.random.default_rng(2026)


def lead_time_demand_sim(rate_per_day, sizes, lt_days, lt_std_days, n=N_SIM):
    """Monte Carlo lead-time demand (Banks & Carson, Example 2.11 style).
    Lead time ~ Normal(lt, lt_std) truncated at 1 day; issues during the lead time ~ Poisson(rate x LT);
    each issue size is resampled from this part's own history. Returns n simulated demands."""
    lts = np.maximum(1.0, RNG.normal(lt_days, lt_std_days, n))
    k = RNG.poisson(rate_per_day * lts)
    total = np.zeros(n)
    sizes = np.asarray(sizes, dtype=float)
    for i in np.nonzero(k)[0]:
        total[i] = RNG.choice(sizes, k[i]).sum()
    return total


def poisson_tail(mean, k):
    """P(X > k) for X ~ Poisson(mean)."""
    if mean <= 0:
        return 0.0
    k = int(max(k, -1))
    if k < 0:
        return 1.0
    term = math.exp(-mean)
    cdf = term
    for i in range(1, k + 1):
        term *= mean / i
        cdf += term
    return max(0.0, 1 - cdf)


def stock_now(r):
    return float(r.stock)


def main():
    bom, fl, mi, mv, nt, pp = (read(n) for n in ["BoM", "FuncLoc list", "Mitem & Mplan", "Movement Material", "Notif History", "PR PO"])

    # ---------------- clean raw tables
    fl.columns = ["funcloc", "description", "criticality"]
    fl["criticality"] = fl["criticality"].fillna("-")
    bom.columns = ["funcloc", "material", "description", "installed_qty", "unit", "min_qty", "max_qty", "stock", "mrp_type"]
    mv.columns = ["posting_date", "movement_type", "material", "description", "quantity", "unit", "order_no"]
    nt.columns = ["notif_date", "notification", "notif_type", "order_no", "priority", "funcloc", "description",
                  "created_on", "required_start", "required_end", "completion_date", "status"]
    nt["order_no"] = nt["order_no"].astype("Int64")
    mi.columns = ["funcloc", "funcloc_desc", "abc", "plan", "item", "item_text", "priority", "cycle", "cycle_start"]
    pp.columns = ["pr_type", "pr", "pr_item", "pr_date", "material", "description", "quantity", "uom", "pr_delivery_date",
                  "plant", "purchasing_group", "po", "po_item", "supplier_code", "supplier_name", "unit_price", "currency", "po_delivery_date"]
    # ---------------- data quality: duplicates found in the supplied files
    quality = [
        ("PR PO", "exact duplicate rows (same PR and PR item)", int(pp.duplicated(["pr", "pr_item"]).sum()), len(pp), "removed"),
        ("BoM", "exact duplicate rows", int(bom.duplicated().sum()), len(bom), "removed"),
        ("Movement Material", "identical rows (same date, part, quantity, order)", int(mv.duplicated().sum()), len(mv),
         "kept: may be two real issues; flagged for data owner"),
        ("BoM", "Non Stock parts with stock on hand", int(bom.loc[(bom.mrp_type == "Non Stock") & (bom.stock > 0), "material"].nunique()), int(bom["material"].nunique()), "kept, flagged (counted per part)"),
    ]
    pp = pp.drop_duplicates(["pr", "pr_item"]).copy()
    bom = bom.drop_duplicates().copy()

    for df, cols in [(mv, ["posting_date"]), (nt, ["notif_date", "created_on", "required_start", "required_end", "completion_date"]),
                     (mi, ["cycle_start"]), (pp, ["pr_date", "pr_delivery_date", "po_delivery_date"])]:
        for c in cols:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    pp["unit_price_idr"] = pp["unit_price"] * pp["currency"].map(FX_TO_IDR).fillna(1)
    pp["lead_time_days"] = (pp["po_delivery_date"] - pp["pr_date"]).dt.days
    pp["late_days"] = (pp["po_delivery_date"] - pp["pr_delivery_date"]).dt.days
    pp.loc[pp["lead_time_days"] < 0, "lead_time_days"] = np.nan
    fleet_lt = float(pp["lead_time_days"].median())
    fleet_lt_std = float(pp["lead_time_days"].std())

    # ---------------- criticality per material (best of its functional locations)
    crit_of = dict(zip(fl["funcloc"], fl["criticality"]))
    bom["criticality"] = bom["funcloc"].map(crit_of).fillna("-")
    bom["crit_rank"] = bom["criticality"].map(CRIT_RANK)

    # ---------------- failure and PM signals per functional location
    window_notif = nt[nt["notif_date"] >= WINDOW_START]
    breakdowns = window_notif[window_notif["notif_type"] == "N2"].groupby("funcloc").size()
    notifs = window_notif.groupby("funcloc").size()

    mi["cycle_months"] = mi["cycle"].map(cycle_months)
    horizon_end = AS_OF + pd.DateOffset(months=12)

    def due_in_horizon(row):
        if pd.isna(row.cycle_start) or not row.cycle_months:
            return 0
        step = pd.DateOffset(days=round(row.cycle_months * 30.4))
        d, n = row.cycle_start, 0
        if d < AS_OF:                          # jump forward to the first due date after AS_OF
            k = math.ceil((AS_OF - d).days / (row.cycle_months * 30.4))
            d = d + pd.DateOffset(days=round(k * row.cycle_months * 30.4))
        while d < horizon_end and n < 60:
            n += 1
            d = d + step
        return n

    mi["due_12m"] = mi.apply(due_in_horizon, axis=1)
    pm_due = mi.groupby("funcloc")["due_12m"].sum()

    bom["breakdowns"] = bom["funcloc"].map(breakdowns).fillna(0)
    bom["notifs"] = bom["funcloc"].map(notifs).fillna(0)
    bom["pm_due_12m"] = bom["funcloc"].map(pm_due).fillna(0)
    bom["pm_qty_12m"] = bom["pm_due_12m"] * bom["installed_qty"]

    mat = bom.groupby("material").agg(
        description=("description", "first"), unit=("unit", "first"), mrp_type=("mrp_type", "first"),
        stock=("stock", "first"), min_qty=("min_qty", "first"), max_qty=("max_qty", "first"),
        n_funcloc=("funcloc", "nunique"), installed_qty=("installed_qty", "sum"), crit_rank=("crit_rank", "max"),
        breakdowns_on_equipment=("breakdowns", "sum"), notifs_on_equipment=("notifs", "sum"),
        pm_events_12m=("pm_due_12m", "sum"), pm_qty_12m=("pm_qty_12m", "sum"))
    rank_to_crit = {v: k for k, v in CRIT_RANK.items()}
    mat["criticality"] = mat["crit_rank"].map(rank_to_crit)

    # ---------------- monthly consumption
    months = pd.period_range(WINDOW_START, AS_OF - pd.Timedelta(days=1), freq="M")
    mv["month"] = mv["posting_date"].dt.to_period("M")
    monthly = mv.groupby(["material", "month"])["quantity"].sum().unstack(fill_value=0).reindex(columns=months, fill_value=0)
    issues = mv.groupby("material").agg(n_issues=("quantity", "size"), total_qty=("quantity", "sum"),
                                        last_issue=("posting_date", "max"), first_issue=("posting_date", "min"),
                                        n_orders=("order_no", "nunique"))
    sizes_of = mv.groupby("material")["quantity"].apply(list).to_dict()
    window_days = (AS_OF - WINDOW_START).days
    last12 = mv[mv["posting_date"] >= AS_OF - pd.DateOffset(months=12)].groupby("material")["quantity"].agg(["size", "sum"])
    last12.columns = ["issues_12m", "qty_12m"]

    # ---------------- procurement per material
    proc = pp.groupby("material").agg(
        n_po=("po", "nunique"), unit_price_idr=("unit_price_idr", "median"), lead_time_days=("lead_time_days", "median"),
        lead_time_std=("lead_time_days", "std"), late_share=("late_days", lambda s: float((s > 0).mean())),
        avg_late_days=("late_days", lambda s: float(s[s > 0].mean()) if (s > 0).any() else 0.0),
        main_supplier=("supplier_name", lambda s: s.mode().iat[0]), last_po=("pr_date", "max"))

    mat = mat.join(issues).join(last12).join(proc)
    fleet_price = float(pp["unit_price_idr"].median())

    rows = []
    quant_rows = []
    SCENARIO_LEVELS = [0.80, 0.85, 0.90, 0.95, 0.975, 0.99, 0.995]
    for m, r in mat.iterrows():
        series = monthly.loc[m].tolist() if m in monthly.index else [0] * len(months)
        nz = [x for x in series if x > 0]
        if nz:
            adi = len(series) / len(nz)
            cv2 = (np.std(nz) / np.mean(nz)) ** 2 if len(nz) > 1 else 0.0
        else:
            adi = cv2 = None
        dclass = classify(adi, cv2)
        if dclass in ("intermittent", "lumpy"):
            f = sba(series)
            method = "SBA"
        elif dclass == "no demand":
            f, method = 0.0, "none"
        else:
            f, method = ses(series), "SES"
        sigma = float(np.std(series))

        lt = r.lead_time_days if not pd.isna(r.lead_time_days) else fleet_lt
        lt_std = r.lead_time_std if not pd.isna(r.lead_time_std) else fleet_lt_std
        lt_m, lt_std_m = lt / 30.4, lt_std / 30.4
        price = r.unit_price_idr if not pd.isna(r.unit_price_idr) else np.nan
        price_used = price if not pd.isna(price) else fleet_price

        crit = r.criticality
        sl = SERVICE_LEVEL[crit]
        z = float(pd.Series([sl]).map(lambda p: _z(p)).iat[0])
        if f > 0 and m in sizes_of:
            sim = lead_time_demand_sim(len(sizes_of[m]) / window_days, sizes_of[m], lt, lt_std)
            for lv, q in zip(SCENARIO_LEVELS, np.quantile(sim, SCENARIO_LEVELS)):
                quant_rows.append((str(m), lv, round(float(q), 2)))
            rop = float(np.quantile(sim, sl))                 # stock that covers lead-time demand sl% of the time
            ltd_mean = float(sim.mean())
            p_stockout = float((sim >= stock_now(r)).mean()) if stock_now(r) > 0 else float((sim > 0).mean())
        else:
            rop = ltd_mean = 0.0
            p_stockout = 0.0
        ss = max(0.0, rop - ltd_mean)
        annual = f * 12
        eoq = math.sqrt(2 * annual * ORDER_COST_IDR / (HOLDING_RATE * price_used)) if annual > 0 else 0.0

        insurance = f == 0 and crit in ("A", "S") and r.mrp_type == "Stock Item"
        if f > 0:
            rec_min = math.ceil(rop)
            rec_max = rec_min + max(1, math.ceil(eoq))
        elif insurance:
            rec_min, rec_max = 0, 1          # keep one insurance spare for critical equipment (human review)
        else:
            rec_min = rec_max = 0

        stock = float(r.stock)

        n12 = 0 if pd.isna(r.issues_12m) else int(r.issues_12m)
        if stock > 0 and pd.isna(r.last_issue):
            health = "dead stock"
        elif stock > 0 and r.last_issue < AS_OF - pd.DateOffset(months=12):
            health = "non-moving"
        elif stock > 0 and n12 <= 2 and stock > rec_max:
            health = "slow-moving"
        elif stock > rec_max and rec_max >= 0 and stock - rec_max >= 1 and f > 0:
            health = "excess"
        elif stock < rec_min:
            health = "below reorder point"
        else:
            health = "healthy"

        excess_qty = max(0.0, stock - rec_max)
        excess_value = excess_qty * price_used
        stock_value = stock * price_used

        # ---- reason sentences: every one carries this part's own numbers, so no two parts read alike
        idle = ("never issued in the 17-month history" if health == "dead stock"
                else f"last issued {r.last_issue.date():%d %b %Y}" if not pd.isna(r.last_issue) else "never issued")
        used_on = f"installed on {int(r.n_funcloc)} location{'s' if r.n_funcloc != 1 else ''} (criticality {crit})"
        signals = []
        if r.breakdowns_on_equipment:
            signals.append(f"{int(r.breakdowns_on_equipment)} emergency breakdown{'s' if r.breakdowns_on_equipment != 1 else ''} on that equipment")
        if r.pm_events_12m:
            signals.append(f"{int(r.pm_events_12m)} PM event{'s' if r.pm_events_12m != 1 else ''} due in the next 12 months")
        signal_txt = ("; " + ", ".join(signals)) if signals else "; no breakdowns or PM due on that equipment"
        money = f"IDR {excess_value:,.0f}" + (" (price estimated from fleet median)" if pd.isna(price) else "")

        if stock <= rec_min and (f > 0 or insurance) and rec_max > stock:
            action, qty = "REORDER", rec_max - stock
            if f > 0:
                why = (f"Stock {stock:g} is at or below the reorder point {rec_min}. Forecast {f:.2f} {r.unit}/month "
                       f"({dclass} demand, {len(nz)} of {len(series)} months used), promised lead time {lt:.0f} days"
                       f"{f', promised later than requested on {r.late_share:.0%} of purchase lines' if not pd.isna(r.late_share) and r.late_share > 0 else ''}. "
                       f"Chance of running out before a new order arrives: {p_stockout:.0%}. Order {qty:g} to reach {rec_max}.")
            else:
                why = (f"Zero stock of an insurance spare, {used_on}{signal_txt}. Keep 1 on hand.")
        elif health in ("dead stock", "non-moving") and excess_value > 0 and crit in ("A", "S"):
            action, qty = "NO_ACTION_EVIDENCE", excess_qty
            why = (f"{stock:g} {r.unit} on hand ({money}), {idle}; {used_on}{signal_txt}. "
                   f"A reliability engineer decides: keep as insurance spare or reduce by {excess_qty:g}.")
        elif health in ("dead stock", "non-moving") and excess_value > 0:
            action, qty = "REDUCE", excess_qty
            why = (f"{stock:g} {r.unit} on hand, {idle}; {used_on}{signal_txt}. "
                   f"Reduce by {excess_qty:g} to free {money}.")
        elif health in ("excess", "slow-moving") and excess_value > 0:
            action, qty = "REDUCE", excess_qty
            why = (f"Stock {stock:g} is above the recommended maximum {rec_max} (forecast {f:.2f}/month, "
                   f"{n12} issue{'s' if n12 != 1 else ''} in the last 12 months). Reducing by {excess_qty:g} frees {money}.")
        elif p_stockout >= 0.2 or n12 in (1, 2) or r.breakdowns_on_equipment > 0:
            action, qty = "MONITOR", 0
            why = (f"Stock {stock:g} within range {rec_min} to {rec_max}, but "
                   f"{f'{p_stockout:.0%} chance of running out during the {lt:.0f}-day promised lead time' if p_stockout >= 0.2 else f'only {n12} issue(s) in the last 12 months'}"
                   f"{signal_txt}. Watch before changing stock.")
        else:
            action, qty = "HOLD", 0
            why = (f"Stock {stock:g} is within the recommended range {rec_min} to {rec_max}"
                   + (f" (forecast {f:.2f}/month)." if f > 0 else f"; {idle}, nothing to free."))

        if f > 0:
            risk_level = "HIGH" if p_stockout >= 0.5 and crit in ("A", "S") else "MEDIUM" if p_stockout >= 0.2 else "LOW"
        else:
            risk_level = "MEDIUM" if insurance and stock == 0 else "LOW"

        if r.mrp_type == "Non Stock" and n12 >= 3:
            mrp_rec = "Change to Stock Item"
            mrp_why = f"Marked Non Stock (no min/max) but issued {n12} times in the last 12 months."
        elif r.mrp_type == "Stock Item" and dclass == "no demand" and crit in ("B", "C", "-"):
            mrp_rec = "Change to Non Stock"
            mrp_why = f"Stock Item never issued in 17 months on class {crit} equipment; buy when a job needs it."
        else:
            mrp_rec, mrp_why = "Keep", ""

        rows.append(dict(
            material=str(m), description=r.description, unit=r.unit, mrp_type=r.mrp_type, criticality=crit,
            mrp_recommendation=mrp_rec, mrp_reason=mrp_why,
            n_funcloc=int(r.n_funcloc), installed_qty=float(r.installed_qty),
            stock=stock, min_qty=float(r.min_qty), max_qty=float(r.max_qty),
            n_issues=0 if pd.isna(r.n_issues) else int(r.n_issues), total_qty=0 if pd.isna(r.total_qty) else float(r.total_qty),
            issues_12m=n12, qty_12m=0 if pd.isna(r.qty_12m) else float(r.qty_12m),
            last_issue=None if pd.isna(r.last_issue) else str(r.last_issue.date()),
            months_with_demand=len(nz), adi=None if adi is None else round(adi, 2), cv2=None if cv2 is None else round(cv2, 2),
            demand_class=dclass, forecast_method=method, forecast_monthly=round(f, 3), demand_sigma_monthly=round(sigma, 3),
            breakdowns_on_equipment=int(r.breakdowns_on_equipment), notifs_on_equipment=int(r.notifs_on_equipment),
            pm_events_12m=int(r.pm_events_12m), pm_qty_12m=float(r.pm_qty_12m),
            lead_time_days=round(lt, 1), lead_time_std_days=round(lt_std, 1), lead_time_source="material" if not pd.isna(r.lead_time_days) else "fleet median",
            late_share=None if pd.isna(r.late_share) else round(r.late_share, 3), main_supplier=r.main_supplier if isinstance(r.main_supplier, str) else None,
            n_po=0 if pd.isna(r.n_po) else int(r.n_po),
            unit_price_idr=None if pd.isna(price) else round(price, 0), price_source="PO history" if not pd.isna(price) else "fleet median",
            stock_value_idr=round(stock_value, 0), service_level=sl, z=round(z, 3),
            safety_stock=round(ss, 2), reorder_point=round(rop, 2), lead_time_demand_mean=round(ltd_mean, 2), eoq=round(eoq, 2),
            rec_min=rec_min, rec_max=rec_max, insurance_spare=int(insurance),
            p_stockout=round(p_stockout, 3), stockout_risk=risk_level,
            health=health, excess_qty=excess_qty, excess_value_idr=round(excess_value, 0),
            action=action, action_qty=qty, action_reason=why))

    out = pd.DataFrame(rows)
    cut = out.loc[out.price_source == "PO history", "stock_value_idr"].quantile(0.999)
    out["value_outlier"] = (out["stock_value_idr"] > cut).astype(int)
    monthly_long = monthly.stack().reset_index()
    monthly_long.columns = ["material", "month", "quantity"]
    monthly_long["month"] = monthly_long["month"].astype(str)
    monthly_long["material"] = monthly_long["material"].astype(str)

    suppliers = pp.groupby(["supplier_code", "supplier_name"]).agg(
        n_po=("po", "nunique"), n_lines=("po", "size"), median_lead_time=("lead_time_days", "median"),
        late_share=("late_days", lambda s: float((s > 0).mean())), avg_late_days=("late_days", lambda s: float(s[s > 0].mean()) if (s > 0).any() else 0.0)
    ).reset_index()

    try:
        DB.unlink(missing_ok=True)
    except PermissionError:
        raise SystemExit("\nThe database is open in another program (DB Browser?). "
                         "Close it there (File > Close Database), then run this script again.")
    con = sqlite3.connect(DB)
    out.to_sql("materials", con, index=False)
    monthly_long.to_sql("monthly_demand", con, index=False)
    # reorder point at several service levels, for the scenario page (no re-simulation needed at run time)
    pd.DataFrame(quant_rows, columns=["material", "service_level", "reorder_point"]).to_sql("rop_by_service_level", con, index=False)
    suppliers.to_sql("suppliers", con, index=False)
    pd.DataFrame(ASSUMPTIONS, columns=["key", "value", "note"]).to_sql("assumptions", con, index=False)
    pd.DataFrame(quality, columns=["file", "issue", "rows_affected", "rows_total", "treatment"]).to_sql("data_quality", con, index=False)
    # raw (cleaned) tables: the source of truth the numbers trace back to
    for name, df in [("raw_bom", bom.drop(columns=["crit_rank"])), ("raw_funcloc", fl), ("raw_movement", mv.drop(columns=["month"])),
                     ("raw_notification", nt), ("raw_pr_po", pp), ("raw_maintenance_plan", mi)]:
        d = df.copy()
        for c in d.columns:
            if pd.api.types.is_datetime64_any_dtype(d[c]):
                d[c] = d[c].dt.strftime("%Y-%m-%d")
        if "material" in d.columns:
            d["material"] = d["material"].astype(str)
        d.to_sql(name, con, index=False)
    cur = con.cursor()
    for sql in ["CREATE UNIQUE INDEX ix_mat ON materials(material)", "CREATE INDEX ix_md ON monthly_demand(material)", "CREATE INDEX ix_rop ON rop_by_service_level(material)",
                "CREATE INDEX ix_mv ON raw_movement(material)", "CREATE INDEX ix_pp ON raw_pr_po(material)",
                "CREATE INDEX ix_bom ON raw_bom(material)", "CREATE INDEX ix_bomfl ON raw_bom(funcloc)",
                "CREATE INDEX ix_nt ON raw_notification(funcloc)", "CREATE INDEX ix_mi ON raw_maintenance_plan(funcloc)"]:
        cur.execute(sql)
    con.commit()
    con.execute("VACUUM")
    con.close()

    print(f"materials: {len(out):,}   db: {DB} ({DB.stat().st_size / 1e6:.1f} MB)")
    print("fleet lead time median", fleet_lt, "days")
    print(out["demand_class"].value_counts().to_dict())
    print(out["health"].value_counts().to_dict())
    print(out["action"].value_counts().to_dict())
    print(out["stockout_risk"].value_counts().to_dict())
    print(out["mrp_recommendation"].value_counts().to_dict())
    o = out[out.value_outlier == 0]
    print(f"without outliers: stock value IDR {o.stock_value_idr.sum() / 1e9:,.1f} bn | excess IDR {o.excess_value_idr.sum() / 1e9:,.1f} bn | outliers {out.value_outlier.sum()}")
    d = out[out.forecast_monthly > 0]
    print("median current min/max vs recommended:", d.min_qty.median(), d.max_qty.median(), "->", d.rec_min.median(), d.rec_max.median())
    print(f"stock value IDR {out.stock_value_idr.sum() / 1e9:,.1f} bn | excess value IDR {out.excess_value_idr.sum() / 1e9:,.1f} bn")


def _z(p):
    """Inverse standard normal (Acklam's approximation), no scipy needed."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - 0.02425:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


if __name__ == "__main__":
    main()
    import build_context  # second step: equipment context, INSpire flags, proposed actions
    build_context.main()

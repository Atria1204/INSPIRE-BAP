"""Overview numbers and part lists. Every number is a SQL query over the `materials` table,
so it traces back to a row the user can open."""
from functools import lru_cache

from ..db import one, rows, scalar

CRITICAL = ("A", "S")


@lru_cache(maxsize=1)
def overview() -> dict:
    k = one("""
        SELECT COUNT(*) parts,
               SUM(stock_value_idr) stock_value,
               SUM(CASE WHEN value_outlier=0 THEN stock_value_idr ELSE 0 END) stock_value_clean,
               SUM(CASE WHEN value_outlier=1 THEN stock_value_idr ELSE 0 END) outlier_value,
               SUM(value_outlier) outliers,
               SUM(stockout_risk='HIGH') high_risk,
               SUM(stockout_risk='MEDIUM') medium_risk,
               SUM(criticality IN ('A','S') AND stock=0 AND forecast_monthly>0) critical_empty,
               SUM(criticality IN ('A','S') AND stock=0 AND forecast_monthly>0 AND p_stockout>=0.5) critical_empty_likely,
               SUM(mrp_type='Stock Item') stock_items,
               SUM(CASE WHEN value_outlier=0 AND price_source='fleet median' AND action IN ('REDUCE','NO_ACTION_EVIDENCE') THEN excess_value_idr ELSE 0 END) free_estimated,
               SUM(action='REORDER') reorder,
               SUM(action='REDUCE') reduce,
               SUM(action='NO_ACTION_EVIDENCE') review,
               SUM(action='MONITOR') monitor,
               SUM(action='HOLD') maintain,
               SUM(CASE WHEN action='REDUCE' AND value_outlier=0 THEN excess_value_idr ELSE 0 END) free_reduce,
               SUM(CASE WHEN action='NO_ACTION_EVIDENCE' AND value_outlier=0 THEN excess_value_idr ELSE 0 END) free_review,
               SUM(CASE WHEN action='REORDER' THEN action_qty*COALESCE(unit_price_idr,0) ELSE 0 END) reorder_value_priced,
               SUM(mrp_recommendation='Change to Stock Item') to_stock,
               SUM(mrp_recommendation='Change to Non Stock') to_nonstock,
               SUM(n_issues=0) never_used,
               SUM(price_source='PO history') priced_parts
        FROM materials""")
    k["health"] = rows("SELECT health, COUNT(*) n, SUM(stock_value_idr) value FROM materials WHERE value_outlier=0 GROUP BY health ORDER BY n DESC")
    k["demand_class"] = rows("SELECT demand_class, COUNT(*) n FROM materials GROUP BY demand_class ORDER BY n DESC")
    k["by_class"] = rows("""SELECT criticality, COUNT(*) parts, SUM(stockout_risk='HIGH') high_risk,
                             SUM(stock=0 AND forecast_monthly>0) empty_used, SUM(CASE WHEN value_outlier=0 THEN stock_value_idr END) value
                             FROM materials GROUP BY criticality ORDER BY CASE criticality WHEN 'A' THEN 1 WHEN 'S' THEN 2 WHEN 'B' THEN 3 WHEN 'C' THEN 4 ELSE 5 END""")
    k["reorder_by_class"] = rows("""SELECT criticality, COUNT(*) n FROM materials WHERE action='REORDER' GROUP BY criticality
                                    ORDER BY CASE criticality WHEN 'A' THEN 1 WHEN 'S' THEN 2 WHEN 'B' THEN 3 WHEN 'C' THEN 4 ELSE 5 END""")
    k["value_by_action"] = rows("""SELECT action, SUM(stock_value_idr) value, SUM(excess_value_idr) excess FROM materials
                                   WHERE value_outlier=0 GROUP BY action""")
    k["monthly_consumption"] = rows("""
        SELECT substr(v.posting_date, 1, 7) month, COUNT(*) issues, COUNT(DISTINCT v.material) parts,
               SUM(v.quantity * m.unit_price_idr) value
        FROM raw_movement v JOIN materials m ON m.material = v.material
        WHERE m.price_source = 'PO history' AND m.value_outlier = 0
        GROUP BY 1 ORDER BY 1""")
    k["demand_parts"] = scalar("SELECT COUNT(*) FROM materials WHERE forecast_monthly>0")
    k["lead_time_median"] = scalar("SELECT lead_time_days FROM materials WHERE lead_time_source='material' ORDER BY lead_time_days LIMIT 1 OFFSET (SELECT COUNT(*)/2 FROM materials WHERE lead_time_source='material')")
    k["late_share"] = scalar("SELECT AVG(late_days>0) FROM raw_pr_po")
    k["as_of"] = scalar("SELECT value FROM assumptions WHERE key='as_of'")
    return k


def top_risk(limit=12):
    """Engine Reorder candidates, highest simulated shortfall probability first."""
    return rows("""SELECT material, description, criticality, stock, rec_min, rec_max, forecast_monthly, lead_time_days,
                          p_stockout, action, action_qty, unit FROM materials
                   WHERE action='REORDER' ORDER BY p_stockout DESC, stock ASC LIMIT ?""", (limit,))


def engine():
    """Headline figures straight from the engine files (no recalculation)."""
    e = {"run_id": scalar("SELECT value FROM eng_manifest WHERE key='run_id'"),
         "data_label": scalar("SELECT value FROM eng_manifest WHERE key='data_label'")}
    e.update(one("""SELECT SUM(action='REORDER') reorder, SUM(action='REDUCE') reduce, SUM(action='HOLD') hold,
                           SUM(action='MONITOR') monitor, SUM(action='NO_ACTION_EVIDENCE') noact,
                           SUM(action IN ('REORDER','REDUCE','HOLD')) params,
                           SUM(stockout_risk='HIGH') high, SUM(stockout_risk='MEDIUM') medium, SUM(stockout_risk='LOW') low FROM materials"""))
    e.update(one("""SELECT SUM(flag_stock_above_recorded_max) above_max, SUM(flag_potentially_obsolete_candidate) obsolete,
                           SUM(flag_non_moving_by_recorded_issues) non_moving, SUM(flag_slow_moving_by_recorded_issues) slow
                    FROM eng_health_flags"""))
    ho = {r["policy"]: r for r in rows("""SELECT policy, CAST(numerator AS REAL) n, CAST(denominator AS REAL) d FROM eng_kpi_summary
                                          WHERE kpi_id='AV-1' AND run_set='HO' AND scenario LIKE 'SC-A-ED-%-K30'""")}
    e["ho"] = ho
    rng = {r["policy"]: r for r in rows("""SELECT policy, MIN(CAST(numerator AS REAL)) lo, MAX(CAST(numerator AS REAL)) hi FROM eng_kpi_summary
                                           WHERE kpi_id='AV-1' AND run_set='HO' GROUP BY policy""")}
    e["ho_range"] = rng
    e["reorder_by_class"] = rows("""SELECT criticality c, COUNT(*) n FROM materials WHERE action='REORDER' GROUP BY 1
                                    ORDER BY CASE criticality WHEN 'A' THEN 1 WHEN 'S' THEN 2 WHEN 'B' THEN 3 ELSE 4 END""")
    return e


def engine_part(material):
    """Everything the engine says about one part, for the part page."""
    out = {"primary": one("SELECT * FROM eng_primary WHERE material=?", (material,))}
    out["params"] = rows("""SELECT policy, service_level, proposed_s, proposed_order_up_to S, proposed_Q, safety_stock, parameter_status
                            FROM eng_proposed_parameters WHERE material_no=? ORDER BY policy""", (material,))
    out["mc"] = {r["policy"]: r for r in rows("""SELECT policy, s_used, order_up_to_used S, CAST(shortfall_probability AS REAL) p,
                          CAST(mean_on_hand AS REAL) on_hand, CAST(sim_fill_rate_quantity AS REAL) fill FROM eng_scenario_result
                          WHERE material_no=? AND run_set='MC-D'""", (material,))}
    out["ho"] = {r["policy"]: r for r in rows("""SELECT policy, any_shortfall, CAST(days_at_or_below_zero AS REAL) days FROM eng_scenario_result
                          WHERE material_no=? AND run_set='HO' AND scenario_id LIKE '%-K30'""", (material,))}
    out["tier"] = one("SELECT tier, policy_grade, demand_class, forecast_eligibility, abstain_reason, confidence FROM eng_material_tier WHERE material_no=?", (material,))
    out["fc"] = one("""SELECT forecast_quantity, forecast_method, rate_low, rate_high, abstain_reason FROM eng_forecast
                       WHERE material_no=? AND horizon_basis='next_month_rate'""", (material,))
    out["n_scen"] = scalar("SELECT COUNT(DISTINCT recommended_action) FROM eng_recommendation WHERE material_no=?", (material,))
    return out


def top_free(limit=8):
    return rows("""SELECT material, description, criticality, stock, rec_max, excess_qty, excess_value_idr, health, action, unit
                   FROM materials WHERE action IN ('REDUCE','NO_ACTION_EVIDENCE') AND value_outlier=0
                   ORDER BY excess_value_idr DESC LIMIT ?""", (limit,))


FILTERS = ["action", "health", "criticality", "demand_class", "stockout_risk", "mrp_recommendation", "mrp_type"]
SORTS = {"risk": "p_stockout DESC, forecast_monthly DESC", "value": "stock_value_idr DESC", "excess": "excess_value_idr DESC",
         "forecast": "forecast_monthly DESC", "material": "material",
         "last": "last_issue IS NULL, last_issue ASC, stock_value_idr DESC"}


SORT_COL = {"value": "stock_value_idr", "forecast": "forecast_monthly", "last": "last_issue", "excess": "excess_value_idr",
            "risk": "p_stockout", "material": "material", "stock": "stock",
            "class": "CASE criticality WHEN 'A' THEN 1 WHEN 'S' THEN 2 WHEN 'B' THEN 3 WHEN 'C' THEN 4 END"}


def filter_options():
    return {f: [r[f] for r in rows(f"SELECT DISTINCT {f} FROM materials WHERE {f} IS NOT NULL ORDER BY {f}")] for f in FILTERS}


# Lead repo definitions. T3 = simulation population: Stock Item, issued, promised interval and unit amount from PO
# history, non-zero recorded Min or Max (665). Grade A = T3 with at least 6 active months (228): proposed parameters.
T3_SQL = ("mrp_type = 'Stock Item' AND n_issues > 0 AND lead_time_source = 'material' "
          "AND (COALESCE(min_qty,0) > 0 OR COALESCE(max_qty,0) > 0)")
GRADE_A_SQL = f"({T3_SQL} AND months_with_demand >= 6)"


def demand_class(months):
    m = months or 0
    return "D0" if m == 0 else "D1" if m <= 2 else "D2" if m <= 5 else "D3+"


def reconciliation():
    """Our database against the Lead's authoritative counts (handover addendum C)."""
    q = lambda w: scalar(f"SELECT COUNT(*) FROM materials WHERE {w}")
    return [
        ("All BoM materials", q("1=1"), 7481, "tier table"),
        ("Never issued (class D0)", q("COALESCE(months_with_demand,0) = 0"), 5551, "no recorded consumption"),
        ("Issued at least once", q("months_with_demand >= 1"), 1930, "classes D1 to D4"),
        ("Sparse, 1 to 2 months (D1)", q("months_with_demand BETWEEN 1 AND 2"), 1475, "abstain from forecast"),
        ("Thin, 3 to 5 months (D2)", q("months_with_demand BETWEEN 3 AND 5"), 159, "rate range only"),
        ("Forecast eligible, 6+ months", q("months_with_demand >= 6"), 296, "forecast output"),
        ("Simulation population T3", q(T3_SQL), 665, "policy comparison"),
        ("Grade A: proposed parameters", q(GRADE_A_SQL), 228, "D-24"),
    ]


def search_parts(args: dict, page=1, per_page=50):
    where, params = [], []
    for f in FILTERS:
        if args.get(f):
            where.append(f"{f} = ?")
            params.append(args[f])
    for flag in ("below_min", "min_below_ltd", "nonstock_issued", "idle_stock_item"):
        if args.get(flag):
            where.append(f"material IN (SELECT material FROM material_flags WHERE {flag} = 1)")
    if args.get("abnormal"):
        where.append("material IN (SELECT material FROM material_flags WHERE abnormal_months > 0)")
    if args.get("reorder_soon"):
        where.append("material IN (SELECT material FROM material_flags WHERE days_to_reorder > 0 AND days_to_reorder <= 30)")
    if args.get("category"):
        where.append("material IN (SELECT b.material FROM raw_bom b JOIN equipment e ON e.funcloc = b.funcloc WHERE e.category = ?)")
        params.append(args["category"])
    if args.get("excess_any"):
        where.append("excess_qty > 0")
    if args.get("eng_reorder"):
        where.append("action = 'REORDER'")
    if args.get("grade_a"):
        where.append(GRADE_A_SQL)
    if args.get("critical_empty"):
        where.append("criticality IN ('A','S') AND stock = 0 AND forecast_monthly > 0")
    if args.get("q"):
        where.append("(description LIKE ? OR material LIKE ?)")
        params += [f"%{args['q']}%", f"%{args['q']}%"]
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = scalar(f"SELECT COUNT(*) FROM materials {w}", params)
    order = SORTS.get(args.get("sort"), SORTS["risk"])
    col = SORT_COL.get(args.get("sort"))
    if col and args.get("dir") in ("asc", "desc"):   # header menu: explicit direction, empty values always last
        order = f"{col} IS NULL, {col} {args['dir'].upper()}, material"
    items = rows(f"""SELECT material, description, unit, criticality, mrp_type, stock, min_qty, max_qty, rec_min, rec_max,
                            forecast_monthly, demand_class, p_stockout, stockout_risk, health, action, action_qty,
                            stock_value_idr, excess_value_idr, excess_qty, value_outlier, mrp_recommendation, last_issue,
                            (SELECT s_point IS NOT NULL FROM eng_primary e WHERE e.material = materials.material) has_prop,
                            (SELECT quantity FROM raw_movement v WHERE v.material = materials.material ORDER BY posting_date DESC LIMIT 1) last_qty,
                            (SELECT order_no FROM raw_movement v WHERE v.material = materials.material ORDER BY posting_date DESC LIMIT 1) last_order
                     FROM materials {w} ORDER BY {order} LIMIT ? OFFSET ?""", params + [per_page, (page - 1) * per_page])
    return total, items


def part_detail(material: str):
    p = one("SELECT * FROM materials WHERE material=?", (material,))
    if not p:
        return None
    p["monthly"] = rows("SELECT month, quantity FROM monthly_demand WHERE material=? ORDER BY month", (material,))
    p["lead_lines"] = scalar("SELECT COUNT(*) FROM raw_pr_po WHERE material=? AND lead_time_days IS NOT NULL", (material,)) or 0
    p["evidence"] = "strong" if (p.get("months_with_demand") or 0) >= 6 and p["lead_lines"] >= 10 else "weak"
    p["t3"] = bool(scalar(f"SELECT COUNT(*) FROM materials WHERE material=? AND {T3_SQL}", (material,)))
    p["grade"] = ("A" if (p.get("months_with_demand") or 0) >= 6 else "B") if p["t3"] else None
    p["dclass"] = demand_class(p.get("months_with_demand"))
    p["rop_levels"] = rows("SELECT service_level, reorder_point FROM rop_by_service_level WHERE material=? ORDER BY service_level", (material,))
    p["locations"] = rows("""SELECT b.funcloc, f.description, f.criticality, b.installed_qty,
                                    (SELECT COUNT(*) FROM raw_notification n WHERE n.funcloc=b.funcloc AND n.notif_type='N2') breakdowns,
                                    (SELECT COUNT(*) FROM raw_notification n WHERE n.funcloc=b.funcloc) notifs
                             FROM raw_bom b LEFT JOIN raw_funcloc f ON f.funcloc=b.funcloc
                             WHERE b.material=? ORDER BY CASE f.criticality WHEN 'A' THEN 1 WHEN 'S' THEN 2 WHEN 'B' THEN 3 WHEN 'C' THEN 4 ELSE 5 END,
                                      breakdowns DESC LIMIT 25""", (material,))
    p["supply"] = one("""SELECT COUNT(DISTINCT po) pos, COUNT(*) lines, COALESCE(SUM(quantity), 0) qty, MIN(pr_date) first_pr, MAX(pr_date) last_pr
                         FROM raw_pr_po WHERE material=?""", (material,))
    p["eq_cats"] = rows("""SELECT e.category, COUNT(*) n, SUM(e.n_emergency) emergency, MAX(e.drawing) drawing,
                                  (SELECT b2.funcloc FROM raw_bom b2 JOIN equipment e2 ON e2.funcloc=b2.funcloc
                                   WHERE b2.material=? AND e2.category=e.category ORDER BY e2.drawing IS NULL, e2.n_emergency DESC LIMIT 1) example
                           FROM raw_bom b JOIN equipment e ON e.funcloc = b.funcloc WHERE b.material=?
                           GROUP BY e.category ORDER BY n DESC LIMIT 4""", (material, material))
    p["issues"] = rows("SELECT posting_date, quantity, order_no FROM raw_movement WHERE material=? ORDER BY posting_date DESC LIMIT 15", (material,))
    p["purchases"] = rows("""SELECT pr_date, quantity, po_delivery_date, pr_delivery_date, lead_time_days, late_days, unit_price,
                                    currency, unit_price_idr, supplier_name FROM raw_pr_po WHERE material=? ORDER BY pr_date DESC LIMIT 15""", (material,))
    return p


def assumptions():
    return rows("SELECT * FROM assumptions")


def data_quality():
    return rows("SELECT * FROM data_quality")


def table_counts():
    names = [r["name"] for r in rows("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return [{"table": n, "rows": scalar(f'SELECT COUNT(*) FROM "{n}"')} for n in names]


# ---------------- INSpire Command Center (Feature Spec 3.1)
@lru_cache(maxsize=1)
def command_kpis():
    return {r["key"]: r for r in rows("SELECT * FROM kpi")}


def flags(material):
    return one("SELECT * FROM material_flags WHERE material = ?", (material,)) or {}


def definitions():
    return rows("SELECT * FROM definitions")


FLAG_FILTERS = {"below_min": "below_min", "min_below_ltd": "min_below_ltd", "nonstock_issued": "nonstock_issued", "idle_stock_item": "idle_stock_item"}

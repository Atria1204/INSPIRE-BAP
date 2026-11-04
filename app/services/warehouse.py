"""Warehouse digital twin (building view): every part in use, one simulated year, current vs recommended Min/Max.

The building is drawn as storage zones, one per equipment family the parts serve. Each day of the simulated year we
count, per zone, how many parts are out of stock (a job would wait). Same random days for both policies
(common random numbers), so the difference is the policy, not luck. One replication: it is a picture of a
typical year; Policy Lab gives the confidence intervals per part.
"""
import math
import random
from functools import lru_cache

from .. import db

ZONES = [  # zone name, equipment categories it serves (from build_context.py)
    ("Rotating equipment", ["Pump", "Motor", "Compressor", "Fan and blower"]),
    ("Valves", ["Control valve", "Safety valve"]),
    ("Instruments and electrical", ["Instrument", "Electrical and I/O"]),
    ("Heat transfer and furnace", ["Heat exchanger", "Furnace"]),
    ("Static and piping", ["Piping", "Vessel and column", "Civil structure", "Site system", "Other equipment"]),
]
DAYS = 365
HISTORY_DAYS = 518


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


@lru_cache(maxsize=1)
def _zone_map():
    """Every BoM part -> the zone holding most of its installed locations."""
    zone_of_cat = {c: z for z, cats in ZONES for c in cats}
    main = {}
    for r in db.rows("""SELECT b.material, e.category, COUNT(*) n FROM raw_bom b JOIN equipment e ON e.funcloc=b.funcloc
                        GROUP BY b.material, e.category ORDER BY b.material, n DESC"""):
        main.setdefault(r["material"], zone_of_cat.get(r["category"], ZONES[-1][0]))
    return main


@lru_cache(maxsize=1)
def _parts():
    """Parts in use with their main zone (the zone holding most of their installed locations)."""
    zone_of_cat = {c: z for z, cats in ZONES for c in cats}
    main = {}
    for r in db.rows("""SELECT b.material, e.category, COUNT(*) n FROM raw_bom b JOIN equipment e ON e.funcloc=b.funcloc
                        GROUP BY b.material, e.category ORDER BY b.material, n DESC"""):
        main.setdefault(r["material"], zone_of_cat.get(r["category"], ZONES[-1][0]))
    parts = db.rows("""SELECT material, description, criticality, stock, min_qty, max_qty, rec_min, rec_max, lead_time_days,
                              lead_time_std_days, health, stockout_risk, action, stock_value_idr, value_outlier
                       FROM materials WHERE n_issues > 0""")
    sizes, lts = {}, {}
    for r in db.rows("SELECT material, quantity FROM raw_movement"):
        sizes.setdefault(r["material"], []).append(r["quantity"])
    for r in db.rows("SELECT material, lead_time_days FROM raw_pr_po WHERE lead_time_days IS NOT NULL"):
        lts.setdefault(r["material"], []).append(r["lead_time_days"])
    for p in parts:
        p["zone"] = main.get(p["material"], ZONES[-1][0])
        p["sizes"], p["lts"] = sizes.get(p["material"], [1]), lts.get(p["material"], [])
    return parts


def _run(p, mn, mx, demands, lead_times, trace=None):
    on_hand, back, pipe, short = p["stock"], 0.0, [], []
    it = iter(lead_times)
    for day in range(DAYS):
        arrived = sum(q for d, q in pipe if d == day)
        if trace is not None and arrived:
            trace["recv"][day] += 1
        if arrived:
            pipe = [(d, q) for d, q in pipe if d != day]
            on_hand += arrived
            use = min(on_hand, back)
            on_hand -= use
            back -= use
        for s in demands[day]:
            take = min(on_hand, s)
            if trace is not None and take > 0:
                trace["issue"][day] += 1
            on_hand -= take
            back += s - take
        pos = on_hand + sum(q for _, q in pipe) - back
        if pos <= mn and mx - pos > 0:
            pipe.append((day + max(1, round(next(it, lead_times[-1]))), mx - pos))
        short.append(back > 0)
    return short


@lru_cache(maxsize=1)
def simulate():
    rng = random.Random(2026)
    zones = {z: {"zone": z, "parts": 0, "critical": 0, "short_now": [0] * DAYS, "short_rec": [0] * DAYS,
                 "health": {}, "value": 0.0,
                 "flow_now": {"recv": [0] * DAYS, "issue": [0] * DAYS}, "flow_rec": {"recv": [0] * DAYS, "issue": [0] * DAYS}} for z, _ in ZONES}
    worst = []
    for p in _parts():
        rate = len(p["sizes"]) / HISTORY_DAYS
        demands = [[rng.choice(p["sizes"]) for _ in range(_poisson(rng, rate))] for _ in range(DAYS)]
        lead_times = [rng.choice(p["lts"]) if p["lts"] else max(1.0, rng.gauss(p["lead_time_days"], p["lead_time_std_days"] or 1))
                      for _ in range(400)]
        z = zones[p["zone"]]
        a = _run(p, p["min_qty"], p["max_qty"], demands, lead_times, z["flow_now"])
        b = _run(p, p["rec_min"], p["rec_max"], demands, lead_times, z["flow_rec"])
        z["parts"] += 1
        z["critical"] += p["criticality"] in ("A", "S")
        z["health"][p["health"]] = z["health"].get(p["health"], 0) + 1
        if not p["value_outlier"]:
            z["value"] += p["stock_value_idr"] or 0
        for d in range(DAYS):
            z["short_now"][d] += a[d]
            z["short_rec"][d] += b[d]
        worst.append({"material": p["material"], "description": p["description"], "zone": p["zone"], "criticality": p["criticality"],
                      "days_now": sum(a), "days_rec": sum(b)})
    out = list(zones.values())
    for z in out:
        z["avg_now"] = sum(z["short_now"]) / DAYS
        z["avg_rec"] = sum(z["short_rec"]) / DAYS
    worst.sort(key=lambda w: -(w["days_now"] - w["days_rec"]))
    tot_now = [sum(z["short_now"][d] for z in out) for d in range(DAYS)]
    tot_rec = [sum(z["short_rec"][d] for z in out) for d in range(DAYS)]
    supply = db.one("""SELECT COUNT(DISTINCT supplier_code) suppliers, COUNT(DISTINCT po) pos, ROUND(AVG(late_days > 0), 3) late_share,
                              ROUND(AVG(lead_time_days), 0) avg_lt FROM raw_pr_po""")
    issues = db.one("SELECT COUNT(*) n, COUNT(DISTINCT order_no) orders FROM raw_movement")
    return {"zones": out, "total_now": tot_now, "total_rec": tot_rec, "avg_now": sum(tot_now) / DAYS, "avg_rec": sum(tot_rec) / DAYS,
            "parts": sum(z["parts"] for z in out), "most_improved": worst[:12], "supply": supply, "issues": issues}


ZONE_OF_CATEGORY = {c: z for z, cats in ZONES for c in cats}


@lru_cache(maxsize=1)
def site():
    """Everything the Site twin page needs: zone details, gauges, recent events (real records)."""
    sim = simulate()
    by_zone = {z["zone"]: z for z in sim["zones"]}
    for p in _parts():
        z = by_zone[p["zone"]]
        z.setdefault("high", 0)
        z.setdefault("below_rop", 0)
        z.setdefault("excess", 0.0)
        z.setdefault("crit_covered", 0)
        z.setdefault("top", [])
        z["high"] += p["stockout_risk"] == "HIGH"
        z["below_rop"] += p["stock"] <= p["rec_min"]
        if p["criticality"] in ("A", "S") and p["stock"] >= p["rec_min"]:
            z["crit_covered"] += 1
    for r in db.rows("""SELECT material, description, criticality, stock, rec_min, rec_max, p_stockout, action, excess_value_idr, value_outlier
                        FROM materials WHERE n_issues > 0 ORDER BY p_stockout DESC"""):
        p = next((x for x in _parts() if x["material"] == r["material"]), None)
        if p:
            z = by_zone[p["zone"]]
            if len(z["top"]) < 6 and r["criticality"] in ("A", "S"):
                z["top"].append(r)
    zmap = _zone_map()   # capital above Max over ALL parts, same rule as the Overview card (REDUCE + NO_ACTION_EVIDENCE)
    for r in db.rows("SELECT material_no material FROM eng_health_flags WHERE flag_stock_above_recorded_max = 1"):   # engine flag, a count
        z = by_zone.get(zmap.get(r["material"], ZONES[-1][0]))
        if z:
            z["excess"] += 1
    for z in sim["zones"]:
        z["cats"] = dict(ZONES)[z["zone"]]
    used = sim["parts"]
    in_stock = sum(1 for p in _parts() if p["stock"] > 0)
    crit = [p for p in _parts() if p["criticality"] in ("A", "S")]
    gauges = {
        "available": in_stock / used,
        "critical_covered": sum(1 for p in crit if p["stock"] >= p["rec_min"]) / max(1, len(crit)),
        "healthy_value": 1 - (db.scalar("SELECT SUM(excess_value_idr) FROM materials WHERE value_outlier=0") or 0)
                         / (db.scalar("SELECT SUM(stock_value_idr) FROM materials WHERE value_outlier=0") or 1),
    }
    from .kpi import overview
    return {**sim, "gauges": gauges, "events": events(), "monthly": overview()["monthly_consumption"]}


def events(limit=14):
    """Most recent records in the data (Sep 2026), as an event feed. Every row is a real source record."""
    ev = []
    for r in db.rows("""SELECT n.notif_date d, n.funcloc, n.description, n.priority, e.category FROM raw_notification n
                        LEFT JOIN equipment e ON e.funcloc = n.funcloc WHERE n.notif_type='N2' ORDER BY n.notif_date DESC LIMIT 4"""):
        ev.append({"date": r["d"], "kind": "crit", "icon": "fa-triangle-exclamation", "title": "Emergency notification",
                   "on": f"{r['funcloc']} · {r['description']}", "link": f"/equipment/{r['funcloc']}", "zone": ZONE_OF_CATEGORY.get(r["category"], "")})
    for r in db.rows("""SELECT p.pr_date d, p.material, m.description, p.late_days, p.supplier_name FROM raw_pr_po p JOIN materials m ON m.material=p.material
                        WHERE p.late_days > 14 ORDER BY p.pr_date DESC LIMIT 4"""):
        ev.append({"date": r["d"], "kind": "warn", "icon": "fa-truck", "title": f"Delivery promised {int(r['late_days'])} days after requested",
                   "on": f"{r['material']} · {r['description']} · {r['supplier_name']}", "link": f"/parts/{r['material']}", "zone": ""})
    for r in db.rows("""SELECT v.posting_date d, v.material, m.description, v.quantity, m.unit, m.stock, m.criticality FROM raw_movement v
                        JOIN materials m ON m.material=v.material WHERE m.stock = 0 AND m.criticality IN ('A','S')
                        ORDER BY v.posting_date DESC LIMIT 3"""):
        ev.append({"date": r["d"], "kind": "crit", "icon": "fa-box-open", "title": f"Last {r['quantity']:g} {r['unit']} issued, stock now 0",
                   "on": f"{r['material']} · {r['description']} · class {r['criticality']}", "link": f"/parts/{r['material']}", "zone": ""})
    for r in db.rows("""SELECT f.abnormal_last_month d, f.material, m.description, f.abnormal_peak_qty, f.abnormal_typical_qty, m.unit FROM material_flags f
                        JOIN materials m ON m.material=f.material WHERE f.abnormal_months > 0 ORDER BY f.abnormal_last_month DESC LIMIT 3"""):
        ev.append({"date": r["d"] + "-28", "kind": "info", "icon": "fa-chart-line", "title": f"Abnormal use: {r['abnormal_peak_qty']:g} {r['unit']} in a month (typical {r['abnormal_typical_qty']:g})",
                   "on": f"{r['material']} · {r['description']}", "link": f"/parts/{r['material']}", "zone": ""})
    ev.sort(key=lambda e: e["date"], reverse=True)
    return ev[:limit]

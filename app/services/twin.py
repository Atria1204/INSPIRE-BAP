"""Warehouse digital twin: a discrete-event simulation of one part's stock for one year,
comparing the CURRENT min-max policy with the RECOMMENDED one.

Method (modul PEMSI):
- Banks & Carson, Discrete-Event System Simulation, Example 2.8 (inventory system simulation).
- Law, Simulation Modeling and Analysis: common random numbers (both policies see the same demand
  and lead times in each run) and output analysis with a 95% confidence interval over replications.

Daily logic:
1. A replenishment order arrives if its lead time has passed.
2. Demand happens: issues per day ~ Poisson(issues per day in history), each issue size drawn from this part's history.
   Stock serves what it can; the rest is a shortage (backordered, served when stock arrives).
3. Review: if inventory position (on hand + on order - backorders) <= Min, order up to Max.
   Lead time drawn from this part's own purchase history.
A Non Stock part (min = max = 0) therefore behaves as "buy only when a job needs it".
"""
import math
import random
import statistics

from ..db import one, rows

HOLDING_RATE = 0.25
ORDER_COST = 750_000
HISTORY_DAYS = 518          # 1 May 2025 to 1 Oct 2026


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def _run(policy_min, policy_max, start, days, demands, lead_times):
    """One replication. demands: list per day of issue sizes; lead_times: iterator of lead times."""
    on_hand, backorder, pipeline = start, 0.0, []     # pipeline: [(arrival_day, qty)]
    demand_qty = served_qty = 0.0
    short_events = orders = 0
    on_hand_sum = 0.0
    path = []
    lt_iter = iter(lead_times)
    for day in range(days):
        arrived = sum(q for d, q in pipeline if d == day)
        if arrived:
            pipeline = [(d, q) for d, q in pipeline if d != day]
            on_hand += arrived
            use = min(on_hand, backorder)
            on_hand -= use
            backorder -= use
        for size in demands[day]:
            demand_qty += size
            take = min(on_hand, size)
            on_hand -= take
            served_qty += take
            if take < size:
                backorder += size - take
                short_events += 1
        position = on_hand + sum(q for _, q in pipeline) - backorder
        if position <= policy_min and policy_max - position > 0:
            qty = policy_max - position
            lt = next(lt_iter)
            pipeline.append((day + max(1, round(lt)), qty))
            orders += 1
        on_hand_sum += on_hand
        path.append(on_hand - backorder)
    return {
        "fill_rate": served_qty / demand_qty if demand_qty else 1.0,
        "short_events": short_events, "orders": orders,
        "avg_on_hand": on_hand_sum / days, "demand": demand_qty, "path": path,
    }


def _ci(values):
    m = statistics.fmean(values)
    if len(values) < 2:
        return {"mean": m, "low": m, "high": m}
    h = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return {"mean": m, "low": m - h, "high": m + h}


def simulate(material: str, reps: int = 200, days: int = 365, seed: int = 2026,
             custom_min: float | None = None, custom_max: float | None = None,
             lt_mult: float = 1.0, expedite_days: float | None = None, expedite_premium: float = 0.0) -> dict | None:
    """lt_mult stretches every promised lead time (stress test). expedite_days / expedite_premium add an
    'Expedite' policy: recommended min/max, every order arrives in expedite_days and costs the premium extra.
    Both are user-entered SCENARIO inputs (INSpire Logistics Lab, 'Expedite or wait')."""
    p = one("SELECT * FROM materials WHERE material=?", (material,))
    if not p:
        return None
    sizes = [r["quantity"] for r in rows("SELECT quantity FROM raw_movement WHERE material=?", (material,))]
    lts = [r["lead_time_days"] for r in rows("SELECT lead_time_days FROM raw_pr_po WHERE material=? AND lead_time_days IS NOT NULL", (material,))]
    price = p["unit_price_idr"] or 0
    if not price:
        price = p["stock_value_idr"] / p["stock"] if p["stock"] else 0
    rate = len(sizes) / HISTORY_DAYS
    policies = {"current": (p["min_qty"], p["max_qty"]), "recommended": (p["rec_min"], p["rec_max"])}
    if custom_min is not None and custom_max is not None:
        policies["custom"] = (custom_min, custom_max)
    if expedite_days:
        policies["expedite"] = (p["rec_min"], p["rec_max"])

    rng = random.Random(seed)
    results = {k: [] for k in policies}
    for _ in range(reps):
        # common random numbers: the same demand stream and lead times for every policy in this run
        demands = [[rng.choice(sizes) for _ in range(_poisson(rng, rate))] if sizes else [] for _ in range(days)]
        lead_times = [lt_mult * (rng.choice(lts) if lts else max(1.0, rng.gauss(p["lead_time_days"], p["lead_time_std_days"] or 1))) for _ in range(400)]
        for k, (mn, mx) in policies.items():
            lt_k = [expedite_days] * len(lead_times) if k == "expedite" else lead_times
            results[k].append(_run(mn, mx, p["stock"], days, demands, lt_k))

    out = {"material": material, "description": p["description"], "unit": p["unit"], "reps": reps, "days": days,
           "lt_mult": lt_mult, "expedite_days": expedite_days, "expedite_premium": expedite_premium,
           "price": price, "price_source": p["price_source"], "start_stock": p["stock"], "policies": {}}
    for k, runs in results.items():
        mn, mx = policies[k]
        holding = [r["avg_on_hand"] * price * HOLDING_RATE for r in runs]
        ordering = [r["orders"] * (ORDER_COST + (expedite_premium if k == "expedite" else 0)) for r in runs]
        out["policies"][k] = {
            "min": mn, "max": mx,
            "fill_rate": _ci([r["fill_rate"] for r in runs]),
            "short_events": _ci([r["short_events"] for r in runs]),
            "orders": _ci([r["orders"] for r in runs]),
            "avg_on_hand": _ci([r["avg_on_hand"] for r in runs]),
            "inventory_value": _ci([r["avg_on_hand"] * price for r in runs]),
            "holding_cost": _ci(holding),
            "ordering_cost": _ci(ordering),
            "total_cost": _ci([h + o for h, o in zip(holding, ordering)]),
            "runs_with_shortage": sum(1 for r in runs if r["short_events"] > 0) / reps,
            "sample_path": runs[0]["path"],
        }
    return out

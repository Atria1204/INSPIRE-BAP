"""Cost-risk scenario: change the target service level per class and see the effect on the whole warehouse.

Reorder points at each service level were pre-computed by the Monte Carlo lead-time-demand simulation
(table rop_by_service_level), so this page only looks them up. Approximations used:
- average inventory under the policy ~ safety stock + half the order quantity
- holding cost = average inventory value x 25% per year
"""
import math
from functools import lru_cache

from ..db import rows

LEVELS = [0.80, 0.85, 0.90, 0.95, 0.975, 0.99, 0.995]
BASE = {"A": 0.99, "S": 0.975, "B": 0.95, "C": 0.90, "-": 0.90}
HOLDING_RATE = 0.25


@lru_cache(maxsize=1)
def _data():
    parts = {r["material"]: r for r in rows("""
        SELECT material, criticality, stock, unit_price_idr, stock_value_idr, eoq, lead_time_demand_mean, forecast_monthly,
               value_outlier, min_qty, max_qty
        FROM materials WHERE forecast_monthly > 0""")}
    for r in rows("SELECT material, service_level, reorder_point FROM rop_by_service_level"):
        if r["material"] in parts:
            parts[r["material"]].setdefault("rop", {})[round(r["service_level"], 3)] = r["reorder_point"]
    return parts


def _nearest(level):
    return min(LEVELS, key=lambda x: abs(x - level))


def run(levels: dict) -> dict:
    """levels: {"A": 0.99, "S": 0.975, "B": 0.95, "C": 0.9}. Returns warehouse totals for parts with demand."""
    t = {"parts": 0, "target_inventory_value": 0.0, "holding_cost": 0.0, "buy_now_value": 0.0, "buy_now_parts": 0,
         "free_value": 0.0, "free_parts": 0, "current_value": 0.0, "current_holding": 0.0,
         "expected_stockouts_per_cycle": 0.0}
    by_class = {}
    for p in _data().values():
        if p["value_outlier"] or "rop" not in p:
            continue
        crit = p["criticality"] or "-"
        sl = _nearest(levels.get(crit, BASE.get(crit, 0.9)))
        rop = p["rop"].get(sl, 0)
        price = p["unit_price_idr"] or (p["stock_value_idr"] / p["stock"] if p["stock"] else 0)
        rec_min = math.ceil(rop)
        rec_max = rec_min + max(1, math.ceil(p["eoq"] or 0))
        safety = max(0.0, rop - (p["lead_time_demand_mean"] or 0))
        avg_inv = safety + (rec_max - rec_min) / 2
        stock = p["stock"]
        t["parts"] += 1
        t["target_inventory_value"] += avg_inv * price
        t["holding_cost"] += avg_inv * price * HOLDING_RATE
        t["current_value"] += stock * price
        t["current_holding"] += stock * price * HOLDING_RATE
        t["expected_stockouts_per_cycle"] += 1 - sl
        if stock <= rec_min:
            t["buy_now_parts"] += 1
            t["buy_now_value"] += (rec_max - stock) * price
        elif stock > rec_max:
            t["free_parts"] += 1
            t["free_value"] += (stock - rec_max) * price
        c = by_class.setdefault(crit, {"class": crit, "service_level": sl, "parts": 0, "target_value": 0.0, "buy_now": 0})
        c["parts"] += 1
        c["target_value"] += avg_inv * price
        c["buy_now"] += int(stock <= rec_min)
    t["by_class"] = sorted(by_class.values(), key=lambda c: "ASBC-".index(c["class"]) if c["class"] in "ASBC-" else 9)
    t["levels"] = {k: _nearest(v) for k, v in levels.items()}
    return t


def presets():
    """Three ready-made scenarios for the comparison table."""
    lean = {"A": 0.95, "S": 0.95, "B": 0.90, "C": 0.80}
    high = {"A": 0.995, "S": 0.99, "B": 0.975, "C": 0.95}
    return [{"name": "Lean", "levels": lean, **run(lean)},
            {"name": "Recommended", "levels": BASE, **run(BASE)},
            {"name": "High availability", "levels": high, **run(high)}]

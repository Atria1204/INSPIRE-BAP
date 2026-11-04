"""Equipment Explorer (INSpire Feature Spec 3.2): category > location > drawing components > installed parts.

Equipment categories and component placement are PROPOSED rules (pipeline/build_context.py) inferred from the
functional-location tag, its description and the part description. They are shown with that caveat.
"""
from functools import lru_cache

from .. import db

DRAWING_TITLE = {"pump": "Centrifugal pump", "motorpump": "Electric motor driving a pump", "compressor": "Centrifugal compressor",
                 "exchanger": "Shell and tube heat exchanger", "blower": "Fan or blower"}


@lru_cache(maxsize=1)
def categories():
    return db.rows("""
        SELECT e.category, COUNT(DISTINCT e.funcloc) locations, MAX(e.drawing) drawing,
               COUNT(DISTINCT b.material) parts,
               COUNT(DISTINCT CASE WHEN m.action = 'REORDER' THEN b.material END) reorder_parts,
               COUNT(DISTINCT CASE WHEN m.stockout_risk = 'HIGH' THEN b.material END) high_risk_parts,
               (SELECT SUM(n_emergency) FROM equipment e2 WHERE e2.category = e.category) emergency
        FROM equipment e LEFT JOIN raw_bom b ON b.funcloc = e.funcloc LEFT JOIN materials m ON m.material = b.material
        GROUP BY e.category ORDER BY reorder_parts DESC""")


@lru_cache(maxsize=1)
def featured():
    """One location per drawing type: the one with the most parts to reorder. Shown as live drawings on the Equipment twin page."""
    out = []
    for d in DRAWING_TITLE:
        r = db.one("""SELECT e.funcloc, (SELECT COUNT(DISTINCT b.material) FROM raw_bom b JOIN materials m ON m.material=b.material
                                         WHERE b.funcloc=e.funcloc AND m.action='REORDER') reorder_parts
                      FROM equipment e WHERE e.drawing = ? ORDER BY reorder_parts DESC, e.n_emergency DESC, e.n_materials DESC LIMIT 1""", (d,))
        if r:
            e = location(r["funcloc"])
            out.append({k: e[k] for k in ("funcloc", "description", "category", "criticality", "drawing", "title", "hotspots", "n_emergency")}
                       | {"reorder_parts": r["reorder_parts"], "n_parts": len(e["parts"])})
    return out


def locations(category=None, q=None, page=1, per_page=40):
    where, params = [], []
    if category:
        where.append("e.category = ?")
        params.append(category)
    if q:
        where.append("(e.funcloc LIKE ? OR e.description LIKE ?)")
        params += [f"%{q}%"] * 2
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.scalar(f"SELECT COUNT(*) FROM equipment e {w}", params)
    items = db.rows(f"""SELECT e.*, (SELECT COUNT(DISTINCT b.material) FROM raw_bom b JOIN materials m ON m.material=b.material
                                     WHERE b.funcloc=e.funcloc AND m.action='REORDER') reorder_parts
                        FROM equipment e {w}
                        ORDER BY reorder_parts DESC, e.n_emergency DESC, e.n_materials DESC LIMIT ? OFFSET ?""",
                    params + [per_page, (page - 1) * per_page])
    return total, items


def location(funcloc):
    e = db.one("SELECT * FROM equipment WHERE funcloc = ?", (funcloc,))
    if not e:
        return None
    e["title"] = DRAWING_TITLE.get(e["drawing"], "")
    e["parts"] = db.rows("""
        SELECT b.material, b.installed_qty, m.description, m.unit, m.stock, m.min_qty, m.max_qty, m.rec_min, m.rec_max,
               (SELECT ep.s_point IS NOT NULL FROM eng_primary ep WHERE ep.material = b.material) has_prop,
               m.mrp_type, m.action, m.p_stockout, m.stockout_risk, m.forecast_monthly, c.component,
               COALESCE(h.hotspot, 'other') hotspot
        FROM raw_bom b JOIN materials m ON m.material = b.material
        LEFT JOIN material_component c ON c.material = b.material
        LEFT JOIN hotspot_map h ON h.drawing = ? AND h.component = c.component
        WHERE b.funcloc = ?
        ORDER BY CASE m.action WHEN 'REORDER' THEN 1 WHEN 'NO_ACTION_EVIDENCE' THEN 2 WHEN 'REDUCE' THEN 3 WHEN 'MONITOR' THEN 4 ELSE 5 END,
                 m.p_stockout DESC""", (e["drawing"], funcloc))
    e["notifications"] = db.rows("""SELECT notif_date, notification, notif_type, priority, description, status, order_no
                                    FROM raw_notification WHERE funcloc = ? ORDER BY notif_date DESC LIMIT 25""", (funcloc,))
    e["plan_items"] = db.rows("""SELECT item_text, cycle, cycle_start, abc, priority FROM raw_maintenance_plan
                                 WHERE funcloc = ? ORDER BY cycle_start DESC LIMIT 25""", (funcloc,))
    # same equipment family: the base tag (e.g. PX_PP-436A and its motor PX_PP-436A-M)
    base = funcloc.split("-M")[0] if funcloc.endswith("-M") else funcloc
    e["related"] = db.rows("SELECT funcloc, description, category FROM equipment WHERE funcloc != ? AND funcloc LIKE ? LIMIT 8",
                           (funcloc, base + "%"))
    hs = {}
    for p in e["parts"]:
        h = hs.setdefault(p["hotspot"], {"parts": 0, "reorder": 0})
        h["parts"] += 1
        h["reorder"] += p["action"] == "REORDER"
    e["hotspots"] = hs
    return e


def where_installed(material, limit=40):
    return db.rows("""SELECT e.funcloc, e.description, e.category, e.criticality, e.drawing, e.n_emergency, b.installed_qty
                      FROM raw_bom b JOIN equipment e ON e.funcloc = b.funcloc WHERE b.material = ?
                      ORDER BY e.drawing IS NULL, e.n_emergency DESC LIMIT ?""", (material, limit))

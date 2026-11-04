"""Pages and JSON API. Screen names follow the INSpire Feature Specification (Part 4)."""
from urllib.parse import quote

from flask import Blueprint, abort, jsonify, redirect, render_template, request

from . import db
from .services import actions, assistant, equipment, kpi, scenario, twin, warehouse

bp = Blueprint("main", __name__)


def _page():
    return max(1, int(request.args.get("page", 1) or 1))


def _per():
    try:
        n = int(request.args.get("per", 20))
    except ValueError:
        n = 20
    return n if n in (20, 50, 100) else 20


# ---------------- Command Center
@bp.get("/")
def site_twin():
    reorder_cls = db.rows("""SELECT m.criticality c, COUNT(*) n FROM proposed_actions a JOIN materials m ON m.material = a.material
                             WHERE a.type = 'Reorder' GROUP BY 1 ORDER BY CASE m.criticality WHEN 'A' THEN 1 WHEN 'S' THEN 2 WHEN 'B' THEN 3 WHEN 'C' THEN 4 ELSE 5 END""")
    return render_template("site.html", s=warehouse.site(), k=kpi.overview(), e=kpi.engine(), acts=actions.summary(), risk=kpi.top_risk()[:5], reorder_cls=reorder_cls,
                           page="site", ai_context="Overview · whole site",
                           ai_suggestions=["Which storage zone needs attention first, and why?",
                                           "Explain the recent events in plain words",
                                           "Bagian gudang mana yang paling sering kehabisan part?"])


@bp.get("/exceptions")
def command_center():
    rules = []
    for key, sort in (("min_below_ltd", "risk"), ("below_min", "risk"), ("nonstock_issued", "forecast"), ("idle_stock_item", "value")):
        total, items = kpi.search_parts({key: 1, "sort": sort}, 1, 4)
        rules.append({"key": key, "total": total, "items": items})
    return render_template("command.html", k=kpi.overview(), ck=kpi.command_kpis(), rules=rules, page="command",
                           ai_context="Rule checks · INSpire exception rules")


# ---------------- Action Center
@bp.get("/actions")
def action_center():
    total, items = actions.search(request.args, _page(), _per())
    return render_template("actions.html", items=items, total=total, pg=_page(), per=_per(), s=actions.summary(), args=request.args,
                           types=actions.TYPES, statuses=actions.STATUSES, page="actions",
                           ai_context="Action Center", ai_suggestions=["Which proposed actions should we accept first and why?",
                                                                      "Summarise the Reduce actions"])


@bp.get("/actions/<action_id>")
def action_detail(action_id):
    a = actions.get(action_id)
    if not a:
        abort(404)
    return render_template("action.html", a=a, p=kpi.part_detail(a["material"]), eng=kpi.engine_part(a["material"]), page="actions", ai_material=a["material"],
                           ai_context=f"Action {action_id} · {a['type']} · part {a['material']}",
                           ai_suggestions=[f"Draft a justification for action {action_id} on part {a['material']}",
                                           f"What evidence is missing before closing the action on {a['material']}?"])


# ---------------- Equipment Explorer (digital twin of the equipment)
@bp.get("/equipment")
def equipment_explorer():
    cat = request.args.get("category")
    total, items = equipment.locations(cat, request.args.get("q"), _page(), _per())
    return render_template("equipment.html", cats=equipment.categories(), items=items, total=total, pg=_page(), per=_per(), featured=equipment.featured(),
                           cat=cat, args=request.args, page="equipment", ai_context=f"Equipment Explorer · {cat or 'all categories'}")


@bp.get("/equipment/<path:funcloc>")
def equipment_location(funcloc):
    e = equipment.location(funcloc)
    if not e:
        abort(404)
    return render_template("location.html", e=e, page="equipment", ai_context=f"Equipment {funcloc} · {e['description']}",
                           ai_suggestions=[f"Which parts installed on {funcloc} are at risk, and what should we do?",
                                           f"Summarise the notifications on {funcloc}"])


# ---------------- Inventory Intelligence and Material 360
@bp.get("/parts")
def inventory():
    total, items = kpi.search_parts(request.args, _page(), _per())
    qcounts = {k: kpi.search_parts({k: 1}, 1, 1)[0] for k in ("eng_reorder", "critical_empty", "excess_any", "abnormal", "grade_a")}
    return render_template("inventory.html", items=items, total=total, pg=_page(), per=_per(), opts=kpi.filter_options(), args=request.args, qcounts=qcounts,
                           cats=[c["category"] for c in equipment.categories() if c["parts"]], page="parts", ai_context="Inventory Intelligence")


@bp.get("/parts/<material>")
def material_360(material):
    p = kpi.part_detail(material)
    if not p:
        abort(404)
    return render_template("material.html", eng=kpi.engine_part(material), p=p, f=kpi.flags(material), installed=equipment.where_installed(material),
                           part_actions=actions.search({"material": material})[1], page="parts",
                           ai_material=material, ai_context=f"Material 360 · {material} · {p['description']}",
                           ai_suggestions=[f"Why is part {material} flagged, and what are the limits of the evidence?",
                                           f"What happens if we keep the current min–max for {material}?",
                                           f"Kenapa part {material} statusnya {p['action']}?"])


# ---------------- Policy Lab (digital twin of the warehouse)
@bp.get("/policy")
def policy_lab():
    material = request.args.get("material") or "4100014049"
    p = db.one("SELECT material, description, min_qty, max_qty, rec_min, rec_max, unit, lead_time_days FROM materials WHERE material=?", (material,))
    picks = db.rows("""SELECT material, description, action FROM materials WHERE n_issues >= 20
                       ORDER BY CASE stockout_risk WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END, n_issues DESC LIMIT 40""")
    d = kpi.part_detail(material) if p else None
    return render_template("policy.html", p=p, picks=picks, grade=d and d["grade"], eng=kpi.engine_part(material) if p else None, page="policy", ai_material=material,
                           ai_context=f"Policy Lab · part {material}",
                           ai_suggestions=[f"Explain the Policy Lab result for part {material} in plain words",
                                           "Is expediting worth it for this part?"])


@bp.get("/policy/warehouse")
def policy_warehouse():
    return render_template("warehouse.html", presets=scenario.presets(), base=scenario.BASE, levels=scenario.LEVELS, page="policy",
                           ai_context="Policy Lab · whole warehouse service levels")


# ---------------- Data Trust
@bp.get("/trust")
def data_trust():
    return render_template("trust.html", recon=kpi.reconciliation(), assumptions=kpi.assumptions(), quality=kpi.data_quality(), tables=kpi.table_counts(),
                           defs=kpi.definitions(), ck=kpi.command_kpis(), events=actions.recent_events(), ai_log=assistant.recent_log(), page="trust",
                           ai_context="Data Trust")


# ---------------- old addresses
@bp.get("/twin")
def old_twin_home():
    if request.args.get("material"):
        return redirect(f"/policy?material={request.args['material']}")
    return redirect("/")


@bp.get("/twin/replay")
def warehouse_twin():
    if request.args.get("material"):
        return redirect(f"/policy?material={request.args['material']}")
    return render_template("warehouse_twin.html", e=kpi.engine(), w=warehouse.simulate(), page="twin", ai_context="Warehouse twin · whole warehouse",
                           ai_suggestions=["Which storage zone gains most from the new Min/Max, and why?",
                                           "Which critical parts are out of stock most days under the current policy?"])


@bp.get("/scenario")
def old_scenario():
    return redirect("/policy/warehouse")


@bp.get("/method")
def old_method():
    return redirect("/trust")


@bp.get("/assistant")
def old_assistant():
    q = request.args.get("q", "")
    target = f"/parts/{request.args['material']}" if request.args.get("material") else "/"
    return redirect(f"{target}?ask={quote(q)}" if q else target)


# ---------------- JSON API
@bp.get("/api/health")
def health():
    return jsonify(status="ok", parts=kpi.overview()["parts"], ai="on" if assistant._client() else "offline")


@bp.get("/api/twin/<material>")
def api_twin(material):
    a = request.args
    r = twin.simulate(material, reps=min(300, a.get("reps", 200, type=int)), custom_min=a.get("min", type=float),
                      custom_max=a.get("max", type=float), lt_mult=a.get("lt_mult", 1.0, type=float),
                      expedite_days=a.get("exp_days", type=float), expedite_premium=a.get("exp_premium", 0.0, type=float))
    return jsonify(r) if r else (jsonify(error="unknown material"), 404)


@bp.post("/api/scenario")
def api_scenario():
    levels = {k: float(v) for k, v in (request.get_json(force=True) or {}).items() if k in ("A", "S", "B", "C")}
    return jsonify(scenario.run(levels))


@bp.post("/api/ask")
def api_ask():
    b = request.get_json(force=True) or {}
    q = (b.get("question") or "").strip()
    if not q:
        return jsonify(error="question is required"), 400
    return jsonify(assistant.ask(q, b.get("material") or None, b.get("page") or "", b.get("context") or ""))


@bp.post("/api/actions/<action_id>")
def api_action_move(action_id):
    b = request.get_json(force=True) or {}
    ok, msg = actions.move(action_id, b.get("to", ""), (b.get("actor") or "").strip(), b.get("role", ""),
                           (b.get("reason") or "").strip(), (b.get("owner") or "").strip(), b.get("due_date", ""),
                           (b.get("evidence") or "").strip())
    return jsonify(ok=ok, message=msg, action=actions.get(action_id)), (200 if ok else 400)

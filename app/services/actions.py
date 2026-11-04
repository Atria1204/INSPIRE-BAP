"""Action Center (INSpire Feature Spec 3.7).

Proposed actions come from the rules (table proposed_actions, read-only). People move them on; every move is an
event in the writable decisions database, so the full history is the audit trail.

Status model (team handover section 8): Generated -> Under review -> Approved, Rejected or Deferred.
After approval the work is tracked: In progress -> Done -> Verified closed. Approval means "accept this candidate for
the planner's own use", nothing changes in an ERP. Reject and defer need a reason; approving a part without Grade A
evidence needs a reason too. The verifier must be a different person from the owner.
"""
from datetime import date

from .. import db

FLOW = {
    "Generated": ["Under review"],
    "Under review": ["Approved", "Rejected", "Deferred"],
    "Deferred": ["Under review"],
    "Approved": ["In progress", "Rejected"],
    "In progress": ["Done"],
    "Done": ["Verified closed", "In progress"],
    "Rejected": [],
    "Verified closed": [],
}
STATUSES = ["Generated", "Under review", "Approved", "In progress", "Done", "Verified closed", "Deferred", "Rejected"]
LEGACY = {"Proposed": "Generated", "Accepted": "Approved", "Dismissed": "Rejected"}   # events logged before the rename
TYPES = ["Reorder", "Reduce", "Maintain"]


def _events_db():
    con = db.decisions_db()
    con.execute("""CREATE TABLE IF NOT EXISTS action_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT, status TEXT, actor TEXT, role TEXT, reason TEXT,
        owner TEXT, due_date TEXT, evidence TEXT, at TEXT DEFAULT (datetime('now')))""")
    return con


def _state():
    """Latest status, owner and due date per action, from the event log."""
    st = {}
    for e in _events_db().execute("SELECT * FROM action_events ORDER BY id"):
        e = dict(e)
        s = st.setdefault(e["action_id"], {"status": "Generated", "owner": "", "due_date": "", "events": 0})
        s["status"] = LEGACY.get(e["status"], e["status"])
        s["events"] += 1
        if e["owner"]:
            s["owner"] = e["owner"]
        if e["due_date"]:
            s["due_date"] = e["due_date"]
    return st


def summary():
    st = _state()
    counts = {s: 0 for s in STATUSES}
    total = db.scalar("SELECT COUNT(*) FROM proposed_actions")
    for v in st.values():
        counts[v["status"]] += 1
    counts["Generated"] = total - sum(v for k, v in counts.items() if k != "Generated")
    today = date.today().isoformat()
    overdue = sum(1 for v in st.values() if v["status"] in ("Approved", "In progress") and v["due_date"] and v["due_date"] < today)
    by_type = db.rows("SELECT type, COUNT(*) n FROM proposed_actions GROUP BY type ORDER BY n DESC")
    return {"total": total, "counts": counts, "overdue": overdue, "by_type": by_type}


def search(args, page=1, per_page=50):
    st = _state()
    where, params = [], []
    if args.get("type"):
        where.append("a.type = ?")
        params.append(args["type"])
    if args.get("criticality"):
        where.append("m.criticality = ?")
        params.append(args["criticality"])
    if args.get("material"):
        where.append("a.material = ?")
        params.append(args["material"])
    if args.get("q"):
        where.append("(m.description LIKE ? OR a.material LIKE ?)")
        params += [f"%{args['q']}%"] * 2
    w = ("WHERE " + " AND ".join(where)) if where else ""
    items = db.rows(f"""SELECT a.*, m.description, m.criticality, m.unit, m.stock, m.rec_min, m.rec_max, m.p_stockout,
                               m.excess_value_idr, m.action AS part_action
                        FROM proposed_actions a JOIN materials m ON m.material = a.material {w}
                        ORDER BY CASE a.type WHEN 'Reorder' THEN 1 WHEN 'Reduce' THEN 2 ELSE 3 END,
                                 m.p_stockout DESC, m.excess_value_idr DESC""", params)
    for it in items:
        it.update(st.get(it["action_id"], {"status": "Generated", "owner": "", "due_date": "", "events": 0}))
    if args.get("status"):
        items = [i for i in items if i["status"] == args["status"]]
    total = len(items)
    return total, items[(page - 1) * per_page: page * per_page]


def get(action_id):
    a = db.one("""SELECT a.*, m.description, m.criticality, m.unit, m.stock, m.rec_min, m.rec_max, m.action AS part_action
                  FROM proposed_actions a JOIN materials m ON m.material = a.material WHERE a.action_id = ?""", (action_id,))
    if not a:
        return None
    a.update(_state().get(action_id, {"status": "Generated", "owner": "", "due_date": "", "events": 0}))
    a["history"] = [dict(e) for e in _events_db().execute("SELECT * FROM action_events WHERE action_id=? ORDER BY id", (action_id,))]
    a["next"] = FLOW[a["status"]]
    return a


def move(action_id, to, actor, role, reason="", owner="", due_date="", evidence=""):
    """Validate and record a status change. Returns (ok, message)."""
    a = get(action_id)
    if not a:
        return False, "Unknown action."
    if to not in a["next"]:
        return False, f"An action in '{a['status']}' cannot move to '{to}'."
    if not actor:
        return False, "Your name is required."
    if to in ("Rejected", "Deferred") and not reason:
        return False, f"{to} needs a reason."
    if to == "Approved" and not (owner and due_date):
        return False, "Approving needs an owner and a due date."
    if to == "Approved" and not reason:
        from .kpi import GRADE_A_SQL
        if not db.scalar(f"SELECT COUNT(*) FROM materials WHERE material=? AND {GRADE_A_SQL}", (a["material"],)):
            return False, "This part has no Grade A evidence: approving it needs a reason."
    if to == "Done" and not evidence:
        return False, "Marking done needs closure evidence (for example the PR or PO number)."
    if to == "Verified closed" and actor.strip().lower() == (a["owner"] or "").strip().lower():
        return False, "The verifier must be a different person from the owner."
    with _events_db() as con:
        con.execute("""INSERT INTO action_events (action_id, status, actor, role, reason, owner, due_date, evidence)
                       VALUES (?,?,?,?,?,?,?,?)""", (action_id, to, actor, role, reason, owner, due_date, evidence))
    return True, f"Moved to {to}."


def recent_events(limit=30):
    return [dict(e) for e in _events_db().execute("SELECT * FROM action_events ORDER BY id DESC LIMIT ?", (limit,))]

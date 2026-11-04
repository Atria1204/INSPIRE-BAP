"""Database access. The SQLite file is the source of truth and is opened READ-ONLY
(works on Vercel, where the deployed files cannot be written).

Human decisions (approve / reject a recommendation) go to a separate small database:
data/decisions.db locally, /tmp/decisions.db on Vercel (temporary there: it resets when the server restarts).
"""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("AETHER_DB", ROOT / "data" / "aether_spare.db"))
DECISIONS_PATH = Path("/tmp/decisions.db") if os.getenv("VERCEL") else ROOT / "data" / "decisions.db"


def connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro&immutable=1", uri=True, check_same_thread=False)


_con = None


def db() -> sqlite3.Connection:
    global _con
    if _con is None:
        _con = connect()
    return _con


def rows(sql: str, params=()) -> list[dict]:
    cur = db().cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description] if cur.description else []
    res = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return res


def one(sql: str, params=()) -> dict | None:
    cur = db().cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description] if cur.description else []
    r = cur.fetchone()
    cur.close()
    return dict(zip(cols, r)) if r else None


def scalar(sql: str, params=()):
    cur = db().cursor()
    cur.execute(sql, params)
    r = cur.fetchone()
    cur.close()
    return r[0] if r else None


# ---------------- human decisions (HV: AETHER recommends, a named person decides)
def decisions_db() -> sqlite3.Connection:
    con = sqlite3.connect(DECISIONS_PATH, check_same_thread=False)
    con.execute("""CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, material TEXT, recommended_action TEXT, decision TEXT,
        decided_by TEXT, role TEXT, reason TEXT, decided_at TEXT DEFAULT (datetime('now')))""")
    return con


def add_decision(material, recommended_action, decision, decided_by, role, reason):
    with decisions_db() as con:
        con.execute("INSERT INTO decisions (material, recommended_action, decision, decided_by, role, reason) VALUES (?,?,?,?,?,?)",
                    (material, recommended_action, decision, decided_by, role, reason))


def decisions_for(material=None, limit=50):
    con = decisions_db()
    cur = con.cursor()
    if material:
        cur.execute("SELECT * FROM decisions WHERE material=? ORDER BY id DESC LIMIT ?", (material, limit))
    else:
        cur.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))
    cols = [c[0] for c in cur.description] if cur.description else []
    res = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return res

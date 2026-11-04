"""AETHER Spare: spare part intelligence and inventory optimization (CALIBER 2026 final case).
Flask monolith: SQLite (read-only source of truth) + simulation + Gemini assistant."""
from pathlib import Path

from flask import Flask

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def _idr(v, short=True):
    """IDR 397.9 B / IDR 2.0 M (short, tables) or IDR 397.9 billion (long, headline numbers).
    B = billion (miliar), M = million (juta)."""
    if v is None:
        return "-"
    if short:
        for div, suf in ((1e12, " T"), (1e9, " B"), (1e6, " M")):
            if abs(v) >= div:
                return f"IDR {v / div:,.1f}{suf}"
        return f"IDR {v:,.0f}"
    for div, suf in ((1e12, " trillion"), (1e9, " billion"), (1e6, " million")):
        if abs(v) >= div:
            return f"IDR {v / div:,.1f}{suf}"
    return f"IDR {v:,.0f}"


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    HEALTH_LABEL = {"dead stock": "potentially obsolete candidate", "non-moving": "non-moving by recorded issues",
                    "slow-moving": "slow-moving by recorded issues"}
    app.jinja_env.filters["hlabel"] = lambda v: HEALTH_LABEL.get(v, v)
    ACTION_LABEL = {"REORDER": "Reorder", "REDUCE": "Reduce", "HOLD": "Maintain", "MONITOR": "Monitor", "NO_ACTION_EVIDENCE": "No action: thin evidence"}
    app.jinja_env.filters["alabel"] = lambda v: ACTION_LABEL.get(v, v)

    def _rate(f):   # 14.24 -> "14 / month", 0.25 -> "1 every 4 months"
        if f is None:
            return "no forecast"
        if f <= 0:
            return "not used"
        if f >= 1:
            return f"{round(f):,} / month"
        return f"1 every {round(1 / f)} months"
    app.jinja_env.filters["rate"] = _rate
    app.jinja_env.filters["idr"] = _idr
    app.jinja_env.filters["idr_long"] = lambda v: _idr(v, short=False)
    app.jinja_env.filters["pct"] = lambda v, d=0: "-" if v is None else f"{v * 100:.{d}f}%"
    app.jinja_env.filters["num"] = lambda v, d=0: "-" if v is None else (f"{v:,.{d}f}" if isinstance(v, (int, float)) else v)
    from .provenance import SOURCES
    app.jinja_env.globals["SOURCES"] = SOURCES
    @app.context_processor
    def _nav():
        from .services import actions, kpi
        k = kpi.overview()
        return {"nav": {"high_risk": k["high_risk"], "parts": k["parts"], "proposed": actions.summary()["counts"]["Generated"]}}

    from .routes import bp
    app.register_blueprint(bp)
    return app

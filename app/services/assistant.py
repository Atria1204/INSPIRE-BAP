"""AI assistant over the SQLite source of truth (retrieval-augmented generation).

1. Retrieve: warehouse KPIs + parts matching the question (material numbers, words in the description,
   or the intent: reorder / reduce / review / risk / supplier ...).
2. Gemini answers ONLY from that context and cites material numbers.
3. Guardrails: rules compute, AI explains, a person decides. No invented numbers.
Without GEMINI_API_KEY it returns the retrieved rows (offline mode).
"""
import json
import os
import re
from functools import lru_cache

from ..db import rows
from .kpi import overview

CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite")
FALLBACKS = [m.strip() for m in os.getenv("GEMINI_CHAT_FALLBACKS", "gemini-3.1-flash-lite,gemini-3.5-flash,gemini-flash-latest").split(",") if m.strip()]

SYSTEM = """You are INSpire Copilot, a colleague who helps spare-part planners at Chandra Asri read the INSpire results.

How to sound
- Talk like an experienced planner explaining to a colleague: plain, warm, direct. No preamble ("Here is a summary"), no filler,
  no headings. Answer the question in the first sentence, then give only the reasons that matter.
- Answer in the language of the question. In Indonesian, use natural everyday business Indonesian, not a translation.
- Short: 2 to 5 sentences, or up to 5 short bullets when you list parts. Use bullets only for a list of parts.
- Mention the whole-warehouse totals in SUMMARY only when the question is about totals or asks for insight about the page.
- For "insight", "kesimpulan", "ringkasan" or "what should I look at" on the Overview: give 3 short insights, each one sentence:
  where the risk is (shortfall risk and the Act first parts), what to do (the engine actions), and how sure we are
  (only 228 of 7,481 parts have enough evidence; the held-out test and its trade-off). Then name at most 3 parts to open first.
- Use the SUMMARY labels exactly; for example "class A/S parts in use with zero stock" is not "empty stock".
- Plain text, no tables, no LaTeX. Write 93% and IDR 2.0 M.

What you may say
- Only facts in the DATA. If the DATA does not hold the answer, say so in one sentence and point to the page or filter that would.
- Name each part by its number and short name, e.g. 4100000203 (bearing 6305). Never invent a number, date, price or supplier.
- Recommendations, s/S/Q and shortfall probabilities come from the team engine (run RUN-277fc4b966e6). Explain them; never change them.
  Actions: Reorder, Maintain, Reduce, Monitor, No action (too little evidence). They are candidates a person approves.
- Say how sure we are in everyday words: "strong evidence" for grade A, "thin evidence" otherwise.
- Words: shortfalls are "simulated", lead times are "promised", today's stock and Min/Max are "recorded". Never "optimal",
  "saving" or "actual stockout".
- When you suggest acting, end with who decides, in the language of the question, e.g. "Planner yang menyetujuinya di Action Center."
- Never repeat a part as a bullet after you already explained it in a sentence. Use bullets only for two or more parts.
- Last line, on its own: "Source: engine run RUN-277fc4b966e6, scenario A/ED, <strong|thin> evidence, synthetic data." """

FIELDS = """material, description, unit, criticality, mrp_type, stock, min_qty, max_qty, rec_min, rec_max, forecast_monthly,
            demand_class, lead_time_days, late_share, p_stockout, stockout_risk, health, action, action_qty, action_reason,
            stock_value_idr, excess_value_idr, mrp_recommendation, main_supplier, price_source,
            CASE WHEN mrp_type = 'Stock Item' AND n_issues > 0 AND lead_time_source = 'material'
                      AND (COALESCE(min_qty,0) > 0 OR COALESCE(max_qty,0) > 0)
                 THEN CASE WHEN months_with_demand >= 6 THEN 'A' ELSE 'B' END ELSE 'outside T3' END evidence_grade"""

INTENTS = [
    (r"reorder|order|pesan|beli|stockout|kehabisan|habis|kosong|risk|risiko|urgent|critical|kritis", "action='REORDER'", "p_stockout DESC"),
    (r"reduce|excess|berlebih|kurangi|dead|mati|obsolete|usang|free|bebas|capital|modal", "action IN ('REDUCE','NO_ACTION_EVIDENCE')", "excess_value_idr DESC"),
    (r"review|insurance|asuransi|cadangan", "action='NO_ACTION_EVIDENCE'", "excess_value_idr DESC"),
    (r"non.?stock|status|mrp", "mrp_recommendation<>'Keep'", "issues_12m DESC"),
    (r"slow|lambat|non.?moving", "health IN ('slow-moving','non-moving')", "stock_value_idr DESC"),
    (r"abnormal|anomal|spike|lonjak|aneh|unusual|tidak wajar",
     "material IN (SELECT material FROM material_flags WHERE abnormal_months > 0)", "stock_value_idr DESC"),
    (r"when|kapan|reorder by|soon|segera|next month|bulan depan",
     "material IN (SELECT material FROM material_flags WHERE days_to_reorder > 0 AND days_to_reorder <= 30)", "p_stockout DESC"),
]
STOP = set("the a an of and or to in on for is are what which how why who with part parts spare yang dan di ke dari untuk apa mana "
           "berapa ini itu ada saja kita harus minggu bulan please show list give me".split())


@lru_cache(maxsize=1)
def _client():
    key = os.getenv("GEMINI_API_KEY")
    if not key or os.getenv("ALLOW_EXTERNAL_LLM", "1") == "0":   # D-07 answered by the team: allowed, stored facts only
        return None
    try:
        from google import genai
        from google.genai import types
        http = types.HttpOptions(timeout=20_000, retry_options=types.HttpRetryOptions(attempts=1))
        return genai.Client(api_key=key, http_options=http), types
    except Exception as e:
        print("[assistant] Gemini disabled:", e)
        return None


def _generate(prompt):
    client, types = _client()
    last = None
    for model in [CHAT_MODEL] + [m for m in FALLBACKS if m != CHAT_MODEL]:
        try:
            r = client.models.generate_content(model=model, contents=prompt,
                                               config=types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.2))
            return r.text or "", model
        except Exception as e:
            if not any(c in str(e) for c in ("503", "504", "500", "429", "404", "UNAVAILABLE", "DEADLINE", "timed out")):
                raise
            last = e
    raise last or RuntimeError("no Gemini model available")


def retrieve(question: str, material: str | None = None) -> dict:
    q = question.lower()
    found, seen = [], set()

    def add(items, why):
        for it in items:
            if it["material"] not in seen and len(found) < 25:
                seen.add(it["material"])
                found.append({**it, "matched_by": why})

    ids = set(re.findall(r"\b4\d{9}\b", question)) | ({material} if material else set())
    if ids:
        add(rows(f"SELECT {FIELDS} FROM materials WHERE material IN ({','.join('?' * len(ids))})", list(ids)), "material number")
    for pattern, where, order in INTENTS:
        if re.search(pattern, q):
            add(rows(f"SELECT {FIELDS} FROM materials WHERE {where} AND value_outlier=0 ORDER BY {order} LIMIT 8"), f"intent: {where}")
    words = [w for w in re.findall(r"[a-z0-9\-]{3,}", q) if w not in STOP and not w.isdigit()]
    for w in words[:4]:
        add(rows(f"SELECT {FIELDS} FROM materials WHERE description LIKE ? ORDER BY p_stockout DESC, stock_value_idr DESC LIMIT 5",
                 (f"%{w.upper()}%",)), f"description contains {w.upper()}")
    if not found:
        add(rows(f"SELECT {FIELDS} FROM materials WHERE stockout_risk='HIGH' ORDER BY p_stockout DESC LIMIT 6"), "top stockout risk")

    if found:
        fl = {r["material"]: r for r in rows(
            f"SELECT material, abnormal_months, abnormal_last_month, abnormal_peak_qty, abnormal_typical_qty, days_to_reorder, reorder_by "
            f"FROM material_flags WHERE material IN ({','.join('?' * len(found))})", [p["material"] for p in found])}
        for p in found:
            f = fl.get(p["material"], {})
            p["reorder_by"] = f.get("reorder_by")
            p["days_to_reorder"] = f.get("days_to_reorder")
            if f.get("abnormal_months"):
                p["abnormal_use"] = (f"{f['abnormal_months']} month(s) far above normal, latest {f['abnormal_last_month']}: "
                                     f"{f['abnormal_peak_qty']:g} vs typical {f['abnormal_typical_qty']:g}")

    if found:   # engine facts are the only source of model numbers (handover 7)
        for p in found[:8]:
            p["engine_facts"] = {r["fact_key"]: (r["value"] + (" " + r["unit"] if r["unit"] else "")) for r in rows(
                "SELECT fact_key, value, unit FROM eng_explanation_facts WHERE material_no=? AND (scenario_id LIKE 'SC-A-ED%' OR scenario_id LIKE 'SC-ALL%') LIMIT 30",
                (p["material"],))}
    k = overview()
    from .kpi import engine
    e = engine()
    summary = {   # labelled so the model cannot mix them up
        "parts_total": k["parts"], "parts_never_issued": k["never_used"], "stock_as_of": k["as_of"],
        "recorded_stock_value_idr_excluding_outliers": k["stock_value_clean"],
        "grade_a_parts_with_proposed_parameters": e["params"],
        "engine_actions": {"reorder": e["reorder"], "reduce": e["reduce"], "maintain": e["hold"], "monitor": e["monitor"], "no_action_thin_evidence": e["noact"]},
        "simulated_shortfall_risk_grade_a": {"high": e["high"], "medium": e["medium"], "low": e["low"]},
        "class_a_or_s_parts_in_use_with_zero_stock": k["critical_empty"],
        "health_flags": {"above_recorded_max": e["above_max"], "slow_moving": e["slow"], "non_moving": e["non_moving"], "potentially_obsolete_candidate": e["obsolete"]},
        "held_out_test_parts_with_a_shortage_of_197": {"recorded_min_max": int(e["ho"]["R0"]["n"]), "x2_95_percent": int(e["ho"]["X2"]["n"])},
        "trade_off": "fewer simulated shortages come with 1.56 to 2.58 times more stock on hand",
    }
    suppliers = rows("SELECT supplier_name, n_po, median_lead_time, ROUND(late_share,2) late_share FROM suppliers ORDER BY late_share DESC LIMIT 5") \
        if re.search(r"supplier|vendor|pemasok|late|telat|lead", q) else []
    return {"summary": summary, "parts": found, "suppliers_latest": suppliers}


def _log(question, material, r):
    """assistant_log, as the team handover asks: question, facts quoted, answer, timestamp."""
    from ..db import decisions_db
    try:
        with decisions_db() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS assistant_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT DEFAULT (datetime('now')),
                           question TEXT, material TEXT, mode TEXT, parts_used TEXT, answer TEXT, run_id TEXT)""")
            con.execute("INSERT INTO assistant_log (question, material, mode, parts_used, answer, run_id) VALUES (?,?,?,?,?,?)",
                        (question, material, r.get("mode"), ",".join(s["material"] for s in r.get("sources", [])), r.get("answer"), "RUN-277fc4b966e6"))
    except Exception as e:
        print("[assistant] log failed:", e)
    return r


def recent_log(limit=20):
    from ..db import decisions_db
    con = decisions_db()
    if not con.execute("SELECT name FROM sqlite_master WHERE name='assistant_log'").fetchone():
        return []
    return [dict(r) for r in con.execute("SELECT * FROM assistant_log ORDER BY id DESC LIMIT ?", (limit,))]


APP_GUIDE = """INSpire pages (left sidebar, 8 pages in 4 groups, plus the part page and the action page):
DAILY WORK
1. Overview (/): four engine cards (shortfall risk, recommended actions, evidence first 228 of 7,481, held-out test 48 to 23),
   Act first (5 Reorder candidates), site twin 3D with zones. Start of the day.
2. Parts (/parts): all 7,481 parts in one table. Search, quick views, every column title sorts and filters, 20 rows a page.
   Part page (/parts/<number>): one part. Recommendation with reason and limitations, stock vs Min/Max, X1/X2/X3,
   simulated shortfall, held-out result, part twin 3D, history tabs, facts and evidence. Decide opens the action.
3. Action Center (/actions): the 228 engine candidates (114 Reorder, 66 Reduce, 48 Maintain). A person moves each one:
   Under review, Approved (owner and due date) or Rejected or Deferred (reason), In progress, Done (PR or PO number),
   Verified by a second person. Every step is logged.
SIMULATE
4. Warehouse replay (/twin/replay): engine held-out test for six policies (recorded 48, X2 23 of 197 parts with a shortage),
   then the app's illustrative replay of every part in use, biggest gains, by zone.
5. Policy Lab (/policy): test one part. Engine result first, then replay it with your own Min/Max, a longer lead time or an
   expedite. Whole-warehouse scenarios (/policy/warehouse): change the service target per class A/S/B/C for all parts
   (illustrative money, cost set not approved).
EQUIPMENT
6. Equipment twin (/equipment): 14,484 functional locations; 2D drawings of pumps, motors, compressors, exchangers, fans with
   the parts installed on each component; red = a part to reorder. Click a machine to open its twin.
DATA CHECKS
7. Rule checks (/exceptions): four stock rules applied to every part (Min below lead-time demand, issued Stock Items below Min,
   Non Stock parts that were used, idle Stock Items) with the worst parts of each. Finds data and setting problems.
8. Data Trust (/trust): where every number comes from, counts that match the team pipeline (8 of 8), data quality, open
   definition questions, assumptions, decision log and the Copilot log. Shows why the numbers can be trusted.
Copilot (this chat): explains engine results and the app. It never changes a number and never approves.
Terms: X1, X2, X3 = proposed reorder levels at 90, 95, 98 percent; s = reorder point (new Min), S = order-up-to (new Max),
Q = order quantity. Grade A = enough evidence for proposed parameters (228 parts)."""
APP_Q = re.compile(r"halaman|\bpage\b|menu|sidebar|navigasi|fitur|feature|cara (pakai|guna|baca)|how (do|to|does)|gimana|bagaimana|"
                   r"untuk apa|buat apa|apa itu|what is|what does|jelaskan halaman|\bx1\b|\bx2\b|\bx3\b|grade a|action center|policy lab|"
                   r"replay|twin|data trust|rule check", re.I)


def _cached(question, material):
    from ..db import decisions_db
    try:
        con = decisions_db()
        if not con.execute("SELECT name FROM sqlite_master WHERE name='assistant_log'").fetchone():
            return None
        r = con.execute("""SELECT answer, mode, parts_used FROM assistant_log WHERE lower(trim(question)) = lower(trim(?))
                           AND COALESCE(material,'') = COALESCE(?, '') AND mode LIKE 'gemini%' AND at > datetime('now', '-1 day')
                           ORDER BY id DESC LIMIT 1""", (question, material)).fetchone()
        if r:
            parts = [x for x in (r["parts_used"] or "").split(",") if x]
            srcs = rows(f"SELECT material, description, action, '' matched_by FROM materials WHERE material IN ({','.join('?' * len(parts))})", parts) if parts else []
            return {"answer": r["answer"], "mode": r["mode"] + " · cached", "sources": srcs}
    except Exception:
        return None
    return None


def ask(question: str, material: str | None = None, page: str = "", context: str = "") -> dict:
    hit = None if APP_Q.search(question) else _cached(question, material)   # app questions depend on the page, never cached
    if hit:
        return hit
    return _log(question, material, _ask(question, material, page, context))


def _ask(question: str, material: str | None = None, page: str = "", context: str = "") -> dict:
    if APP_Q.search(question) and not re.search(r"\b4\d{9}\b", question):
        if _client() is None:
            return {"answer": APP_GUIDE, "mode": "rules only (app guide)", "sources": []}
        prompt = (f"APP GUIDE:\n{APP_GUIDE}\n\nTHE USER IS ON: {page} ({context})\n\nQUESTION about the app: {question}\n"
                  "Answer from the APP GUIDE only, like a colleague showing a new planner around. Short and concrete. "
                  "If they ask about 'this page', explain the page they are on. End with: Source: INSpire app guide.")
        try:
            text, model = _generate(prompt)
            return {"answer": text, "mode": f"gemini {model} · app guide", "sources": []}
        except Exception:
            return {"answer": APP_GUIDE, "mode": "rules only (app guide)", "sources": []}
    ctx = retrieve(question, material)
    sources = [{"material": p["material"], "description": p["description"], "action": p["action"], "matched_by": p["matched_by"]} for p in ctx["parts"]]
    if _client() is None:
        return {"answer": _rule_answer(ctx), "mode": "rules only (no GEMINI_API_KEY)", "sources": sources}
    prompt = (f"APP GUIDE (for questions about the app):\n{APP_GUIDE}\n\nTHE USER IS ON: {page} ({context})\n\n"
              f"DATA (JSON from the INSpire database):\n{json.dumps(ctx, ensure_ascii=False, default=str)}\n\nQUESTION: {question}")
    try:
        text, model = _generate(prompt)
        text = re.sub(r"\$([^$\n]{1,40})\$", r"\1", text).replace("\\%", "%")   # strip LaTeX such as $93\%$
        return {"answer": text, "mode": f"gemini {model}", "sources": sources}
    except Exception as e:
        print("[assistant] all Gemini models failed:", str(e)[:120])
        return {"answer": _rule_answer(ctx), "mode": "rules only (Gemini busy, answer built from the database)", "sources": sources}


def _rule_answer(ctx):
    """Deterministic answer when no AI is reachable: the retrieved records, summarised by the same rules."""
    s, parts = ctx["summary"], ctx["parts"][:8]
    head = (f"{s['high_risk']} parts have high stockout risk, {s['reorder']} need a reorder, "
            f"{s['reduce']} can be reduced and {s['review']} need an engineer review.")
    lines = [f"- {p['material']} {p['description']}: {p['action']}"
             + (f" {p['action_qty']:g} {p['unit']}" if p['action_qty'] else "") + f". {p['action_reason']}" for p in parts]
    return head + "\n\nMost relevant parts:\n" + "\n".join(lines) + "\n\nA planner makes the final decision."

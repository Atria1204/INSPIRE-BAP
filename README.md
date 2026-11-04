# INSpire · Spare Part Intelligence (team BAP, CALIBER 2026)

INSpire is an MVP for the final case, **Spare Part Intelligence & Inventory Optimization**. It is built on the AETHER design.
It reads the six case Excel files and builds one SQLite database. A Flask web app answers both key questions with that database:

- **KQ1, demand predictability.** Each part gets a demand pattern (Syntetos–Boylan ADI / CV²), a forecast (SES or SBA) and an abnormal-consumption flag.
- **KQ2, dynamic optimisation.** Each part gets a reorder point from a Monte Carlo of lead-time demand at the target service level of its class (A 99%, S 97.5%, B 95%, C 90%). EOQ then sets the recommended Min/Max. A "reorder by" date and an action (REORDER, REDUCE, REVIEW, MONITOR, MAINTAIN) follow. The trade-off is tested in a discrete-event simulation for one part or for the whole warehouse.

All data is synthetic, as provided by the committee. Every number in the UI has an info chip that names its source file, its columns and its formula.

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env          # optional: add GEMINI_API_KEY for the Copilot; without it the Copilot answers from rules
python run.py                 # http://localhost:5000
```

## Rebuild the database from the Excel files (optional)

The zip already contains `data/aether_spare.db`. To rebuild it:

```bash
pip install -r pipeline/requirements.txt
python pipeline/build_db.py     # reads data/raw/*.xlsx and writes data/aether_spare.db (about 1 minute)
python pipeline/export_csv.py   # optional CSV exports
```

## Pages

| Page | Address | What it answers |
|---|---|---|
| Site twin | `/` | Supplier gate → warehouse zones → plant: risk, capital and a one-year replay |
| Exceptions | `/exceptions` | What needs a decision today (INSpire KPIs) |
| Parts | `/parts`, `/parts/<material>` | Filter all 7,481 parts; Material 360 with the recommendation, its evidence and a flow twin |
| Action Center | `/actions` | Proposed actions → owner, due date, verification (stored in `data/decisions.db`) |
| Warehouse replay | `/twin/replay` | Whole warehouse, current vs recommended Min/Max over one simulated year |
| Equipment twin | `/equipment` | Functional locations, their BoM parts and an equipment drawing |
| Policy Lab | `/policy` | One part: what-if Min/Max, lead-time stress, expediting |
| Data Trust | `/trust` | Data-quality findings (DEF-01 … DEF-15) and the assumptions used |

## Structure

```
api/index.py         Vercel entry (WSGI app)
app/                 Flask app: routes, services (kpi, twin, warehouse, scenario, actions, assistant), templates, static
pipeline/            build_db.py (cleaning, forecast, Monte Carlo, EOQ) and build_context.py (equipment, flags, KPIs, actions)
data/aether_spare.db the database the app reads (read-only)
data/raw/            the six case Excel files
```

Key assumptions: the PO amount is a unit price; the rates are USD 18,000, EUR 20,600, SGD 14,000 and JPY 115; the order cost is IDR 750k; the holding cost is 25% a year; the stock date is 1 Oct 2026. Data Trust lists all of them.

## Alignment with the team data pipeline (final-caliber26-aetherxinspire)

| Team rule | In this app |
| --- | --- |
| Authoritative counts 7,481 / 5,551 / 1,930 / 1,475 / 159 / 296 / 665 / 228 | Recomputed from this database, all match (Data Trust, "Counts checked against the team data pipeline") |
| D-24 Grade A (228) gets proposed parameters | Material 360 evidence chip: Grade A "proposed candidate", Grade B and outside T3 "scenario-configured, low confidence". Parts quick view "Grade A evidence" |
| Handover 8 review states | Generated → Under review → Approved / Rejected / Deferred, then In progress → Done → Verified closed. Reject and defer need a reason; approving a non-Grade-A part needs a reason |
| D-07 no external LLM with project data | Assistant is rules-only by default. Gemini runs only when `ALLOW_EXTERNAL_LLM=1` and `GEMINI_API_KEY` are both set |
| D-07 no raw workbooks in the zip | `make_zip.py` skips `data/raw` |
| D-21 wording | "potentially obsolete", "non-moving by recorded issues", never "dead stock" on screen |
| Handover 9 data label and view | Topbar on every page: synthetic data, stock date, demand scenario A, PR PO one row per PR item |
| Handover 15 no invented routes or warehouses | Site twin labelled "Schematic, not a map: zones = equipment families" |

## Engine output (team run RUN-277fc4b966e6, contract 0.2)

`python pipeline/load_engine.py` copies the team engine files from `final-caliber26-aetherxinspire/data/processed/engine/`
into `eng_*` tables and makes every page read them: recommended action (Reorder 114, Reduce 66, Maintain 48, Monitor 4,595,
No action 2,658 for demand A, view ED), proposed s/S for the 228 Grade A parts only, simulated shortfall risk, health flags,
the 296 forecasts, the held-out test (48 → 23 of 197 parts with a shortage, recorded vs X2) and the assistant facts.
The app's earlier values are kept in `materials_app`. The twin and Warehouse replay charts remain the app's own illustrative replay.

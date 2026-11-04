"""Export tables of the database to CSV (opens directly in Excel).

    python pipeline/export_csv.py          ->  exports/  (3 files for the team: materials, monthly_demand, assumptions)
    python pipeline/export_csv.py --all    ->  exports/  (every table, including the cleaned raw files)

Encoding utf-8-sig so Excel shows the degree sign and other characters correctly.
"""
import csv
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "exports"
TEAM = ["materials", "monthly_demand", "assumptions"]

shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir()
con = sqlite3.connect(ROOT / "data" / "aether_spare.db")
all_tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
tables = all_tables if "--all" in sys.argv else TEAM
for t in tables:
    cur = con.execute(f'SELECT * FROM "{t}"')
    with open(OUT / f"{t}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([d[0] for d in cur.description])
        n = 0
        for row in cur:
            w.writerow(row)
            n += 1
    print(f"{t:24s} {n:>7,} rows -> exports/{t}.csv")

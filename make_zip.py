"""Build the submission zip: source code + SQLite database. Never includes .env (the API key) or local work files.

    python make_zip.py   ->  ../INSpire_BAP_source_and_db.zip
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "INSpire_BAP_source_and_db.zip"
SKIP_DIRS = {"__pycache__", ".vercel", ".impeccable", "belajar", "exports", ".git", "raw"}   # raw = the six source workbooks (D-07)
SKIP_FILES = {".env", "decisions.db", "aether_spare_next.db", "aether_spare_prev.db", "aether_spare_new.db", "exports.zip"}

n = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if p.is_dir() or any(part in SKIP_DIRS for part in rel.parts) or p.name in SKIP_FILES or p.suffix == ".pyc":
            continue
        z.write(p, Path("aether-spare") / rel)
        n += 1
    assert not any(i.filename.endswith("/.env") for i in z.infolist()), ".env must never be zipped"
print(f"{n} files -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")

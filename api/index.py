"""Vercel Serverless Entrypoint for BTC SCALPING AI Web Dashboard."""

import os
from pathlib import Path
import shutil
import sys

# Ensure repository root is in Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Handle Vercel's read-only serverless filesystem
tmp_data_dir = Path("/tmp/data")
try:
    tmp_data_dir.mkdir(parents=True, exist_ok=True)
    tmp_db = tmp_data_dir / "btc_scalping.db"
    orig_db = ROOT_DIR / "data" / "btc_scalping.db"

    if orig_db.exists() and not tmp_db.exists():
        shutil.copy2(orig_db, tmp_db)

    os.environ["DATABASE_PATH"] = str(tmp_db)
except Exception:
    pass

from dashboard.app import app

# Vercel WSGI entrypoint
if __name__ == "__main__":
    app.run()

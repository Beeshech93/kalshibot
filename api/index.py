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
if os.getenv("VERCEL") or not os.access(str(ROOT_DIR / "data"), os.W_OK):
    tmp_data_dir = Path("/tmp/data")
    tmp_data_dir.mkdir(parents=True, exist_ok=True)
    tmp_db = tmp_data_dir / "btc_scalping.db"
    orig_db = ROOT_DIR / "data" / "btc_scalping.db"

    if not tmp_db.exists() and orig_db.exists():
        try:
            shutil.copy2(orig_db, tmp_db)
        except Exception:
            pass

    os.environ["DATABASE_PATH"] = str(tmp_db)

from dashboard.app import app

# Vercel WSGI entrypoint
if __name__ == "__main__":
    app.run()

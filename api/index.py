"""Vercel Serverless Entrypoint for BTC SCALPING AI Web Dashboard."""

import os
from pathlib import Path
import shutil
import sys
import traceback

# Ensure both api/ and root directory are in Python path
API_DIR = Path(__file__).resolve().parent
ROOT_DIR = API_DIR.parent

for p in [str(API_DIR), str(ROOT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Handle Vercel serverless writable environment in /tmp
os.environ["VERCEL"] = "1"
tmp_data_dir = Path("/tmp/data")
tmp_logs_dir = Path("/tmp/logs")

try:
    tmp_data_dir.mkdir(parents=True, exist_ok=True)
    tmp_logs_dir.mkdir(parents=True, exist_ok=True)
    tmp_db = tmp_data_dir / "btc_scalping.db"

    # Search for initial seed database
    for cand in [API_DIR / "data" / "btc_scalping.db", ROOT_DIR / "data" / "btc_scalping.db"]:
        if cand.exists() and not tmp_db.exists():
            try:
                shutil.copy2(cand, tmp_db)
                break
            except Exception:
                pass

    os.environ["DATABASE_PATH"] = str(tmp_db)
except Exception:
    pass

# Load Flask WSGI application
try:
    from dashboard.app import app
except Exception:
    try:
        from api.dashboard.app import app
    except Exception:
        from flask import Flask
        app = Flask(__name__)
        err_tb = traceback.format_exc()

        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def diagnostic_fallback(path):
            return (
                f"<!DOCTYPE html>"
                f"<html><head><title>Diagnóstico Vercel - BTC SCALPING AI</title>"
                f"<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
                f"<style>"
                f"body {{ background: #0d1117; color: #c9d1d9; font-family: monospace; padding: 25px; margin: 0; }}"
                f".box {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; max-width: 900px; margin: 0 auto; }}"
                f"h2 {{ color: #f85149; margin-top: 0; }}"
                f"pre {{ background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 15px; color: #ff7b72; font-size: 13px; overflow-x: auto; white-space: pre-wrap; }}"
                f"</style></head><body>"
                f"<div class='box'>"
                f"<h2>⚠️ Diagnóstico de Inicialización en Vercel</h2>"
                f"<pre>{err_tb}</pre>"
                f"</div></body></html>",
                200,
                {"Content-Type": "text/html; charset=utf-8"}
            )

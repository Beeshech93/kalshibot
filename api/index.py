"""Vercel Serverless Entrypoint for BTC SCALPING AI Web Dashboard."""

import os
from pathlib import Path
import shutil
import sys
import traceback

# Ensure repository root is in Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Handle Vercel serverless environment
os.environ["VERCEL"] = "1"
tmp_data_dir = Path("/tmp/data")
tmp_logs_dir = Path("/tmp/logs")

try:
    tmp_data_dir.mkdir(parents=True, exist_ok=True)
    tmp_logs_dir.mkdir(parents=True, exist_ok=True)
    tmp_db = tmp_data_dir / "btc_scalping.db"
    orig_db = ROOT_DIR / "data" / "btc_scalping.db"

    if orig_db.exists() and not tmp_db.exists():
        shutil.copy2(orig_db, tmp_db)

    os.environ["DATABASE_PATH"] = str(tmp_db)
except Exception:
    pass

# Attempt to load the Flask application
try:
    from dashboard.app import app
except Exception as e:
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
            f"body {{ background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, monospace; padding: 25px; margin: 0; }}"
            f".box {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; max-width: 900px; margin: 0 auto; }}"
            f"h2 {{ color: #f85149; margin-top: 0; }}"
            f"pre {{ background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 15px; color: #ff7b72; font-size: 13px; overflow-x: auto; white-space: pre-wrap; }}"
            f"</style></head><body>"
            f"<div class='box'>"
            f"<h2>⚠️ Error al Iniciar en Vercel (Diagnóstico Automático)</h2>"
            f"<p>La aplicación no pudo cargar debido a una excepción durante la importación:</p>"
            f"<pre>{err_tb}</pre>"
            f"</div></body></html>",
            200,
            {"Content-Type": "text/html; charset=utf-8"}
        )

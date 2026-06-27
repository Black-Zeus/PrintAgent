"""
Portal HTTP local del agente.
Corre en localhost:8765 (configurable) y expone:
  GET  /           → Dashboard de estado
  GET  /config     → Formulario de configuración
  POST /config     → Guardar configuración
  POST /test-print → Imprimir ticket de prueba
  GET  /api/status → JSON de estado (para integraciones)
"""
import logging
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

import config_manager
import poller
import printer as printer_module

logger = logging.getLogger("agent.portal")

TEMPLATES_DIR = Path(__file__).parent / "templates"
app = Flask(__name__, template_folder=str(TEMPLATES_DIR))
app.secret_key = "cecichic-print-agent-local"


@app.route("/")
def dashboard():
    cfg = config_manager.load()
    s = poller.state
    available_printers = printer_module.list_printers()
    return render_template(
        "index.html",
        state=s,
        cfg=cfg,
        available_printers=available_printers,
    )


@app.route("/config", methods=["GET"])
def config_page():
    cfg = config_manager.load()
    available_printers = printer_module.list_printers()
    return render_template("config.html", cfg=cfg, available_printers=available_printers, saved=False)


@app.route("/config", methods=["POST"])
def config_save():
    cfg = config_manager.load()
    cfg["server_url"] = request.form.get("server_url", "").strip().rstrip("/")
    cfg["printer_api_key"] = request.form.get("printer_api_key", "").strip()
    cfg["printer_name"] = request.form.get("printer_name", "auto").strip()
    cfg["portal_port"] = int(request.form.get("portal_port", 8765))
    cfg["poll_interval_seconds"] = max(1, int(request.form.get("poll_interval_seconds", 2)))
    config_manager.save(cfg)
    logger.info("Configuración guardada desde portal")
    available_printers = printer_module.list_printers()
    return render_template("config.html", cfg=cfg, available_printers=available_printers, saved=True)


@app.route("/test-print", methods=["POST"])
def test_print():
    result = poller.print_test()
    s = poller.state
    cfg = config_manager.load()
    available_printers = printer_module.list_printers()
    return render_template(
        "index.html",
        state=s,
        cfg=cfg,
        available_printers=available_printers,
        test_result=result,
    )


@app.route("/api/status")
def api_status():
    return jsonify({
        "agent": "CeciChic Print Agent",
        "state": poller.state,
        "config": {
            "server_url": config_manager.get("server_url"),
            "printer_name": config_manager.get("printer_name"),
            "poll_interval_seconds": config_manager.get("poll_interval_seconds"),
        },
    })


def run(port: int = 8765, debug: bool = False) -> None:
    logger.info("Portal iniciado en http://localhost:%d", port)
    app.run(host="127.0.0.1", port=port, debug=debug, use_reloader=False)

"""
Portal HTTP local del agente.
Corre en localhost:80 (configurable) y expone:
  GET  /           → Dashboard de estado
  GET  /config     → Formulario de configuración
  POST /config     → Guardar configuración
  POST /test-print → Imprimir ticket de prueba
  GET  /api/status → JSON de estado (para integraciones)
"""
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

import config_manager
import db
import modules
import poller
import printer as printer_module
import station
import template_manager

logger = logging.getLogger("agent.portal")

AGENT_VERSION = "1.0.0"

TEMPLATES_DIR = Path(__file__).parent / "templates"
app = Flask(__name__, template_folder=str(TEMPLATES_DIR))
app.secret_key = "gestioncom-print-agent-local"
app.config["TEMPLATES_AUTO_RELOAD"] = True

db.init()


@app.template_filter("clp")
def clp_filter(value):
    try:
        return f"$ {int(float(str(value or 0))):,}".replace(",", ".")
    except Exception:
        return "—"


@app.template_filter("utc_local")
def utc_local_filter(value):
    return config_manager.utc_to_local(value or "")


@app.route("/media/<name>")
def serve_local_media(name):
    """Sirve imágenes de empresa desde el cache local (evita peticiones al servidor)."""
    path = station.get_local_media_path(name)
    if path:
        return send_file(path)
    # Fallback: redirige al servidor si no hay cache local
    s = station.fetch()
    server_url = config_manager.get("server_url", "").rstrip("/")
    remote = s.get(f"{name}_url")
    if remote:
        return redirect(server_url + remote if remote.startswith("/") else remote)
    return "", 404


@app.context_processor
def inject_station():
    """Inyecta info de estación y empresa en todos los templates."""
    s = station.fetch()
    def _url(name, server_relative):
        if station.get_local_media_path(name):
            return f"/media/{name}"
        if server_relative:
            server_url = config_manager.get("server_url", "").rstrip("/")
            return server_url + server_relative if server_relative.startswith("/") else server_relative
        return None
    return {
        "station": s,
        "station_logo_url":   _url("logo",   s.get("logo_url")),
        "station_banner_url": _url("banner", s.get("banner_url")),
    }


@app.route("/")
def dashboard():
    return render_template(
        "index.html",
        state=poller.state,
        cfg=config_manager.load(),
        tmpl_count=len(template_manager.get_all()),
    )


@app.route("/tools")
def tools():
    return render_template(
        "tools.html",
        state=poller.state,
        cfg=config_manager.load(),
        available_printers=printer_module.list_printers(),
    )


@app.route("/history")
def history():
    today     = datetime.now().strftime("%Y-%m-%d")
    f_type    = request.args.get("type", "")
    f_from    = request.args.get("from", today)
    f_to      = request.args.get("to",   today)
    f_company = request.args.get("company", "")
    rows  = db.get_history(300, ticket_type=f_type, date_from=f_from,
                           date_to=f_to, company=f_company)
    stats = db.get_stats()
    return render_template("history.html", rows=rows, stats=stats,
                           f_type=f_type, f_from=f_from, f_to=f_to,
                           f_company=f_company, today=today)


@app.route("/reprint/<int:row_id>", methods=["POST"])
def reprint_job(row_id):
    import json as _json
    import concurrent.futures

    row = db.get_by_id(row_id)
    if not row or not row.get("payload_json"):
        return redirect(url_for("history") + "?reprint_err=Sin+datos+para+reimprimir")

    def _do():
        from datetime import datetime, timezone as _tz
        payload      = _json.loads(row["payload_json"])
        payload["reprint_date"] = datetime.now(_tz.utc).isoformat()
        ticket_type  = row["ticket_type"]
        template     = template_manager.get_current(ticket_type)
        printer_name = config_manager.get("printer_name", "auto")
        p = printer_module.open_printer(printer_name)
        if p is None:
            raise Exception(f"No se pudo abrir impresora '{printer_name}'")
        try:
            modules.render(ticket_type, p, payload, template)
        finally:
            try: p.close()
            except Exception: pass
        return payload

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_do)
        try:
            payload = future.result(timeout=12)
            db.increment_print_count(row_id)
            return redirect(url_for("history") + "?reprinted=1")
        except concurrent.futures.TimeoutError:
            return redirect(url_for("history") + "?reprint_err=Timeout+al+imprimir")
        except Exception as exc:
            return redirect(url_for("history") + f"?reprint_err={str(exc)[:80]}")


@app.route("/config", methods=["GET"])
def config_page():
    cfg = config_manager.load()
    available_printers = printer_module.list_printers()
    cached_templates = template_manager.get_all()
    return render_template(
        "config.html",
        cfg=cfg,
        available_printers=available_printers,
        cached_templates=cached_templates,
        saved=False,
    )


def _print_with_timeout(printer_name: str, font_name: str = None,
                        font_size: int = None, timeout: int = 10) -> dict:
    """Ejecuta print_test en un hilo con timeout para no bloquear Flask."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(poller.print_test, printer_name, font_name, font_size)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return {
                "ok": False,
                "error": f"La impresora no respondió en {timeout}s. "
                         "Verifica que esté encendida, en línea y sin atascos.",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


@app.route("/config/test-printer", methods=["POST"])
def config_test_printer():
    """Paso 1: hace test de impresión con la config del formulario sin guardar aún."""
    pending = {
        "server_url":            config_manager.normalize_server_url(request.form.get("server_url", "")),
        "printer_api_key":       request.form.get("printer_api_key", "").strip(),
        "printer_name":          request.form.get("printer_name", "auto").strip(),
        "portal_port":           request.form.get("portal_port", "80"),
        "poll_interval_seconds": request.form.get("poll_interval_seconds", "2"),
        "ticket_font":           request.form.get("ticket_font", "calibri").strip().lower(),
        "ticket_font_size":      request.form.get("ticket_font_size", "26"),
        "ticket_timezone":       request.form.get("ticket_timezone", "").strip(),
    }
    print_result = _print_with_timeout(
        pending["printer_name"],
        font_name=pending["ticket_font"],
        font_size=int(pending["ticket_font_size"]),
    )
    available_printers = printer_module.list_printers()
    return render_template(
        "config.html",
        cfg=config_manager.load(),
        available_printers=available_printers,
        pending=pending,
        print_result=print_result,
        saved=False,
    )


@app.route("/config", methods=["POST"])
def config_save():
    """Paso 2: guarda la config (solo si viene confirmada desde config_test_printer)."""
    cfg = config_manager.load()
    cfg["server_url"]            = config_manager.normalize_server_url(request.form.get("server_url", ""))
    cfg["printer_api_key"]       = request.form.get("printer_api_key", "").strip()
    cfg["printer_name"]          = request.form.get("printer_name", "auto").strip()
    cfg["portal_port"]           = int(request.form.get("portal_port", 80))
    cfg["poll_interval_seconds"] = max(1, int(request.form.get("poll_interval_seconds", 2)))
    cfg["ticket_font"]           = request.form.get("ticket_font", "calibri").strip().lower()
    cfg["ticket_font_size"]      = max(10, min(32, int(request.form.get("ticket_font_size", 18))))
    cfg["ticket_timezone"]       = request.form.get("ticket_timezone", "").strip()
    config_manager.save(cfg)
    logger.info("Configuración guardada desde portal")
    available_printers = printer_module.list_printers()
    cached_templates = template_manager.get_all()
    return render_template(
        "config.html",
        cfg=cfg,
        available_printers=available_printers,
        cached_templates=cached_templates,
        saved=True,
    )


@app.route("/test-print", methods=["POST"])
def test_print():
    result = _print_with_timeout(config_manager.get("printer_name", "auto"))
    return render_template(
        "tools.html",
        state=poller.state,
        cfg=config_manager.load(),
        available_printers=printer_module.list_printers(),
        test_result=result,
    )


@app.route("/api/status")
def api_status():
    return jsonify({
        "agent": "GestionCom Print Agent",
        "state": poller.state,
        "config": {
            "server_url": config_manager.get("server_url"),
            "printer_name": config_manager.get("printer_name"),
            "poll_interval_seconds": config_manager.get("poll_interval_seconds"),
        },
    })


@app.route("/about")
def about():
    import sys
    import platform

    def _pkg(name):
        try:
            import importlib.metadata
            return importlib.metadata.version(name)
        except Exception:
            return None

    pil_ver     = _pkg("Pillow")
    barcode_ver = _pkg("python-barcode")
    escpos_ver  = _pkg("python-escpos")
    flask_ver   = _pkg("flask")
    requests_ver= _pkg("requests")

    return render_template(
        "about.html",
        agent_version = AGENT_VERSION,
        python_version= sys.version,
        platform_info = platform.platform(),
        cfg           = config_manager.load(),
        stats         = db.get_stats(),
        pil_ver       = pil_ver,
        barcode_ver   = barcode_ver,
        escpos_ver    = escpos_ver,
        flask_ver     = flask_ver,
        requests_ver  = requests_ver,
    )


@app.route("/force-sync", methods=["POST"])
def force_sync():
    from modules.image_renderer import clear_image_cache
    clear_image_cache()
    station.clear()
    station.fetch(force=True)   # re-descarga station-info + imágenes locales
    ok, _, msg = template_manager.force_update_all()
    param = f"sync_ok={msg}" if ok else f"sync_err={msg}"
    return redirect(url_for("tools") + f"?{param}")


@app.route("/restart", methods=["POST"])
def restart():
    from modules.image_renderer import clear_image_cache
    poller.stop()
    station.clear()
    clear_image_cache()
    poller.start()
    return redirect(url_for("tools") + "?restarted=1")


@app.route("/shutdown", methods=["POST"])
def shutdown():
    poller.stop()
    def _exit():
        time.sleep(0.8)
        os._exit(0)
    threading.Thread(target=_exit, daemon=True).start()
    return "<html><body style='font-family:sans-serif;text-align:center;padding:3rem'>" \
           "<h2>Agente detenido.</h2><p>Puedes cerrar esta pestaña.</p></body></html>"


def run(port: int = 80, debug: bool = False) -> None:
    logger.info("Portal iniciado en http://localhost:%d", port)
    app.run(host="127.0.0.1", port=port, debug=debug, use_reloader=False)

"""
Loop principal de polling: consulta el servidor cada N segundos,
descarga trabajos pendientes y los ejecuta.
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import requests

import config_manager
import db
import modules
import printer as printer_module
import station
import template_manager

logger = logging.getLogger("agent.poller")

# Estado compartido consultado por el portal
state = {
    "running": False,
    "last_poll": None,
    "last_job_code": None,
    "last_job_status": None,
    "last_job_type": None,
    "last_error": None,
    "jobs_ok": 0,
    "jobs_failed": 0,
    "server_reachable": False,
    "printer_ok": False,
    "printer_name": None,
}

_stop_event = threading.Event()
_thread: Optional[threading.Thread] = None

# Cuántos ciclos esperamos para re-verificar versión de template (cada ~2 min a 2s/poll)
_TEMPLATE_CHECK_INTERVAL = 60
# Verificar disponibilidad de impresora cada ~60s sin imprimir nada
_PRINTER_CHECK_INTERVAL = 30


def _api_headers() -> dict:
    return {"X-Printer-Api-Key": config_manager.get("printer_api_key", "")}


def _check_printer_status() -> None:
    """Verifica disponibilidad de la impresora usando EnumPrinters (sin abrir job)."""
    printer_name = config_manager.get("printer_name", "auto")
    try:
        if printer_name.lower() == "auto":
            target = printer_module.detect_thermal_printer()
            state["printer_ok"] = bool(target)
            state["printer_name"] = target or state.get("printer_name")
        else:
            available = printer_module.list_printers()
            state["printer_ok"] = printer_name in available
            state["printer_name"] = printer_name
            if not state["printer_ok"]:
                logger.debug("Impresora '%s' no en la lista del sistema", printer_name)
    except Exception as exc:
        logger.debug("Error verificando impresora: %s", exc)
        state["printer_ok"] = False


def _fetch_pending_jobs() -> list[dict]:
    try:
        resp = requests.get(
            f"{config_manager.api_base_url()}/print/agent/jobs/pending",
            headers=_api_headers(),
            timeout=5,
        )
        state["server_reachable"] = resp.status_code == 200
        if resp.status_code == 200:
            return resp.json().get("data", [])
        logger.warning("Servidor respondió HTTP %s al consultar jobs", resp.status_code)
    except requests.RequestException as exc:
        state["server_reachable"] = False
        state["last_error"] = str(exc)
        logger.debug("Sin conexión al servidor: %s", exc)
    return []


def _update_job_status(job_code: str, status: str, error: Optional[str] = None) -> None:
    payload: dict = {"status": status}
    if error:
        payload["error_message"] = error[:500]
    try:
        requests.patch(
            f"{config_manager.api_base_url()}/print/agent/jobs/{job_code}/status",
            json=payload,
            headers=_api_headers(),
            timeout=5,
        )
    except requests.RequestException as exc:
        logger.warning("No se pudo actualizar estado del job %s: %s", job_code, exc)


def _execute_job(job: dict, templates: dict) -> None:
    job_code = job.get("job_code", "?")
    ticket_type = job.get("ticket_type", "TICKET_VENTA")
    payload = job.get("payload", {})
    template = templates.get(ticket_type) or templates.get("TICKET_VENTA") or template_manager.DEFAULT_TEMPLATE.copy()

    logger.info("Ejecutando job %s [%s]", job_code, ticket_type)
    _update_job_status(job_code, "PROCESSING")

    printer_name = config_manager.get("printer_name", "auto")
    p = printer_module.open_printer(printer_name)

    if p is None:
        err = f"No se pudo abrir impresora '{printer_name}'"
        logger.error(err)
        _update_job_status(job_code, "FAILED", err)
        state["last_job_status"] = "FAILED"
        state["last_error"] = err
        state["jobs_failed"] += 1
        state["printer_ok"] = False
        return

    state["printer_ok"] = True
    state["printer_name"] = printer_name if printer_name != "auto" else state.get("printer_name")

    try:
        modules.render(ticket_type, p, payload, template)
        _update_job_status(job_code, "COMPLETED")
        db.log_job(job_code=job_code, ticket_type=ticket_type, status="COMPLETED", payload=payload)
        state["last_job_status"] = "COMPLETED"
        state["last_error"] = None
        state["jobs_ok"] += 1
        logger.info("Job %s completado", job_code)
    except Exception as exc:
        err = str(exc)
        logger.error("Error imprimiendo job %s: %s", job_code, err)
        _update_job_status(job_code, "FAILED", err)
        db.log_job(job_code=job_code, ticket_type=ticket_type, status="FAILED", payload=payload, error=err)
        state["last_job_status"] = "FAILED"
        state["last_error"] = err
        state["jobs_failed"] += 1
    finally:
        try:
            p.close()
        except Exception:
            pass

    state["last_job_code"] = job_code
    state["last_job_type"] = ticket_type


def _poll_loop() -> None:
    logger.info("Poller iniciado")
    state["running"] = True
    cycle = 0
    templates = template_manager.get_all()

    db.init()
    station.fetch()
    _check_printer_status()

    while not _stop_event.is_set():
        # Verificar templates periódicamente
        if cycle % _TEMPLATE_CHECK_INTERVAL == 0:
            updated, templates = template_manager.check_and_update_all()
            if updated:
                logger.info("Templates actualizados en ciclo %d: %s", cycle, list(templates.keys()))

        # Verificar impresora periódicamente si no hay jobs activos
        if cycle > 0 and cycle % _PRINTER_CHECK_INTERVAL == 0:
            _check_printer_status()

        state["last_poll"] = datetime.now(timezone.utc).isoformat()

        jobs = _fetch_pending_jobs()
        for job in jobs:
            if _stop_event.is_set():
                break
            _execute_job(job, templates)

        interval = config_manager.get("poll_interval_seconds", 2)
        _stop_event.wait(timeout=interval)
        cycle += 1

    state["running"] = False
    logger.info("Poller detenido")


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_poll_loop, name="poller", daemon=True)
    _thread.start()


def stop() -> None:
    _stop_event.set()
    if _thread:
        _thread.join(timeout=10)


def print_test(printer_name: Optional[str] = None,
               font_name: Optional[str] = None,
               font_size: Optional[int] = None) -> dict:
    """Imprime un ticket de prueba. Llamado desde el portal y el CLI."""
    cfg = config_manager.load()
    printer_name = printer_name or cfg.get("printer_name", "auto")
    p = printer_module.open_printer(printer_name)
    if p is None:
        return {"ok": False, "error": f"No se pudo abrir impresora '{printer_name}'"}

    template = template_manager.get_current("TICKET_VENTA")
    s = station.fetch()
    test_payload = {
        "company": {
            "name":         s.get("company_name", ""),
            "fantasy_name": s.get("company_fantasy_name", ""),
            "rut":          "",
            "address":      "",
            "logo_url":     s.get("logo_url"),
            "banner_url":   s.get("banner_url"),
        },
        "server_url":       cfg.get("server_url", ""),
        "printer_name":     printer_name,
        "template_version": template.get("version", "—"),
        "template_code":    template.get("template_code", "—"),
        "ticket_font":      font_name or cfg.get("ticket_font", "calibri"),
        "ticket_font_size": font_size or cfg.get("ticket_font_size", 26),
    }
    try:
        modules.render("TICKET_PRUEBA", p, test_payload, template)
        state["printer_ok"] = True
        state["printer_name"] = printer_name
        return {"ok": True, "printer_name": printer_name}
    except Exception as exc:
        state["printer_ok"] = False
        return {"ok": False, "printer_name": printer_name, "error": str(exc)}
    finally:
        try:
            p.close()
        except Exception:
            pass

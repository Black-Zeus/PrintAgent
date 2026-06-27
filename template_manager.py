"""
Gestión de templates: descarga desde el servidor y cache local.

El agente verifica la versión en cada arranque y cada poll cycle.
Si la versión del servidor difiere del cache, descarga el template completo.
"""
import json
import logging
from pathlib import Path
from typing import Optional

import requests

import config_manager

logger = logging.getLogger("agent.template")

CACHE_PATH = Path(__file__).parent / "template_cache.json"

# Template por defecto cuando el servidor no responde o no tiene template activo
DEFAULT_TEMPLATE = {
    "template_code": "DEFAULT",
    "version": "0.0.0",
    "paper_width_mm": 80,
    "content": {
        "header": {
            "show_logo": False,
            "show_commercial_name": True,
            "show_fantasy_name": True,
            "show_rut": True,
            "show_date": True,
        },
        "body": {
            "show_unit_price": False,
            "show_discount": True,
        },
        "footer": {
            "show_subtotal": True,
            "show_tax": True,
            "show_discounts": True,
            "show_total": True,
            "show_payment_method": True,
            "show_change": True,
            "show_barcode": True,
            "barcode_field": "ticket_number",
            "barcode_type": "CODE128",
            "footer_message": "Guarda este ticket para cambios",
        },
    },
}


def _api_headers() -> dict:
    return {"X-Printer-Api-Key": config_manager.get("printer_api_key", "")}


def _server_url() -> str:
    return config_manager.get("server_url", "").rstrip("/")


def load_cached() -> dict:
    """Carga el template desde cache local. Retorna DEFAULT_TEMPLATE si no hay cache."""
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Cache de template corrupto, usando default: %s", exc)
    return DEFAULT_TEMPLATE.copy()


def _save_cache(template: dict) -> None:
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2, ensure_ascii=False)


def check_and_update() -> tuple[bool, dict]:
    """
    Consulta la versión del servidor. Si es diferente al cache, descarga el template.
    Retorna (updated: bool, template: dict).
    """
    url = _server_url()
    if not url:
        logger.warning("server_url no configurado")
        return False, load_cached()

    try:
        resp = requests.get(
            f"{url}/print/agent/template-version",
            headers=_api_headers(),
            timeout=5,
        )
        if resp.status_code != 200:
            logger.warning("Error verificando versión de template: HTTP %s", resp.status_code)
            return False, load_cached()

        data = resp.json().get("data", {})
        server_version = data.get("version")
        template_code = data.get("template_code")

        if not server_version or not template_code:
            return False, load_cached()

        cached = load_cached()
        if cached.get("version") == server_version and cached.get("template_code") == template_code:
            return False, cached

        # Versión nueva → descargar
        logger.info("Nueva versión de template detectada: %s → %s", cached.get("version"), server_version)
        return _download(template_code)

    except requests.RequestException as exc:
        logger.warning("No se pudo verificar versión de template: %s", exc)
        return False, load_cached()


def _download(template_code: str) -> tuple[bool, dict]:
    url = _server_url()
    try:
        resp = requests.get(
            f"{url}/print/agent/template/{template_code}",
            headers=_api_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error("Error descargando template %s: HTTP %s", template_code, resp.status_code)
            return False, load_cached()

        template = resp.json().get("data", {})
        _save_cache(template)
        config_manager.set_value("template_cache_version", template.get("version"))
        logger.info("Template actualizado: %s v%s", template_code, template.get("version"))
        return True, template

    except requests.RequestException as exc:
        logger.error("Error descargando template: %s", exc)
        return False, load_cached()


def get_current() -> dict:
    """Retorna el template en cache (sin verificar servidor)."""
    return load_cached()

"""
Gestión de templates: descarga desde el servidor y cache local.

Cache format (template_cache.json):
  { "TICKET_VENTA": { full template object }, "TICKET_CAMBIO": { ... }, ... }

El agente verifica versiones en cada arranque y cada N poll cycles.
Si alguna versión difiere del cache, descarga ese template.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

import config_manager

logger = logging.getLogger("agent.template")

CACHE_PATH = Path(__file__).parent / "template_cache.json"

DEFAULT_TEMPLATE = {
    "template_code": "DEFAULT",
    "version": "0.0.0",
    "paper_width_mm": 80,
    "content": {
        "header": {
            "show_banner": True,
            "show_fantasy_name": True,
            "show_commercial_name": True,
            "show_rut": True,
            "show_address": True,
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
            "show_payment_breakdown": True,
            "show_change": True,
            "show_agreement": True,
            "show_email": True,
            "show_barcode": True,
            "barcode_field": "ticket_number",
            "barcode_type": "CODE128",
            "footer_message": "Guarda este ticket para cambios",
        },
    },
}


def _api_headers() -> dict:
    return {"X-Printer-Api-Key": config_manager.get("printer_api_key", "")}


# ── Cache I/O ─────────────────────────────────────────────────────────────────

def load_all_cached() -> dict[str, dict]:
    """Carga el cache. Retorna dict {ticket_type: template}."""
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Formato antiguo: objeto plano con "version" en raíz
            if "version" in data and "content" in data:
                code = data.get("template_code", "TICKET_VENTA")
                return {code: data}
            # Formato nuevo: dict de ticket_type → template
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if isinstance(v, dict)}
        except Exception as exc:
            logger.warning("Cache de template corrupto, usando default: %s", exc)
    return {}


def _save_all_cache(templates: dict[str, dict]) -> None:
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2, ensure_ascii=False)


def load_cached(ticket_type: str = "TICKET_VENTA") -> dict:
    """Retorna el template cacheado para el tipo dado. Fallback: primer template o DEFAULT."""
    all_templates = load_all_cached()
    if ticket_type in all_templates:
        return all_templates[ticket_type]
    if all_templates:
        return next(iter(all_templates.values()))
    return DEFAULT_TEMPLATE.copy()


def get_all() -> dict[str, dict]:
    """Retorna todos los templates cacheados. Si no hay cache, retorna DEFAULT como TICKET_VENTA."""
    result = load_all_cached()
    if not result:
        return {"TICKET_VENTA": DEFAULT_TEMPLATE.copy()}
    return result


def get_current(ticket_type: str = "TICKET_VENTA") -> dict:
    """Retorna el template cacheado para el tipo dado (sin consultar servidor)."""
    return load_cached(ticket_type)


# ── Descarga ──────────────────────────────────────────────────────────────────

def _download(template_code: str) -> tuple[bool, dict]:
    """Descarga un template por código y actualiza el cache multi-template."""
    url = config_manager.api_base_url()
    try:
        resp = requests.get(
            f"{url}/print/agent/template/{template_code}",
            headers=_api_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error("Error descargando template %s: HTTP %s", template_code, resp.status_code)
            return False, load_cached(template_code)

        template = resp.json().get("data", {})
        template["_synced_at"] = datetime.now(timezone.utc).isoformat()
        all_cached = load_all_cached()
        all_cached[template_code.upper()] = template
        _save_all_cache(all_cached)
        config_manager.set_value("template_cache_version", template.get("version"))
        logger.info("Template actualizado: %s v%s", template_code, template.get("version"))
        return True, template

    except requests.RequestException as exc:
        logger.error("Error descargando template: %s", exc)
        return False, load_cached(template_code)


# ── Verificación periódica ────────────────────────────────────────────────────

def check_and_update_all() -> tuple[bool, dict[str, dict]]:
    """
    Consulta el servidor por todos los templates activos y sus versiones.
    Descarga los que difieren del cache.
    Retorna (updated: bool, {ticket_type: template}).
    """
    url = config_manager.api_base_url()
    if not url:
        logger.warning("server_url no configurado")
        return False, get_all()

    try:
        resp = requests.get(
            f"{url}/print/agent/template-versions",
            headers=_api_headers(),
            timeout=5,
        )
        if resp.status_code != 200:
            logger.warning("Error verificando versiones de template: HTTP %s", resp.status_code)
            return False, get_all()

        server_list = resp.json().get("data", [])
        server_active = {e["template_code"].upper() for e in server_list if e.get("template_code")}
        cached = load_all_cached()
        updated_any = False

        # Descargar templates nuevos o con versión cambiada
        for entry in server_list:
            code = entry.get("template_code")
            server_ver = entry.get("version")
            if not code:
                continue
            cached_ver = cached.get(code, {}).get("version")
            if cached_ver != server_ver:
                logger.info("Nueva versión de template %s: %s → %s", code, cached_ver, server_ver)
                ok, tmpl = _download(code)
                if ok:
                    cached[code] = tmpl
                    updated_any = True

        # Eliminar del cache los tipos que ya no están activos en el servidor
        obsolete = [code for code in list(cached.keys()) if code not in server_active]
        if obsolete:
            for code in obsolete:
                del cached[code]
            _save_all_cache(cached)
            logger.info("Templates obsoletos eliminados del cache: %s", ", ".join(obsolete))
            updated_any = True

        return updated_any, cached if cached else get_all()

    except requests.RequestException as exc:
        logger.warning("No se pudo verificar versiones de template: %s", exc)
        return False, get_all()


def check_and_update() -> tuple[bool, dict]:
    """Backwards compat: verifica y actualiza. Retorna template primario (TICKET_VENTA)."""
    updated, templates = check_and_update_all()
    primary = templates.get("TICKET_VENTA") or next(iter(templates.values()), DEFAULT_TEMPLATE.copy())
    return updated, primary


# ── Forzar sincronización ─────────────────────────────────────────────────────

def force_update_all() -> tuple[bool, dict[str, dict], str]:
    """
    Descarga todos los templates activos del servidor sin comparar versiones.
    Retorna (ok: bool, templates: dict, message: str).
    """
    url = config_manager.api_base_url()
    if not url:
        return False, get_all(), "server_url no configurado"

    try:
        resp = requests.get(
            f"{url}/print/agent/template-versions",
            headers=_api_headers(),
            timeout=5,
        )
        if resp.status_code != 200:
            return False, get_all(), f"Servidor respondió HTTP {resp.status_code}"

        server_list = resp.json().get("data", [])
        if not server_list:
            return False, get_all(), "El servidor no tiene templates activos"

        server_active = {e["template_code"].upper() for e in server_list if e.get("template_code")}
        cached = load_all_cached()
        downloaded: list[str] = []

        for entry in server_list:
            code = entry.get("template_code")
            if not code:
                continue
            ok, tmpl = _download(code)
            if ok:
                cached[code] = tmpl
                time_str = config_manager.utc_to_local(tmpl.get("_synced_at", ""), fmt="%H:%M:%S")
                downloaded.append(f"{code}|v{tmpl.get('version', '?')}|{time_str}")

        # Eliminar del cache los tipos que ya no están activos en el servidor
        for code in [c for c in list(cached.keys()) if c not in server_active]:
            del cached[code]
            logger.info("Template obsoleto eliminado del cache: %s", code)

        if downloaded:
            return True, cached, ";;".join(downloaded)
        return False, cached, "No se pudo descargar ningún template"

    except requests.RequestException as exc:
        return False, get_all(), f"Sin conexión al servidor: {exc}"


def force_update() -> tuple[bool, dict, str]:
    """Backwards compat: fuerza actualización del template primario."""
    ok, templates, msg = force_update_all()
    primary = templates.get("TICKET_VENTA") or next(iter(templates.values()), DEFAULT_TEMPLATE.copy())
    return ok, primary, msg

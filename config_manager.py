"""
Gestión de configuración local del agente.
Lee y escribe config.json en el mismo directorio que este archivo.
"""
import json
import os
from datetime import datetime, timezone as _utc
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "server_url": "http://localhost:8000",
    "printer_api_key": "",
    "printer_name": "auto",
    "portal_port": 80,
    "poll_interval_seconds": 2,
    "template_cache_version": None,
    "max_job_attempts": 3,
    "log_level": "INFO",
    "ticket_font": "calibri",
    "ticket_font_size": 26,
    "ticket_timezone": "",
}


def load() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save(DEFAULTS.copy())
        return DEFAULTS.copy()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Merge defaults so new keys appear automatically
    merged = {**DEFAULTS, **data}
    return merged


def save(config: dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get(key: str, default: Any = None) -> Any:
    return load().get(key, default)


def set_value(key: str, value: Any) -> None:
    config = load()
    config[key] = value
    save(config)


def is_configured() -> bool:
    cfg = load()
    return bool(cfg.get("server_url")) and bool(cfg.get("printer_api_key"))


# Prefijo nginx para el backend-api en GestionCom
_BACKEND_API_PREFIX = "/api"


def api_base_url() -> str:
    """Devuelve la URL base de la API: scheme://host[:port]/api/services.
    Acepta IP sola, URL con o sin esquema — siempre normaliza a solo host:port."""
    raw = get("server_url", "").strip().rstrip("/")
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    parsed = urlparse(raw)
    base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    return base + _BACKEND_API_PREFIX


def normalize_server_url(raw: str) -> str:
    """Normaliza la URL ingresada por el usuario a solo scheme://host[:port].
    Elimina cualquier path — solo se guarda la dirección del servidor."""
    raw = raw.strip().rstrip("/")
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    parsed = urlparse(raw)
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def _get_local_tz():
    """Retorna el objeto tzinfo configurado (o la zona local del sistema)."""
    tz_name = get("ticket_timezone", "").strip()
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo


def local_now(fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Hora actual en la zona horaria configurada."""
    return datetime.now(_get_local_tz()).strftime(fmt)


def utc_to_local(utc_str: str, fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Convierte una cadena ISO UTC al formato local configurado para mostrar en tickets."""
    if not utc_str:
        return ""
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_utc.utc)
        return dt.astimezone(_get_local_tz()).strftime(fmt)
    except Exception:
        return utc_str[:16].replace("T", " ")

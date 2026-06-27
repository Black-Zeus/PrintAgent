"""
Gestión de configuración local del agente.
Lee y escribe config.json en el mismo directorio que este archivo.
"""
import json
import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "server_url": "http://localhost:8000",
    "printer_api_key": "",
    "printer_name": "auto",
    "portal_port": 8765,
    "poll_interval_seconds": 2,
    "template_cache_version": None,
    "max_job_attempts": 3,
    "log_level": "INFO",
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

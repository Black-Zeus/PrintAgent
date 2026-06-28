"""
Información de la estación (punto de venta + empresa).
Se fetcha del servidor al arranque y se cachea en memoria.
Las imágenes (logo, banner) se descargan al disco y se sirven localmente.
"""
import logging
from pathlib import Path

import requests

import config_manager

logger = logging.getLogger("agent.station")

_info: dict = {}

MEDIA_CACHE_DIR = Path(__file__).parent / "media_cache"


def _download_image(relative_url: str, name: str) -> bool:
    """Descarga una imagen del servidor y la guarda en media_cache/."""
    if not relative_url:
        return False
    try:
        base = config_manager.get("server_url", "").rstrip("/")
        full_url = base + relative_url if relative_url.startswith("/") else relative_url
        resp = requests.get(full_url, timeout=8)
        if resp.status_code != 200:
            return False
        MEDIA_CACHE_DIR.mkdir(exist_ok=True)
        ct = resp.headers.get("content-type", "image/jpeg")
        ext = "png" if "png" in ct else "jpg"
        for old in MEDIA_CACHE_DIR.glob(f"{name}.*"):
            old.unlink(missing_ok=True)
        (MEDIA_CACHE_DIR / f"{name}.{ext}").write_bytes(resp.content)
        logger.info("Imagen '%s' cacheada localmente (%s bytes)", name, len(resp.content))
        return True
    except Exception as exc:
        logger.debug("No se pudo cachear imagen '%s': %s", name, exc)
        return False


def get_local_media_path(name: str) -> Path | None:
    """Retorna el Path local de una imagen si existe en cache."""
    for ext in ("jpg", "png", "jpeg", "webp"):
        p = MEDIA_CACHE_DIR / f"{name}.{ext}"
        if p.exists():
            return p
    return None


def fetch(force: bool = False) -> dict:
    global _info
    if _info and not force:
        return _info
    try:
        resp = requests.get(
            f"{config_manager.api_base_url()}/print/agent/station-info",
            headers={"X-Printer-Api-Key": config_manager.get("printer_api_key", "")},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            if data:
                _info = data
                logger.info(
                    "Estación: %s | Empresa: %s",
                    data.get("sales_point_name", "—"),
                    data.get("company_fantasy_name", "—"),
                )
                _download_image(data.get("logo_url"),   "logo")
                _download_image(data.get("banner_url"), "banner")
    except Exception as exc:
        logger.debug("No se pudo obtener station-info: %s", exc)
    return _info


def get(key: str, default=None):
    return _info.get(key, default)


def clear() -> None:
    global _info
    _info = {}

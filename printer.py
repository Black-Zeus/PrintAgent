"""
Interfaz ESC/POS para impresoras térmicas en Windows.

Soporta:
  - Win32Raw: impresora instalada en Windows (USB, red, cualquier cola)
  - Fallback de listado de impresoras via win32print
"""
import logging
import sys
from typing import Optional

logger = logging.getLogger("agent.printer")

# Solo importamos win32print si estamos en Windows
_WIN32PRINT_AVAILABLE = False
if sys.platform == "win32":
    try:
        import win32print
        _WIN32PRINT_AVAILABLE = True
    except ImportError:
        logger.warning("pywin32 no instalado — listado de impresoras no disponible")

_ESCPOS_AVAILABLE = False
try:
    from escpos.printer import Win32Raw
    _ESCPOS_AVAILABLE = True
except ImportError:
    logger.warning("python-escpos no instalado — impresión deshabilitada")


def list_printers() -> list[str]:
    """Lista las impresoras disponibles en el sistema Windows."""
    if not _WIN32PRINT_AVAILABLE:
        return []
    try:
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return [p[2] for p in win32print.EnumPrinters(flags)]
    except Exception as exc:
        logger.error("Error listando impresoras: %s", exc)
        return []


def get_default_printer() -> Optional[str]:
    """Retorna el nombre de la impresora predeterminada del sistema."""
    if not _WIN32PRINT_AVAILABLE:
        return None
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return None


def detect_thermal_printer() -> Optional[str]:
    """
    Intenta detectar automáticamente una impresora térmica buscando
    nombres comunes (XPrinter, Epson TM, Star, BIXOLON, Citizen, etc.)
    """
    printers = list_printers()
    thermal_keywords = ["xprinter", "xp-", "epson tm", "star", "bixolon", "citizen", "postek", "thermal", "pos"]
    for name in printers:
        if any(kw in name.lower() for kw in thermal_keywords):
            return name
    # Fallback: primera impresora disponible
    return printers[0] if printers else None


def open_printer(printer_name: str) -> Optional[object]:
    """
    Abre conexión con la impresora. Retorna instancia escpos o None si falla.
    Si printer_name == 'auto', detecta automáticamente.
    """
    if not _ESCPOS_AVAILABLE:
        logger.error("python-escpos no disponible — no se puede imprimir")
        return None

    target = printer_name
    if printer_name.lower() == "auto":
        target = detect_thermal_printer()
        if not target:
            logger.error("No se detectó ninguna impresora automáticamente")
            return None
        logger.info("Impresora detectada automáticamente: %s", target)

    try:
        p = Win32Raw(target)
        logger.info("Conexión abierta con impresora: %s", target)
        return p
    except Exception as exc:
        logger.error("No se pudo abrir impresora '%s': %s", target, exc)
        return None


def test_connection(printer_name: str) -> dict:
    """
    Verifica si se puede conectar con la impresora. Retorna dict con status.
    """
    if not _ESCPOS_AVAILABLE:
        return {"ok": False, "error": "python-escpos no instalado"}

    target = printer_name
    if printer_name.lower() == "auto":
        target = detect_thermal_printer()

    if not target:
        return {"ok": False, "error": "No se encontró impresora disponible"}

    try:
        p = Win32Raw(target)
        return {"ok": True, "printer_name": target}
    except Exception as exc:
        return {"ok": False, "printer_name": target, "error": str(exc)}

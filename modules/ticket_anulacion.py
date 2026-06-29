"""Módulo: Ticket de Anulación de Venta."""
import logging

import config_manager
from modules.escpos_helpers import get_cols, separator
from modules.image_renderer import PIL_AVAILABLE, render_anulacion

logger = logging.getLogger("agent.ticket_anulacion")


def render(printer, payload: dict, template: dict) -> None:
    font_name = payload.get("ticket_font") or config_manager.get("ticket_font", "calibri")
    font_size = int(payload.get("ticket_font_size") or config_manager.get("ticket_font_size", 26))

    if PIL_AVAILABLE:
        try:
            img = render_anulacion(payload, template, font_name=font_name, font_size=font_size)
            if img is not None:
                printer.image(img); printer.text("\n"); printer.cut(); return
        except Exception as exc:
            logger.warning("Fallo TrueType en anulacion, usando ESC/POS: %s", exc)

    cols = get_cols(template.get("paper_width_mm", 80))
    printer.set(align="center", bold=True)
    printer.text("--- ANULACIÓN DE VENTA ---\n")
    printer.set(bold=False, align="left")
    printer.text(separator(width=cols) + "\n")
    printer.text(f"Folio anulac.: {payload.get('session_folio', '—')}\n")
    printer.text(f"Folio orig.:   {payload.get('original_folio', '—')}\n")
    printer.text(f"Cajero:        {payload.get('cashier_name', '—')}\n")
    printer.text(separator(width=cols) + "\n")
    printer.set(bold=True)
    printer.text(f"MONTO ANULADO: $ {payload.get('cancelled_amount', 0):,}\n".replace(",", "."))
    printer.set(bold=False)
    printer.text(f"Motivo: {payload.get('reason', '—')}\n")
    printer.text(f"Estado: {payload.get('cancellation_status', '—')}\n")
    printer.text("\n\n"); printer.cut()

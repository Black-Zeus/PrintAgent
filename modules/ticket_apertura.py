"""
Módulo: Ticket de Apertura de Caja
Renderiza el comprobante de apertura de sesión de caja.
"""
import logging

import config_manager
from modules.escpos_helpers import get_cols, separator
from modules.image_renderer import PIL_AVAILABLE, render_apertura

logger = logging.getLogger("agent.ticket_apertura")


def render(printer, payload: dict, template: dict) -> None:
    font_name = payload.get("ticket_font") or config_manager.get("ticket_font", "calibri")
    font_size = int(payload.get("ticket_font_size") or config_manager.get("ticket_font_size", 26))

    if PIL_AVAILABLE:
        try:
            img = render_apertura(payload, template, font_name=font_name, font_size=font_size)
            if img is not None:
                printer.image(img)
                printer.text("\n")
                printer.cut()
                return
        except Exception as exc:
            logger.warning("Fallo TrueType en apertura, usando ESC/POS: %s", exc)

    # Fallback ESC/POS
    paper_mm = template.get("paper_width_mm", 80)
    cols     = get_cols(paper_mm)

    printer.set(align="center", bold=True)
    printer.text("--- APERTURA DE CAJA ---\n")
    printer.set(bold=False, align="left")
    printer.text(separator(width=cols) + "\n")
    printer.text(f"Folio:    {payload.get('session_folio', '—')}\n")
    printer.text(f"Sucursal: {payload.get('branch_name', '—')}\n")
    printer.text(f"Caja:     {payload.get('cash_register_name', '—')}\n")
    printer.text(f"Cajero:   {payload.get('cashier_name', '—')}\n")
    if payload.get("supervisor_name"):
        printer.text(f"Superv.:  {payload['supervisor_name']}\n")
    printer.text(separator(width=cols) + "\n")
    printer.set(bold=True)
    printer.text(f"MONTO INICIAL: $ {payload.get('initial_amount', 0):,}\n".replace(",", "."))
    printer.set(bold=False)
    printer.text("\n\n")
    printer.cut()

"""
Módulo: Ticket de Cambio / Devolución
Mismo renderizado PIL/TrueType que ticket_venta — respeta el template configurado.
"""
import logging

import config_manager
from modules.escpos_helpers import (
    get_cols, print_barcode, print_footer_message,
    print_header, print_items, print_totals, separator, truncate,
)
from modules.image_renderer import PIL_AVAILABLE, render_cambio

logger = logging.getLogger("agent.ticket_cambio")


def _escpos_fallback(printer, payload: dict, template: dict) -> None:
    content = template.get("content", {})
    header_cfg = content.get("header", {})
    body_cfg = content.get("body", {})
    footer_cfg = content.get("footer", {})
    cols = get_cols(template.get("paper_width_mm", 80))

    print_header(printer, payload, header_cfg, cols=cols)

    doc_type = truncate(payload.get("document_type", "TICKET DE CAMBIO"), cols)
    ticket_num = payload.get("ticket_number", "")
    printer.set(align="center", bold=True, double_height=False, double_width=False, font="a")
    printer.text(f"{doc_type}\n")
    if ticket_num:
        printer.set(bold=False, font="b", double_height=False, double_width=False)
        printer.text(f"N\xb0 {ticket_num}\n")
    printer.set(align="left", bold=False, double_height=False, double_width=False, font="a")
    printer.text(separator(width=cols) + "\n")

    printer.set(font="b", align="left", bold=False, double_height=False, double_width=False)
    print_items(printer, payload, body_cfg, cols=cols, font="b")

    printer.set(font="a", align="left", bold=False, double_height=False, double_width=False)
    print_totals(printer, payload, footer_cfg, cols=cols)

    print_barcode(printer, payload, footer_cfg, cols=cols)
    print_footer_message(printer, footer_cfg)

    printer.text("\n\n")
    printer.cut()


def render(printer, payload: dict, template: dict) -> None:
    font_name = config_manager.get("ticket_font", "calibri")
    font_size = int(config_manager.get("ticket_font_size", 18))

    if PIL_AVAILABLE:
        try:
            img = render_cambio(payload, template, font_name=font_name, font_size=font_size)
            if img is not None:
                printer.image(img)
                printer.text("\n")
                printer.cut()
                return
        except Exception as exc:
            logger.warning("Fallo renderizado TrueType en cambio, usando ESC/POS: %s", exc)

    _escpos_fallback(printer, payload, template)

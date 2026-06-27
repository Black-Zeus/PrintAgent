"""
Módulo: Ticket de Cambio / Devolución
Mismo layout que el ticket de venta pero con encabezado diferenciado.
"""
from modules.escpos_helpers import (
    COLS, center_text, print_barcode, print_footer_message,
    print_header, print_items, print_totals, separator,
)


def render(printer, payload: dict, template: dict) -> None:
    content = template.get("content", {})
    header_cfg = content.get("header", {})
    body_cfg = content.get("body", {})
    footer_cfg = content.get("footer", {})

    print_header(printer, payload, header_cfg)

    ticket_num = payload.get("ticket_number", "")
    doc_type = payload.get("document_type", "TICKET DE CAMBIO")
    printer.set(align="center", bold=True)
    printer.text(f"{doc_type}\n")
    if ticket_num:
        printer.text(f"N° {ticket_num}\n")
    printer.set(align="left", bold=False)
    printer.text(separator("*") + "\n")

    print_items(printer, payload, body_cfg)
    print_totals(printer, payload, footer_cfg)
    print_barcode(printer, payload, footer_cfg)
    print_footer_message(printer, footer_cfg)

    printer.text("\n\n\n")
    printer.cut()

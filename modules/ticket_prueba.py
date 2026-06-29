"""
Módulo: Ticket de Prueba
Renderiza un ticket de prueba con 3 productos de muestra usando el layout real,
marcado claramente como prueba. Sirve para verificar impresora, fuente y papel.
"""
import logging
from datetime import datetime, timezone

import config_manager
from modules.escpos_helpers import get_cols, separator
from modules.image_renderer import PIL_AVAILABLE, render_prueba

logger = logging.getLogger("agent.ticket_prueba")


def render(printer, payload: dict, template: dict) -> None:
    font_name = payload.get("ticket_font") or config_manager.get("ticket_font", "calibri")
    font_size = int(payload.get("ticket_font_size") or config_manager.get("ticket_font_size", 26))

    if PIL_AVAILABLE:
        try:
            img = render_prueba(payload, template, font_name=font_name, font_size=font_size)
            if img is not None:
                printer.image(img)
                printer.text("\n")
                printer.cut()
                return
        except Exception as exc:
            logger.warning("Fallo TrueType en prueba, usando ESC/POS: %s", exc)

    # Fallback ESC/POS
    paper_mm = template.get("paper_width_mm", 80)
    cols     = get_cols(paper_mm)
    now      = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")

    printer.set(align="center", bold=True)
    printer.text("*** TICKET DE PRUEBA ***\n")
    printer.text("NO ES UNA VENTA REAL\n")
    printer.set(bold=False)
    printer.text(separator(width=cols) + "\n")
    printer.set(align="left")
    for item in payload.get("items", []):
        name  = item.get("name", "")
        qty   = item.get("qty", 1)
        total = item.get("total", 0)
        printer.text(f"{name}\n")
        printer.text(f"  {qty} x $ {item.get('unit_price', 0):,}".replace(",", ".") + f"   $ {total:,}\n".replace(",", "."))
    printer.text(separator(width=cols) + "\n")
    printer.text(f"TOTAL:    $ {payload.get('total_amount', 0):,}\n".replace(",", "."))
    printer.text(separator(width=cols) + "\n")
    printer.text(f"Fecha:    {now}\n")
    printer.text(f"Template: {payload.get('template_code', '—')} v{payload.get('template_version', '—')}\n")
    printer.text(f"Fuente:   {payload.get('ticket_font', '—')} {payload.get('ticket_font_size', '—')}px\n")
    printer.text(f"Impres.:  {payload.get('printer_name', '—')}\n")
    printer.text(separator(width=cols) + "\n")
    printer.set(align="center")
    printer.text("Si ves este ticket\nel agente funciona OK.\n")
    printer.text("\n\n")
    printer.cut()

"""
Módulo: Ticket de Prueba
Imprime un ticket de diagnóstico para verificar la conexión y configuración.
"""
from datetime import datetime, timezone
from modules.escpos_helpers import COLS, separator


def render(printer, payload: dict, template: dict) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    server_url = payload.get("server_url", "")
    printer_name = payload.get("printer_name", "")
    template_version = payload.get("template_version", "—")
    template_code = payload.get("template_code", "—")

    printer.set(align="center")
    printer.set(bold=True, double_height=True)
    printer.text("PRUEBA DE IMPRESION\n")
    printer.set(bold=False, double_height=False)
    printer.text("CeciChic Print Agent\n")
    printer.text(separator() + "\n")

    printer.set(align="left")
    printer.text(f"Fecha     : {now}\n")
    printer.text(f"Servidor  : {server_url}\n")
    printer.text(f"Impresora : {printer_name}\n")
    printer.text(f"Template  : {template_code} v{template_version}\n")
    printer.text(separator() + "\n")

    printer.set(align="center")
    printer.text("Si ves este ticket, el agente\n")
    printer.text("esta funcionando correctamente.\n")

    try:
        printer.barcode("TEST12345", "CODE128", height=48, width=2, pos="BELOW")
    except Exception:
        printer.text("\n[TEST12345]\n")

    printer.text("\n\n\n")
    printer.cut()

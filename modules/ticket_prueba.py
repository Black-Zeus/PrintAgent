"""
Módulo: Ticket de Prueba
Usa el header del template activo (banner, empresa, RUT, dirección) y muestra
información de diagnóstico en el cuerpo. Sirve para calibrar fuente y papel.
"""
import logging

import config_manager
from modules.escpos_helpers import get_cols
from modules.image_renderer import (
    PIL_AVAILABLE, PAPER_DOTS, TicketCanvas, load_fonts,
    _fetch_company_image,
)

logger = logging.getLogger("agent.ticket_prueba")


def _render_pil(printer, payload: dict, template: dict) -> None:
    font_name = payload.get("ticket_font") or config_manager.get("ticket_font", "calibri")
    font_size = int(payload.get("ticket_font_size") or config_manager.get("ticket_font_size", 26))

    paper_mm = template.get("paper_width_mm", 80)
    width    = PAPER_DOTS.get(paper_mm, 384)
    content  = template.get("content", {})
    hdr_cfg  = content.get("header", {})

    F  = load_fonts(font_name, font_size)
    fB = F["bold"]
    fR = F["regular"]
    fS = F["small"]

    company = payload.get("company", {})
    c = TicketCanvas(width=width)

    # ── Header: igual que render_venta ───────────────────────────────────────
    if hdr_cfg.get("show_banner", True):
        banner_url = company.get("banner_url")
        if banner_url:
            banner_img = _fetch_company_image(banner_url, width)
            if banner_img is not None:
                c.paste(banner_img, align="center", gap=8)
                c.separator()

    c.spacer(6)
    if hdr_cfg.get("show_fantasy_name"):
        fantasy = company.get("fantasy_name", "")
        if fantasy:
            c.text(fantasy, fB, align="center", gap=7)

    if hdr_cfg.get("show_commercial_name"):
        name = company.get("name", "")
        if name:
            c.text(name, fS, align="center", gap=6)

    if hdr_cfg.get("show_rut"):
        rut = company.get("rut", "")
        if rut:
            c.text(f"RUT: {rut}", fS, align="center", gap=6)

    if hdr_cfg.get("show_address"):
        address = company.get("address", "")
        if address:
            c.text(address, fS, align="center", gap=6)

    # ── Sección diagnóstico ──────────────────────────────────────────────────
    c.spacer(6)
    c.separator()
    c.spacer(4)
    c.text("TICKET DE PRUEBA", fB, align="center", gap=6)
    c.separator()
    c.spacer(4)

    now          = config_manager.local_now()
    server_url   = payload.get("server_url", "—")
    printer_name = payload.get("printer_name", "—")
    tmpl_version = payload.get("template_version", "—")
    tmpl_code    = payload.get("template_code", "—")

    c.text(f"Fecha:     {now}", fR, gap=5)
    c.text(f"Template:  {tmpl_code}  v{tmpl_version}", fR, gap=5)
    c.text(f"Fuente:    {font_name}  {font_size}px", fR, gap=5)
    c.text(f"Impres.:   {printer_name}", fR, gap=5)
    c.text(f"Servidor:  {server_url}", fS, gap=5)
    c.separator()
    c.spacer(4)
    c.text("Si ves este ticket,", fR, align="center", gap=4)
    c.text("el agente funciona OK.", fB, align="center", gap=6)
    c.spacer(6)

    printer.image(c.render())
    printer.text("\n")
    printer.cut()


def render(printer, payload: dict, template: dict) -> None:
    if PIL_AVAILABLE:
        try:
            _render_pil(printer, payload, template)
            return
        except Exception as exc:
            logger.warning("Fallo TrueType en prueba, usando ESC/POS: %s", exc)

    # Fallback ESC/POS
    from modules.escpos_helpers import separator
    paper_mm = template.get("paper_width_mm", 80)
    cols     = get_cols(paper_mm)
    now      = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")

    printer.set(align="center", bold=True)
    printer.text("TICKET DE PRUEBA\n")
    printer.set(bold=False)
    printer.text("GestionCom Print Agent\n")
    printer.text(separator(width=cols) + "\n")
    printer.set(align="left")
    printer.text(f"Fecha:    {now}\n")
    printer.text(f"Servidor: {payload.get('server_url', '—')}\n")
    printer.text(f"Impres.:  {payload.get('printer_name', '—')}\n")
    printer.text(f"Template: {payload.get('template_code', '—')} v{payload.get('template_version', '—')}\n")
    printer.text(f"Fuente:   {payload.get('ticket_font', '—')} {payload.get('ticket_font_size', '—')}px\n")
    printer.text(separator(width=cols) + "\n")
    printer.set(align="center")
    printer.text("Si ves este ticket\nel agente funciona OK.\n")
    printer.text("\n\n")
    printer.cut()

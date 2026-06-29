"""
Renderizador de tickets usando PIL/Pillow con fuentes TrueType del sistema Windows.
Genera una imagen bitmap 1-bit que se envía a la impresora via printer.image().

Ventaja sobre ESC/POS bitmap: control total de tamaño de fuente (configurable),
fuentes antialiased, layout proporcional sin contar columnas.

Estructura:
  - Utilidades de fuente / canvas / barcode (privadas)
  - Secciones compartidas _sec_*  ← building blocks para cualquier ticket
  - Funciones públicas render_*   ← orquestadores, solo contienen su body propio
"""
from __future__ import annotations

import logging
import os
import re
from decimal import Decimal
from io import BytesIO
from typing import Optional

import config_manager

logger = logging.getLogger("agent.image_renderer")

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import barcode as _barcode_lib
    from barcode.writer import ImageWriter as _BarcodeImageWriter
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False
    logger.warning("python-barcode no instalado — barcode desactivado. Ejecuta: pip install python-barcode")


# Ancho en dots por ancho de papel (58mm = 384 dots, 80mm = 576 dots)
PAPER_DOTS = {58: 384, 80: 576}

PAD_X = 10
PAD_Y = 10

_FONT_MAP: dict[str, tuple[str, str]] = {
    "calibri":  ("calibri.ttf",   "calibrib.ttf"),
    "arial":    ("arial.ttf",     "arialbd.ttf"),
    "tahoma":   ("tahoma.ttf",    "tahomabd.ttf"),
    "verdana":  ("verdana.ttf",   "verdanab.ttf"),
    "courier":  ("cour.ttf",      "courbd.ttf"),
    "segoe":    ("segoeui.ttf",   "segoeuib.ttf"),
}
_FONTS_DIR = "C:/Windows/Fonts/"


# ── Fuentes ──────────────────────────────────────────────────────────────────

def _load_font(filename: str, size: int):
    path = _FONTS_DIR + filename
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def load_fonts(font_name: str = "calibri", size: int = 18) -> dict:
    reg_file, bold_file = _FONT_MAP.get(font_name.lower(), ("calibri.ttf", "calibrib.ttf"))
    reg   = _load_font(reg_file,  size)
    bold  = _load_font(bold_file, size)
    small = _load_font(reg_file,  max(10, size - 3))
    if reg is ImageFont.load_default():
        reg   = _load_font("arial.ttf",   size)
        bold  = _load_font("arialbd.ttf", size)
        small = _load_font("arial.ttf",   max(10, size - 3))
    return {"regular": reg, "bold": bold, "small": small}


# ── Canvas ───────────────────────────────────────────────────────────────────

_M_IMG = _M_DRAW = None

def _get_measure_draw():
    global _M_IMG, _M_DRAW
    if _M_DRAW is None:
        _M_IMG  = Image.new("L", (2, 2))
        _M_DRAW = ImageDraw.Draw(_M_IMG)
    return _M_DRAW

def _text_wh(text: str, font) -> tuple[int, int]:
    bbox = _get_measure_draw().textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def _fit(text: str, font, max_px: int) -> str:
    if _text_wh(text, font)[0] <= max_px:
        return text
    while len(text) > 1:
        text = text[:-1]
        if _text_wh(text + "...", font)[0] <= max_px:
            return text + "..."
    return "..."

def _clp(value) -> str:
    try:
        return f"$ {int(Decimal(str(value or 0))):,}".replace(",", ".")
    except Exception:
        return str(value)


class TicketCanvas:
    """Acumula operaciones de dibujo; renderiza en una imagen PIL al final."""

    def __init__(self, width: int = 384):
        self.width  = width
        self._ops   = []
        self._y     = PAD_Y
        self._avail = width - PAD_X * 2

    def line_h(self, font) -> int:
        return _text_wh("Ag", font)[1]

    def text(self, text: str, font, align: str = "left", gap: int = 3, fit: bool = True) -> "TicketCanvas":
        t = _fit(text, font, self._avail) if fit else text
        tw, th = _text_wh(t, font)
        x = (self.width - tw) // 2 if align == "center" else (self.width - PAD_X - tw if align == "right" else PAD_X)
        self._ops.append(("text", x, self._y, t, font))
        self._y += th + gap
        return self

    def text_lr(self, left: str, right: str, font, gap: int = 3) -> "TicketCanvas":
        rw, _ = _text_wh(right, font)
        l = _fit(left, font, self._avail - rw - 4)
        self._ops.append(("text", PAD_X, self._y, l, font))
        self._ops.append(("text", self.width - PAD_X - rw, self._y, right, font))
        self._y += self.line_h(font) + gap
        return self

    def separator(self, gap: int = 5) -> "TicketCanvas":
        self._y += gap
        self._ops.append(("line", PAD_X, self._y, self.width - PAD_X, self._y))
        self._y += gap
        return self

    def spacer(self, h: int = 5) -> "TicketCanvas":
        self._y += h
        return self

    def paste(self, img: Image.Image, align: str = "center", gap: int = 4) -> "TicketCanvas":
        iw, ih = img.size
        x = max(0, (self.width - iw) // 2) if align == "center" else (max(0, self.width - iw) if align == "right" else 0)
        self._ops.append(("paste", x, self._y, img))
        self._y += ih + gap
        return self

    def render(self) -> Image.Image:
        img  = Image.new("RGB", (self.width, self._y + PAD_Y), "white")
        draw = ImageDraw.Draw(img)
        for op in self._ops:
            if op[0] == "text":
                _, x, y, text, font = op
                draw.text((x, y), text, font=font, fill="black")
            elif op[0] == "line":
                _, x1, y1, x2, y2 = op
                draw.line([(x1, y1), (x2, y2)], fill="black", width=1)
            elif op[0] == "paste":
                _, x, y, src = op
                img.paste(src.convert("RGB"), (x, y))
        return img.convert("1")


# ── Barcode ──────────────────────────────────────────────────────────────────

_BARCODE_TYPE_MAP: dict[str, str] = {
    "CODE128": "code128", "CODE39": "code39",
    "EAN13": "ean13",     "EAN8":  "ean8",
    "EAN128": "gs1_128",  "GS1_128": "gs1_128", "GS1128": "gs1_128",
    "UPCA": "upca",       "ITF": "itf", "ITF14": "itf",
}
_BC_ALPHANUM = re.compile(r"^[A-Za-z0-9 \-\./\+\%\$]+$")
_BC_NUMERIC  = re.compile(r"^\d+$")


def _render_barcode_img(value: str, paper_dots: int = 384,
                        barcode_type: str = "CODE128") -> Optional[Image.Image]:
    if not BARCODE_AVAILABLE or not PIL_AVAILABLE:
        if not BARCODE_AVAILABLE:
            logger.warning("Barcode omitido: python-barcode no instalado.")
        return None
    lib_type = _BARCODE_TYPE_MAP.get(barcode_type.upper(), "code128")
    pattern  = _BC_NUMERIC if lib_type in {"ean8", "ean13", "gs1_128", "upca", "itf"} else _BC_ALPHANUM
    if not value or not pattern.match(value):
        logger.warning("Barcode omitido: valor %r inválido para tipo %s", value, barcode_type)
        return None
    try:
        writer = _BarcodeImageWriter()
        code   = _barcode_lib.get(lib_type, value, writer=writer)
        buf    = BytesIO()
        code.write(buf, options={
            "module_width": 0.6, "module_height": 20.0, "quiet_zone": 2.0,
            "write_text": False, "background": "white", "foreground": "black",
        })
        buf.seek(0)
        img     = Image.open(buf).convert("RGB")
        ratio   = (paper_dots - 16) / img.width
        img     = img.resize((paper_dots - 16, int(img.height * ratio)), Image.LANCZOS)
        logger.debug("Barcode %s generado: %r → %dx%d px", barcode_type, value, img.width, img.height)
        return img.convert("1")
    except Exception as exc:
        logger.error("Error generando barcode %s para %r: %s", barcode_type, value, exc)
        return None


# ── Imágenes de empresa ───────────────────────────────────────────────────────

_image_cache: dict[str, Image.Image] = {}


def clear_image_cache() -> None:
    _image_cache.clear()
    logger.info("Cache de imágenes limpiado")


def _fetch_company_image(url: str, paper_dots: int = 384, max_width: int | None = None) -> Optional[Image.Image]:
    if not PIL_AVAILABLE or not url:
        return None
    cache_key = f"{url}:{max_width or paper_dots}"
    if cache_key in _image_cache:
        return _image_cache[cache_key]
    try:
        import requests as _req
        base     = config_manager.get("server_url", "").rstrip("/")
        full_url = base + url if url.startswith("/") else url
        resp     = _req.get(full_url, timeout=4)
        if resp.status_code != 200:
            return None
        img     = Image.open(BytesIO(resp.content)).convert("RGB")
        target  = (max_width or paper_dots) - 8
        img     = img.resize((target, int(img.height * target / img.width)), Image.LANCZOS)
        _image_cache[cache_key] = img
        logger.debug("Imagen cacheada: %s (%dx%d px)", url, img.width, img.height)
        return img
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════
# Secciones compartidas  (_sec_*)
# Cada función recibe ctx (dict con canvas/fonts/cfg) + payload y dibuja
# su sección en el canvas. Sin valor de retorno.
# ════════════════════════════════════════════════════════════════════════════

def _init_render(template: dict, font_name: str, font_size: int) -> dict:
    """Prepara canvas, fuentes y config dicts. Retorna ctx usado por _sec_*."""
    paper_mm = template.get("paper_width_mm", 80)
    width    = PAPER_DOTS.get(paper_mm, 384)
    content  = template.get("content", {})
    return {
        "width":  width,
        "hdr":    content.get("header", {}),
        "body":   content.get("body",   {}),
        "foot":   content.get("footer", {}),
        "fonts":  load_fonts(font_name, font_size),
        "canvas": TicketCanvas(width=width),
    }


def _sec_header(ctx: dict, payload: dict) -> None:
    """Banner de empresa + datos de encabezado + separador."""
    c, hdr, F, width = ctx["canvas"], ctx["hdr"], ctx["fonts"], ctx["width"]
    fB, fS = F["bold"], F["small"]
    company = payload.get("company", {})

    if hdr.get("show_banner", True):
        url = company.get("banner_url")
        if url:
            img = _fetch_company_image(url, width)
            if img is not None:
                c.paste(img, align="center", gap=8)
                c.separator()

    c.spacer(6)
    if hdr.get("show_fantasy_name"):
        v = company.get("fantasy_name", "")
        if v: c.text(v, fB, align="center", gap=7)
    if hdr.get("show_commercial_name"):
        v = company.get("name") or company.get("commercial_name", "")
        if v: c.text(v, fS, align="center", gap=6)
    if hdr.get("show_rut"):
        v = company.get("rut", "")
        if v: c.text(f"RUT: {v}", fS, align="center", gap=6)
    if hdr.get("show_address"):
        v = company.get("address", "")
        if v: c.text(v, fS, align="center", gap=6)
    if hdr.get("show_date"):
        date_val = payload.get("sale_date") or payload.get("print_date", "")
        c.text(config_manager.utc_to_local(date_val), fS, align="center", gap=6)

    c.spacer(6)
    c.separator()
    c.spacer(6)


def _sec_doc_id(ctx: dict, payload: dict, default_doc_type: str = "TICKET") -> None:
    """Tipo de documento centrado en negrita + número de ticket."""
    c, F = ctx["canvas"], ctx["fonts"]
    c.text(payload.get("document_type", default_doc_type), F["bold"], align="center", gap=6)
    num = payload.get("ticket_number", "")
    if num:
        c.text(f"{num}", F["small"], align="center", gap=6)


def _sec_items(ctx: dict, items: list) -> None:
    """Lista de productos: nombre, cantidad × precio, descuento por línea."""
    c, body, F = ctx["canvas"], ctx["body"], ctx["fonts"]
    fR, fS = F["regular"], F["small"]
    show_unit = body.get("show_unit_price", True)
    show_disc = body.get("show_discount",   True)

    for item in items:
        qty      = int(item.get("quantity", 1))
        total_v  = Decimal(str(item.get("total",            0) or 0))
        unit_v   = Decimal(str(item.get("unit_price",       0) or 0))
        disc_pct = Decimal(str(item.get("discount_percent", 0) or 0))
        c.text(item.get("name", ""), fR, gap=3)
        qty_label = f"  x{qty}" + (f"  {_clp(unit_v)}" if show_unit else "")
        c.text_lr(qty_label, _clp(total_v), fS, gap=6)
        if show_disc and disc_pct > 0:
            disc_amt = (unit_v * qty) - total_v
            if disc_amt > 0:
                c.text(f"  Desc: -{_clp(disc_amt)}", fS, gap=5)


def _sec_payment(ctx: dict, payload: dict, net_total: Decimal | None = None) -> None:
    """Método de pago, desglose mixto y vuelto.
    Si net_total se provee y es ≤ 0, omite todo (cambio sin cobro adicional)."""
    c, foot, F = ctx["canvas"], ctx["foot"], ctx["fonts"]
    fS = F["small"]
    skip = net_total is not None and net_total <= 0

    if not skip and foot.get("show_payment_method"):
        method = payload.get("payment_method", "")
        if method:
            c.text_lr("Pago:", method, fS, gap=5)

    breakdown = payload.get("payment_breakdown")
    if not skip and foot.get("show_payment_breakdown") and isinstance(breakdown, list):
        for item in breakdown:
            m_name = item.get("method", "")
            m_amt  = Decimal(str(item.get("amount") or 0))
            if m_name:
                c.text_lr(f"  {m_name}:", _clp(m_amt), fS, gap=3)

    if not skip and foot.get("show_change"):
        c.text_lr("Vuelto:", _clp(payload.get("change", 0)), fS, gap=5)


def _sec_agreement(ctx: dict, payload: dict) -> None:
    """Bloque de convenio (crédito o descuento)."""
    c, foot, F = ctx["canvas"], ctx["foot"], ctx["fonts"]
    fS = F["small"]
    agreement = payload.get("agreement")
    if not foot.get("show_agreement") or not isinstance(agreement, dict):
        return

    org        = agreement.get("organization_name", "")
    assoc_id   = agreement.get("associate_identifier", "")
    assoc_name = agreement.get("associate_name", "")
    ag_type    = str(agreement.get("agreement_type") or "").upper()
    single_use = agreement.get("agreement_single_purchase", False)
    remaining  = agreement.get("remaining_credit")
    disc_pct   = agreement.get("discount_percent")

    if not (org or assoc_id):
        return

    c.spacer(4); c.separator(); c.spacer(4)
    c.text("Convenio Crédito" if ag_type == "CREDIT" else "Convenio", fS, align="center", gap=4)
    if org:        c.text_lr("Organización:", org,        fS, gap=4)
    if assoc_name: c.text_lr("Beneficiario:", assoc_name, fS, gap=4)
    if assoc_id:   c.text_lr("Identificador:", assoc_id,  fS, gap=4)
    if ag_type == "CREDIT":
        if remaining is not None:
            c.text_lr("Crédito disponible:", _clp(Decimal(str(remaining))), fS, gap=4)
        if single_use:
            c.spacer(2)
            c.text("Uso único — crédito saldado", fS, align="center", gap=4)
    elif disc_pct:
        c.text_lr("Descuento convenio:", f"{disc_pct}%", fS, gap=4)


def _sec_email(ctx: dict, payload: dict) -> None:
    """Email del cliente (con separador previo si existe)."""
    c, foot, F = ctx["canvas"], ctx["foot"], ctx["fonts"]
    email = payload.get("receipt_email")
    if foot.get("show_email") and email:
        c.spacer(4); c.separator(); c.spacer(4)
        c.text(email, F["small"], align="center", gap=4)


def _sec_footer_msg(ctx: dict) -> None:
    """Mensaje de pie de ticket libre."""
    c, foot, F = ctx["canvas"], ctx["foot"], ctx["fonts"]
    msg = foot.get("footer_message", "")
    if msg:
        c.spacer(6); c.separator(); c.spacer(4)
        c.text(msg, F["small"], align="center", gap=4)


def _sec_reprint(ctx: dict, payload: dict) -> None:
    """Línea de reimpresión (solo si el payload viene de una reimpresión)."""
    reprint_date = payload.get("reprint_date")
    if not reprint_date:
        return
    c, F = ctx["canvas"], ctx["fonts"]
    c.spacer(4)
    c.separator()
    c.spacer(4)
    c.text(f"Reimpresión: {config_manager.utc_to_local(reprint_date)}", F["small"], align="center", gap=4)


def _sec_barcode(ctx: dict, payload: dict) -> None:
    """Código de barras al pie."""
    c, foot, width = ctx["canvas"], ctx["foot"], ctx["width"]
    if not foot.get("show_barcode"):
        return
    bc_field = foot.get("barcode_field", "ticket_number")
    bc_value = str(payload.get(bc_field) or payload.get("ticket_number", "")).strip()
    bc_type  = foot.get("barcode_type", "CODE128")
    logger.debug("Barcode type=%r field=%r value=%r", bc_type, bc_field, bc_value)
    if bc_value:
        bc_img = _render_barcode_img(bc_value, width, barcode_type=bc_type)
        if bc_img is not None:
            c.spacer(8); c.separator(); c.spacer(6)
            c.paste(bc_img, align="center", gap=6)
        else:
            logger.warning("Barcode no renderizado para valor: %r", bc_value)


# ════════════════════════════════════════════════════════════════════════════
# Funciones públicas  render_*
# Cada una orquesta las secciones compartidas + su body propio.
# Para añadir un nuevo tipo de ticket: copiar la plantilla de render_venta,
# reemplazar solo la sección de cuerpo/totales específica del documento.
# ════════════════════════════════════════════════════════════════════════════

def render_venta(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de venta estándar."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    foot = ctx["foot"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    # ── Encabezado ───────────────────────────────────────────────────────────
    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "TICKET DE VENTA")
    c.spacer(6); c.separator(); c.spacer(6)

    # ── Items ─────────────────────────────────────────────────────────────────
    _sec_items(ctx, payload.get("items", []))
    c.separator(); c.spacer(4)

    # ── Totales ───────────────────────────────────────────────────────────────
    if foot.get("show_subtotal"):
        c.text_lr("Subtotal (neto):", _clp(payload.get("subtotal", 0)), fS, gap=5)
    if foot.get("show_tax"):
        c.text_lr("IVA (19%):", _clp(payload.get("tax", 0)), fS, gap=5)
    if foot.get("show_discounts"):
        d = (Decimal(str(payload.get("line_discount",     0) or 0))
           + Decimal(str(payload.get("document_discount", 0) or 0)))
        if d > 0:
            c.text_lr("Descuentos:", f"-{_clp(d)}", fS, gap=5)
    ag_disc = Decimal(str(payload.get("agreement_discount", 0) or 0))
    if ag_disc > 0:
        c.text_lr("Desc. convenio:", f"-{_clp(ag_disc)}", fS, gap=5)
    if foot.get("show_total"):
        c.spacer(4)
        c.text_lr("TOTAL:", _clp(payload.get("total", 0)), fB, gap=6)
        c.spacer(4)

    # ── Pie compartido ────────────────────────────────────────────────────────
    _sec_payment(ctx, payload)
    _sec_agreement(ctx, payload)
    _sec_email(ctx, payload)
    _sec_footer_msg(ctx)
    _sec_reprint(ctx, payload)
    _sec_barcode(ctx, payload)
    c.spacer(4)
    return c.render()


def render_devolucion(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de devolución: muestra los productos devueltos y el total a reembolsar."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    foot = ctx["foot"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    # ── Encabezado ───────────────────────────────────────────────────────────
    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "TICKET DE DEVOLUCIÓN")

    # ── Productos devueltos ───────────────────────────────────────────────────
    return_items = payload.get("return_items", [])
    c.spacer(6); c.separator(); c.spacer(4)
    c.text("Productos devueltos", fB, align="center", gap=5); c.spacer(4)
    _sec_items(ctx, return_items)

    c.separator(); c.spacer(4)

    # ── Totales de la devolución ──────────────────────────────────────────────
    refund_total = Decimal(str(payload.get("refund_total", 0) or 0))

    if foot.get("show_subtotal"):
        c.text_lr("Subtotal devuelto:", _clp(payload.get("subtotal", 0)), fS, gap=5)
    if foot.get("show_tax"):
        c.text_lr("IVA (19%):", _clp(payload.get("tax", 0)), fS, gap=5)
    if foot.get("show_total"):
        c.spacer(4)
        c.text_lr("TOTAL DEVUELTO:", _clp(refund_total), fB, gap=6)
        c.spacer(4)

    # ── Pie compartido ────────────────────────────────────────────────────────
    _sec_payment(ctx, payload)
    _sec_agreement(ctx, payload)
    _sec_email(ctx, payload)
    _sec_footer_msg(ctx)
    _sec_reprint(ctx, payload)
    _sec_barcode(ctx, payload)
    c.spacer(4)
    return c.render()


def render_cambio(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de cambio/devolución: sección Devuelto + Recibido + totales propios."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    body = ctx["body"]
    foot = ctx["foot"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    # ── Encabezado ───────────────────────────────────────────────────────────
    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "CAMBIO DE PRODUCTO")

    # ── Devuelto ──────────────────────────────────────────────────────────────
    credit_items = payload.get("exchange_credit_items", [])
    if credit_items and body.get("show_credit_section", True):
        c.spacer(6); c.separator(); c.spacer(4)
        c.text("Devuelto", fB, align="center", gap=5); c.spacer(4)
        _sec_items(ctx, credit_items)

    # ── Recibido ──────────────────────────────────────────────────────────────
    c.spacer(6); c.separator(); c.spacer(4)
    if body.get("show_received_section", True):
        c.text("Recibido", fB, align="center", gap=5); c.spacer(4)
    _sec_items(ctx, payload.get("items", []))

    c.separator(); c.spacer(4)

    # ── Totales del cambio ────────────────────────────────────────────────────
    exchange_credit = Decimal(str(payload.get("exchange_credit", 0) or 0))
    net_total       = Decimal(str(payload.get("total",           0) or 0))

    if foot.get("show_subtotal"):
        c.text_lr("Subtotal recibido:", _clp(payload.get("subtotal", 0)), fS, gap=5)
    if foot.get("show_tax"):
        c.text_lr("IVA (19%):", _clp(payload.get("tax", 0)), fS, gap=5)
    if exchange_credit > 0:
        c.text_lr("Crédito devuelto:", f"-{_clp(exchange_credit)}", fS, gap=5)
    if foot.get("show_total"):
        c.spacer(4)
        total_label = "Sin cobro adicional" if net_total <= 0 else _clp(net_total)
        c.text_lr("TOTAL:", total_label, fB, gap=6)
        c.spacer(4)

    # ── Pie compartido ────────────────────────────────────────────────────────
    _sec_payment(ctx, payload, net_total=net_total)
    _sec_agreement(ctx, payload)
    _sec_email(ctx, payload)
    _sec_footer_msg(ctx)
    _sec_reprint(ctx, payload)
    _sec_barcode(ctx, payload)
    c.spacer(4)
    return c.render()


def render_apertura(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de apertura de caja: datos de la sesión y monto inicial."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    body = ctx["body"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "APERTURA DE CAJA")
    c.separator(); c.spacer(4)

    if payload.get("branch_name"):        c.text_lr("Sucursal:",  payload["branch_name"],        fS, gap=4)
    if payload.get("cash_register_name"): c.text_lr("Caja:",      payload["cash_register_name"], fS, gap=4)
    if payload.get("cashier_name"):       c.text_lr("Cajero:",    payload["cashier_name"],        fS, gap=4)
    if payload.get("supervisor_name"):    c.text_lr("Supervisor:", payload["supervisor_name"],    fS, gap=4)

    c.separator(); c.spacer(4)
    c.text_lr("MONTO INICIAL:", _clp(payload.get("initial_amount", 0)), fB, gap=6)
    c.spacer(4)

    if body.get("show_cash_detail"):
        cash_detail = payload.get("cash_detail", [])
        if cash_detail:
            c.separator(); c.spacer(4)
            c.text("Detalle efectivo inicial", fS, align="center", gap=4)
            for d in cash_detail:
                denom = d.get("denomination", 0)
                qty   = d.get("qty", 0)
                tot   = d.get("total", denom * qty)
                c.text_lr(f"  {_clp(denom)} x {qty}", _clp(tot), fS, gap=3)

    if body.get("show_observations"):
        obs = payload.get("observations", "")
        c.separator(); c.spacer(4)
        c.text(f"Obs.: {obs or '—'}", fS, gap=4)

    if body.get("show_signature"):
        c.separator(); c.spacer(4)
        c.text("Firma: ___________________________", fS, align="center", gap=6)

    c.spacer(4)
    return c.render()


def render_arqueo(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de arqueo: ventas acumuladas, ajustes y conteo de efectivo."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    body = ctx["body"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "ARQUEO DE CAJA")
    c.separator(); c.spacer(4)

    if payload.get("branch_name"):        c.text_lr("Sucursal:", payload["branch_name"],        fS, gap=4)
    if payload.get("cash_register_name"): c.text_lr("Caja:",     payload["cash_register_name"], fS, gap=4)
    if payload.get("cashier_name"):       c.text_lr("Cajero:",   payload["cashier_name"],        fS, gap=4)
    c.text_lr("M. inicial:", _clp(payload.get("initial_amount", 0)), fS, gap=4)

    if body.get("show_sales_by_method"):
        c.separator(); c.spacer(4)
        c.text("Ventas por medio de pago", fB, align="center", gap=5)
        for m in payload.get("sales_by_method", []):
            c.text_lr(f"  {m.get('method', '')}:", _clp(m.get("amount", 0)), fS, gap=3)
        c.text_lr("TOTAL VENTAS:", _clp(payload.get("total_sales", 0)), fB, gap=6)

    if body.get("show_adjustments"):
        c.separator(); c.spacer(4)
        w    = Decimal(str(payload.get("withdrawals",   0) or 0))
        dep  = Decimal(str(payload.get("deposits",      0) or 0))
        canc = Decimal(str(payload.get("cancellations", 0) or 0))
        ref  = Decimal(str(payload.get("refunds",       0) or 0))
        if w    > 0: c.text_lr("Retiros:",      f"-{_clp(w)}",    fS, gap=3)
        if dep  > 0: c.text_lr("Ingresos:",      _clp(dep),        fS, gap=3)
        if canc > 0: c.text_lr("Anulaciones:",  f"-{_clp(canc)}", fS, gap=3)
        if ref  > 0: c.text_lr("Devoluciones:", f"-{_clp(ref)}",  fS, gap=3)

    if body.get("show_cash_count"):
        c.separator(); c.spacer(4)
        c.text_lr("Efectivo esperado:", _clp(payload.get("expected_cash", 0)), fS, gap=4)
        c.text_lr("Efectivo contado:",  _clp(payload.get("counted_cash",  0)), fS, gap=4)
        diff = Decimal(str(payload.get("difference", 0) or 0))
        c.text_lr("DIFERENCIA:", _clp(diff), fB, gap=6)

    if body.get("show_observations"):
        obs = payload.get("observations", "")
        c.separator(); c.spacer(4)
        c.text(f"Obs.: {obs or '—'}", fS, gap=4)

    if body.get("show_signature"):
        c.separator(); c.spacer(4)
        c.text("Firma: ___________________________", fS, align="center", gap=6)

    c.spacer(4)
    return c.render()


def render_cierre(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de cierre de caja: resumen completo de la sesión."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    body = ctx["body"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "CIERRE DE CAJA")
    c.separator(); c.spacer(4)

    if payload.get("branch_name"):     c.text_lr("Sucursal:",   payload["branch_name"],     fS, gap=4)
    caja_line = payload.get("cash_register_name", "")
    if payload.get("shift"): caja_line += f" / {payload['shift']}"
    if caja_line:             c.text_lr("Caja:",       caja_line,                   fS, gap=4)
    if payload.get("cashier_name"):    c.text_lr("Cajero:",     payload["cashier_name"],    fS, gap=4)
    if payload.get("supervisor_name"): c.text_lr("Supervisor:", payload["supervisor_name"], fS, gap=4)
    open_d  = payload.get("open_date",  "")
    close_d = payload.get("close_date", "")
    if open_d:  c.text_lr("Apertura:", config_manager.utc_to_local(open_d),  fS, gap=4)
    if close_d: c.text_lr("Cierre:",   config_manager.utc_to_local(close_d), fS, gap=4)

    if body.get("show_sales_by_method"):
        c.separator(); c.spacer(4)
        c.text("Ventas por medio de pago", fB, align="center", gap=5)
        for m in payload.get("sales_by_method", []):
            c.text_lr(f"  {m.get('method', '')}:", _clp(m.get("amount", 0)), fS, gap=3)
        c.text_lr("TOTAL VENTAS:", _clp(payload.get("total_sales", 0)), fB, gap=6)

    if body.get("show_adjustments"):
        c.separator(); c.spacer(4)
        disc = Decimal(str(payload.get("total_discounts",    0) or 0))
        ref  = Decimal(str(payload.get("total_refunds",      0) or 0))
        canc = Decimal(str(payload.get("total_cancellations",0) or 0))
        w    = Decimal(str(payload.get("total_withdrawals",  0) or 0))
        dep  = Decimal(str(payload.get("total_deposits",     0) or 0))
        if disc > 0: c.text_lr("Descuentos:",   f"-{_clp(disc)}", fS, gap=3)
        if ref  > 0: c.text_lr("Devoluciones:", f"-{_clp(ref)}",  fS, gap=3)
        if canc > 0: c.text_lr("Anulaciones:",  f"-{_clp(canc)}", fS, gap=3)
        if w    > 0: c.text_lr("Retiros:",      f"-{_clp(w)}",    fS, gap=3)
        if dep  > 0: c.text_lr("Ingresos:",      _clp(dep),        fS, gap=3)

    if body.get("show_cash_count"):
        c.separator(); c.spacer(4)
        c.text_lr("M. inicial:",        _clp(payload.get("initial_amount",  0)), fS, gap=4)
        c.text_lr("Efectivo esperado:", _clp(payload.get("expected_cash",   0)), fS, gap=4)
        c.text_lr("Efectivo declarado:", _clp(payload.get("declared_cash",   0)), fS, gap=4)
        diff = Decimal(str(payload.get("difference", 0) or 0))
        c.text_lr("DIFERENCIA:", _clp(diff), fB, gap=5)
        status = payload.get("close_status", "")
        if status:
            c.spacer(4)
            c.text(f"Estado: {status}", fB, align="center", gap=6)

    if body.get("show_observations"):
        obs = payload.get("observations", "")
        c.separator(); c.spacer(4)
        c.text(f"Obs.: {obs or '—'}", fS, gap=4)

    if body.get("show_signature"):
        c.separator(); c.spacer(4)
        c.text("Cajero: ___________________________",    fS, align="center", gap=4)
        c.text("Supervisor: _______________________",    fS, align="center", gap=6)

    c.spacer(4)
    return c.render()


def render_anulacion(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de anulación de venta: folio original, motivo, autorizador y estado."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    body = ctx["body"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "ANULACIÓN DE VENTA")
    c.separator(); c.spacer(4)

    if payload.get("branch_name"):        c.text_lr("Sucursal:", payload["branch_name"],        fS, gap=4)
    if payload.get("cash_register_name"): c.text_lr("Caja:",     payload["cash_register_name"], fS, gap=4)
    if payload.get("shift"):              c.text_lr("Turno:",    payload["shift"],               fS, gap=4)
    if payload.get("cashier_name"):       c.text_lr("Cajero:",   payload["cashier_name"],        fS, gap=4)
    if body.get("show_original_folio", True):
        c.text_lr("Folio original:", payload.get("original_folio", "—"), fS, gap=4)

    c.separator(); c.spacer(4)
    c.text_lr("MONTO ANULADO:", _clp(payload.get("cancelled_amount", 0)), fB, gap=6)
    c.spacer(4)

    if body.get("show_payment_method", True):
        method = payload.get("payment_method", "")
        if method: c.text_lr("Medio de pago:", method, fS, gap=4)

    if body.get("show_reason", True):
        c.separator(); c.spacer(4)
        c.text(f"Motivo: {payload.get('reason', '—')}", fS, gap=4)

    if body.get("show_authorizer", True):
        auth = payload.get("authorizer_name", "")
        if auth: c.text_lr("Autorizador:", auth, fS, gap=4)

    if body.get("show_status", True):
        status = payload.get("cancellation_status", "")
        c.separator(); c.spacer(4)
        c.text(f"Estado: {status or '—'}", fB, align="center", gap=6)

    c.spacer(4)
    return c.render()


def render_retiro(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de retiro de efectivo: monto, receptor, efectivo antes/después."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    body = ctx["body"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "RETIRO DE EFECTIVO")
    c.separator(); c.spacer(4)

    if payload.get("branch_name"):        c.text_lr("Sucursal:", payload["branch_name"],        fS, gap=4)
    if payload.get("cash_register_name"): c.text_lr("Caja:",     payload["cash_register_name"], fS, gap=4)
    if payload.get("shift"):              c.text_lr("Turno:",    payload["shift"],               fS, gap=4)
    if payload.get("cashier_name"):       c.text_lr("Cajero:",   payload["cashier_name"],        fS, gap=4)

    c.separator(); c.spacer(4)
    c.text_lr("MONTO RETIRADO:", _clp(payload.get("amount", 0)), fB, gap=6)
    c.spacer(4)
    c.text(f"Motivo: {payload.get('reason', '—')}", fS, gap=4)

    if body.get("show_receiver", True):
        recv = payload.get("receiver_name", "")
        if recv: c.text_lr("Recibe:", recv, fS, gap=4)
    if body.get("show_authorizer", True):
        auth = payload.get("authorizer_name", "")
        if auth: c.text_lr("Supervisor:", auth, fS, gap=4)

    if body.get("show_cash_before_after", True):
        c.separator(); c.spacer(4)
        c.text_lr("Efectivo antes:",   _clp(payload.get("cash_before", 0)), fS, gap=4)
        c.text_lr("Efectivo después:", _clp(payload.get("cash_after",  0)), fS, gap=4)

    if body.get("show_observations", True):
        obs = payload.get("observations", "")
        c.separator(); c.spacer(4)
        c.text(f"Obs.: {obs or '—'}", fS, gap=4)

    if body.get("show_signature", True):
        c.separator(); c.spacer(4)
        c.text("Firma: ___________________________", fS, align="center", gap=6)

    c.spacer(4)
    return c.render()


def render_ingreso(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de ingreso manual de efectivo: monto, origen, efectivo antes/después."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    body = ctx["body"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "INGRESO DE EFECTIVO")
    c.separator(); c.spacer(4)

    if payload.get("branch_name"):        c.text_lr("Sucursal:", payload["branch_name"],        fS, gap=4)
    if payload.get("cash_register_name"): c.text_lr("Caja:",     payload["cash_register_name"], fS, gap=4)
    if payload.get("shift"):              c.text_lr("Turno:",    payload["shift"],               fS, gap=4)
    if payload.get("cashier_name"):       c.text_lr("Cajero:",   payload["cashier_name"],        fS, gap=4)

    c.separator(); c.spacer(4)
    c.text_lr("MONTO INGRESADO:", _clp(payload.get("amount", 0)), fB, gap=6)
    c.spacer(4)
    c.text(f"Motivo: {payload.get('reason', '—')}", fS, gap=4)

    if body.get("show_deliverer", True):
        dlv = payload.get("deliverer_name", "")
        if dlv: c.text_lr("Entrega:", dlv, fS, gap=4)
    if body.get("show_authorizer", True):
        auth = payload.get("authorizer_name", "")
        if auth: c.text_lr("Supervisor:", auth, fS, gap=4)

    if body.get("show_cash_before_after", True):
        c.separator(); c.spacer(4)
        c.text_lr("Efectivo antes:",   _clp(payload.get("cash_before", 0)), fS, gap=4)
        c.text_lr("Efectivo después:", _clp(payload.get("cash_after",  0)), fS, gap=4)

    if body.get("show_observations", True):
        obs = payload.get("observations", "")
        c.separator(); c.spacer(4)
        c.text(f"Obs.: {obs or '—'}", fS, gap=4)

    if body.get("show_signature", True):
        c.separator(); c.spacer(4)
        c.text("Firma: ___________________________", fS, align="center", gap=6)

    c.spacer(4)
    return c.render()


def render_gasto(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de gasto menor: concepto, proveedor, efectivo antes/después."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    body = ctx["body"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "GASTO MENOR")
    c.separator(); c.spacer(4)

    if payload.get("branch_name"):        c.text_lr("Sucursal:", payload["branch_name"],        fS, gap=4)
    if payload.get("cash_register_name"): c.text_lr("Caja:",     payload["cash_register_name"], fS, gap=4)
    if payload.get("shift"):              c.text_lr("Turno:",    payload["shift"],               fS, gap=4)
    if payload.get("cashier_name"):       c.text_lr("Cajero:",   payload["cashier_name"],        fS, gap=4)

    c.separator(); c.spacer(4)
    c.text_lr("MONTO:", _clp(payload.get("amount", 0)), fB, gap=6)
    c.spacer(4)
    c.text(f"Concepto: {payload.get('concept', '—')}", fS, gap=4)

    if body.get("show_supplier", True):
        sup = payload.get("supplier", "")
        if sup: c.text_lr("Proveedor:", sup, fS, gap=4)
    if body.get("show_associated_doc", False):
        doc = payload.get("associated_doc", "")
        if doc: c.text_lr("Doc. asociado:", doc, fS, gap=4)
    if body.get("show_authorizer", True):
        auth = payload.get("authorizer_name", "")
        if auth: c.text_lr("Supervisor:", auth, fS, gap=4)

    if body.get("show_cash_before_after", True):
        c.separator(); c.spacer(4)
        c.text_lr("Efectivo antes:",   _clp(payload.get("cash_before", 0)), fS, gap=4)
        c.text_lr("Efectivo después:", _clp(payload.get("cash_after",  0)), fS, gap=4)

    if body.get("show_observations", True):
        obs = payload.get("observations", "")
        c.separator(); c.spacer(4)
        c.text(f"Obs.: {obs or '—'}", fS, gap=4)

    if body.get("show_signature", True):
        c.separator(); c.spacer(4)
        c.text("Firma: ___________________________", fS, align="center", gap=6)

    c.spacer(4)
    return c.render()


def render_reporte_x(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de reporte X: corte parcial informativo sin cerrar caja."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    body = ctx["body"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "REPORTE X — CORTE PARCIAL")
    c.separator(); c.spacer(4)

    if payload.get("branch_name"):        c.text_lr("Sucursal:", payload["branch_name"],        fS, gap=4)
    if payload.get("cash_register_name"): c.text_lr("Caja:",     payload["cash_register_name"], fS, gap=4)
    if payload.get("shift"):              c.text_lr("Turno:",    payload["shift"],               fS, gap=4)
    if payload.get("cashier_name"):       c.text_lr("Cajero:",   payload["cashier_name"],        fS, gap=4)
    open_d = payload.get("open_date", "")
    if open_d: c.text_lr("Apertura:", config_manager.utc_to_local(open_d), fS, gap=4)

    if body.get("show_sales_by_method", True):
        c.separator(); c.spacer(4)
        c.text("Ventas por medio de pago", fB, align="center", gap=5)
        for m in payload.get("sales_by_method", []):
            c.text_lr(f"  {m.get('method', '')}:", _clp(m.get("amount", 0)), fS, gap=3)
        c.text_lr("TOTAL VENTAS:", _clp(payload.get("total_sales", 0)), fB, gap=6)

    c.separator(); c.spacer(4)
    if body.get("show_cancellations", True):
        v = Decimal(str(payload.get("total_cancellations", 0) or 0))
        c.text_lr("Anulaciones:", f"-{_clp(v)}", fS, gap=3)
    if body.get("show_refunds", True):
        v = Decimal(str(payload.get("total_refunds", 0) or 0))
        c.text_lr("Devoluciones:", f"-{_clp(v)}", fS, gap=3)
    if body.get("show_exchanges", True):
        v = Decimal(str(payload.get("total_exchanges", 0) or 0))
        if v: c.text_lr("Cambios:", _clp(v), fS, gap=3)
    if body.get("show_withdrawals", True):
        v = Decimal(str(payload.get("total_withdrawals", 0) or 0))
        if v: c.text_lr("Retiros:", f"-{_clp(v)}", fS, gap=3)
    if body.get("show_deposits", True):
        v = Decimal(str(payload.get("total_deposits", 0) or 0))
        if v: c.text_lr("Ingresos:", _clp(v), fS, gap=3)
    if body.get("show_expenses", True):
        v = Decimal(str(payload.get("total_expenses", 0) or 0))
        if v: c.text_lr("Gastos:", f"-{_clp(v)}", fS, gap=3)

    if body.get("show_cash_count", False):
        c.separator(); c.spacer(4)
        c.text_lr("Efectivo esperado:", _clp(payload.get("expected_cash", 0)), fS, gap=4)
        c.text_lr("Efectivo contado:",  _clp(payload.get("counted_cash",  0)), fS, gap=4)
        diff = Decimal(str(payload.get("difference", 0) or 0))
        c.text_lr("DIFERENCIA:", _clp(diff), fB, gap=6)
    else:
        c.separator(); c.spacer(4)
        c.text_lr("Efectivo esperado:", _clp(payload.get("expected_cash", 0)), fB, gap=6)

    c.spacer(4)
    return c.render()


def render_reporte_z(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de reporte Z: cierre consolidado del periodo operativo."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    body = ctx["body"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    _sec_header(ctx, payload)
    _sec_doc_id(ctx, payload, "REPORTE Z")
    c.separator(); c.spacer(4)

    if payload.get("period"):             c.text_lr("Periodo:",  payload["period"],              fS, gap=4)
    if payload.get("branch_name"):        c.text_lr("Sucursal:", payload["branch_name"],         fS, gap=4)
    if payload.get("cash_register_name"): c.text_lr("Caja:",     payload["cash_register_name"],  fS, gap=4)
    if payload.get("shift"):              c.text_lr("Turno:",    payload["shift"],                fS, gap=4)
    if payload.get("responsible_name"):   c.text_lr("Responsable:", payload["responsible_name"], fS, gap=4)

    if body.get("show_sales_by_method", True):
        c.separator(); c.spacer(4)
        c.text("Ventas por medio de pago", fB, align="center", gap=5)
        for m in payload.get("sales_by_method", []):
            c.text_lr(f"  {m.get('method', '')}:", _clp(m.get("amount", 0)), fS, gap=3)
        c.text_lr("TOTAL BRUTO:", _clp(payload.get("gross_total", 0)), fB, gap=6)

    if body.get("show_cancellations", True):
        c.separator(); c.spacer(4)
        disc = Decimal(str(payload.get("total_discounts",    0) or 0))
        ref  = Decimal(str(payload.get("total_refunds",      0) or 0))
        canc = Decimal(str(payload.get("total_cancellations",0) or 0))
        if disc > 0: c.text_lr("Descuentos:",   f"-{_clp(disc)}", fS, gap=3)
        if ref  > 0: c.text_lr("Devoluciones:", f"-{_clp(ref)}",  fS, gap=3)
        if canc > 0: c.text_lr("Anulaciones:",  f"-{_clp(canc)}", fS, gap=3)
        c.text_lr("TOTAL NETO:", _clp(payload.get("net_total", 0)), fB, gap=5)
        tax = Decimal(str(payload.get("tax", 0) or 0))
        if tax > 0: c.text_lr("IVA (19%):", _clp(tax), fS, gap=4)

    if body.get("show_transaction_count", True):
        c.separator(); c.spacer(4)
        c.text_lr("Transacciones:", str(payload.get("transaction_count", 0)), fS, gap=4)
        c.text_lr("Productos:",     str(payload.get("product_count",     0)), fS, gap=4)

    if body.get("show_adjustments", True):
        c.separator(); c.spacer(4)
        w   = Decimal(str(payload.get("total_withdrawals", 0) or 0))
        dep = Decimal(str(payload.get("total_deposits",    0) or 0))
        exp = Decimal(str(payload.get("total_expenses",    0) or 0))
        if w   > 0: c.text_lr("Retiros:", f"-{_clp(w)}",   fS, gap=3)
        if dep > 0: c.text_lr("Ingresos:", _clp(dep),       fS, gap=3)
        if exp > 0: c.text_lr("Gastos:",  f"-{_clp(exp)}",  fS, gap=3)

    if body.get("show_cash_count", True):
        c.separator(); c.spacer(4)
        c.text_lr("Efectivo esperado:",  _clp(payload.get("expected_cash",  0)), fS, gap=4)
        c.text_lr("Efectivo declarado:", _clp(payload.get("declared_cash",  0)), fS, gap=4)
        diff = Decimal(str(payload.get("difference", 0) or 0))
        c.text_lr("DIFERENCIA:", _clp(diff), fB, gap=5)
        status = payload.get("close_status", "")
        if status:
            c.spacer(4)
            c.text(f"Estado: {status}", fB, align="center", gap=6)

    c.spacer(4)
    return c.render()


def render_prueba(payload: dict, template: dict, font_name: str = "calibri", font_size: int = 18) -> Optional[Image.Image]:
    """Ticket de prueba: layout real con 3 productos de muestra, marcado claramente como prueba."""
    if not PIL_AVAILABLE:
        return None

    ctx  = _init_render(template, font_name, font_size)
    c    = ctx["canvas"]
    foot = ctx["foot"]
    fB   = ctx["fonts"]["bold"]
    fS   = ctx["fonts"]["small"]

    # ── Encabezado empresa ────────────────────────────────────────────────────
    _sec_header(ctx, payload)

    # ── Banner de prueba prominente ───────────────────────────────────────────
    c.spacer(4); c.separator(); c.spacer(4)
    c.text("*** TICKET DE PRUEBA ***", fB, align="center", gap=5)
    c.text("NO ES UNA VENTA REAL", fS, align="center", gap=4)
    c.separator(); c.spacer(4)

    _sec_doc_id(ctx, payload, "TICKET DE PRUEBA")

    # ── Productos de muestra ──────────────────────────────────────────────────
    c.spacer(6); c.separator(); c.spacer(4)
    _sec_items(ctx, payload.get("items", []))
    c.separator(); c.spacer(4)

    # ── Totales ───────────────────────────────────────────────────────────────
    if foot.get("show_subtotal"):
        c.text_lr("Subtotal (neto):", _clp(payload.get("subtotal", 0)), fS, gap=5)
    if foot.get("show_tax"):
        c.text_lr("IVA (19%):", _clp(payload.get("tax", 0)), fS, gap=5)
    if foot.get("show_total"):
        c.spacer(4)
        c.text_lr("TOTAL:", _clp(payload.get("total_amount", 0)), fB, gap=6)
        c.spacer(4)

    # ── Info diagnóstico ──────────────────────────────────────────────────────
    c.separator(); c.spacer(4)
    c.text(f"Template:  {payload.get('template_code', '—')}  v{payload.get('template_version', '—')}", fS, gap=4)
    c.text(f"Fuente:    {font_name}  {font_size}px", fS, gap=4)
    c.text(f"Impres.:   {payload.get('printer_name', '—')}", fS, gap=4)
    c.separator(); c.spacer(4)
    c.text("Si ves este ticket,", fS, align="center", gap=3)
    c.text("el agente funciona OK.", fB, align="center", gap=6)
    c.spacer(4)
    return c.render()

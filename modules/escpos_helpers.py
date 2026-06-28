"""
Funciones de formateo ESC/POS compartidas entre módulos de ticket.
Ancho estándar: 80mm = 48 columnas font A, 58mm = 32 col font A / 42 col font B.
"""
from decimal import Decimal

import config_manager

COLS = 48  # columnas para 80mm font A (default)


def get_cols(paper_width_mm: int) -> int:
    """Retorna columnas según ancho de papel (Font A/B tienen misma anchura en la mayoría de impresoras)."""
    return 32 if paper_width_mm == 58 else 48


def clp(value) -> str:
    """Formatea un valor numérico como pesos chilenos."""
    try:
        amount = int(Decimal(str(value or 0)))
        return f"$ {amount:,}".replace(",", ".")
    except Exception:
        return str(value)


def line_lr(left: str, right: str, width: int = COLS) -> str:
    """Línea con texto izquierda y derecha alineados."""
    space = width - len(left) - len(right)
    return left + " " * max(1, space) + right


def separator(char: str = "-", width: int = COLS) -> str:
    return char * width


def center_text(text: str, width: int = COLS) -> str:
    return text.center(width)


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."  # ASCII: seguro en cualquier codepage de impresora


def print_header(printer, payload: dict, cfg: dict, cols: int = COLS) -> None:
    """Imprime la sección de encabezado según la configuración del template."""
    company = payload.get("company", {})

    # Nombre comercial en Font A bold (debe destacar)
    if cfg.get("show_commercial_name"):
        name = company.get("name") or company.get("commercial_name", "")
        if name:
            printer.set(align="center", bold=True, double_height=False, double_width=False, font="a")
            printer.text(f"{truncate(name, cols)}\n")

    # Datos secundarios del header en Font B (más compacto)
    printer.set(align="center", bold=False, double_height=False, double_width=False, font="b")

    if cfg.get("show_fantasy_name"):
        fantasy = company.get("fantasy_name", "")
        if fantasy:
            printer.text(f"{truncate(fantasy, cols)}\n")

    if cfg.get("show_rut"):
        rut = company.get("rut", "")
        if rut:
            printer.text(f"RUT: {rut}\n")

    if cfg.get("show_date"):
        date_val = payload.get("sale_date") or payload.get("print_date", "")
        date_str = config_manager.utc_to_local(date_val)
        reprint_date = payload.get("reprint_date")
        if reprint_date:
            date_str += f"\nReimpresión: {config_manager.utc_to_local(reprint_date)}"
        printer.text(f"{date_str}\n")

    printer.set(align="left", font="a")
    printer.text(separator(width=cols) + "\n")


def print_items(printer, payload: dict, cfg: dict, cols: int = COLS, font: str = "a") -> None:
    """Imprime el listado de productos."""
    items = payload.get("items", [])
    show_unit_price = cfg.get("show_unit_price", False)
    show_discount = cfg.get("show_discount", True)

    for item in items:
        qty = int(item.get("quantity", 1))
        total_val = Decimal(str(item.get("total", 0) or 0))
        unit_val = Decimal(str(item.get("unit_price", 0) or 0))
        discount_pct = Decimal(str(item.get("discount_percent", 0) or 0))

        printer.set(bold=False, double_height=False, double_width=False, font=font)

        # Línea 1: nombre del producto (ocupa toda la línea)
        name = truncate(item.get("name", ""), cols)
        printer.text(f"{name}\n")

        # Línea 2: qty × precio unitario (izq) + total (der) — siempre cabe en 32 cols
        qty_label = f"  x{qty}"
        if show_unit_price:
            qty_label = f"  x{qty} {clp(unit_val)}"
        printer.text(line_lr(qty_label, clp(total_val), width=cols) + "\n")

        # Línea 3: descuento en monto (opcional)
        if show_discount and discount_pct > 0:
            disc_amount = (unit_val * qty) - total_val
            if disc_amount > 0:
                printer.text(f"  Desc: -{clp(disc_amount)}\n")

    printer.text(separator(width=cols) + "\n")


def print_totals(printer, payload: dict, cfg: dict, cols: int = COLS) -> None:
    """Imprime el bloque de totalizaciones."""
    # Subtotal, IVA, descuentos en Font B (secundario)
    printer.set(font="b", bold=False, double_height=False, double_width=False)

    if cfg.get("show_subtotal"):
        printer.text(line_lr("Subtotal (neto):", clp(payload.get("subtotal", 0)), width=cols) + "\n")

    if cfg.get("show_tax"):
        printer.text(line_lr("IVA (19%):", clp(payload.get("tax", 0)), width=cols) + "\n")

    if cfg.get("show_discounts"):
        disc = Decimal(str(payload.get("line_discount", 0) or 0))
        doc_disc = Decimal(str(payload.get("document_discount", 0) or 0))
        total_disc = disc + doc_disc
        if total_disc > 0:
            printer.text(line_lr("Descuentos:", f"-{clp(total_disc)}", width=cols) + "\n")

    # TOTAL en Font A bold (lo más importante del ticket)
    if cfg.get("show_total"):
        printer.set(bold=True, font="a", double_height=False, double_width=False)
        printer.text(line_lr("TOTAL:", clp(payload.get("total", 0)), width=cols) + "\n")
        printer.set(bold=False, font="b")

    if cfg.get("show_payment_method"):
        method = payload.get("payment_method", "")
        if method:
            printer.text(line_lr("Pago:", method, width=cols) + "\n")

    if cfg.get("show_change"):
        change = Decimal(str(payload.get("change", 0) or 0))
        printer.text(line_lr("Vuelto:", clp(change), width=cols) + "\n")


def print_barcode(printer, payload: dict, cfg: dict, cols: int = COLS) -> None:
    """Imprime código de barras si está configurado."""
    if not cfg.get("show_barcode"):
        return

    field = cfg.get("barcode_field", "ticket_number")
    value = str(payload.get(field, "")).strip()

    # Si el campo configurado es un UUID u otro valor largo, usar ticket_number
    if not value or len(value) > 20:
        value = str(payload.get("ticket_number", "")).strip()

    if not value:
        return

    bc_width = 2  # mínimo seguro para CODE128 en XP-58 y XP-80

    try:
        printer.set(align="center")
        printer.barcode(value, "CODE128", height=64, width=bc_width, pos="BELOW")
        printer.set(align="left")
    except Exception:
        printer.set(align="center")
        printer.text(f"\n[{value}]\n")
        printer.set(align="left")


def print_footer_message(printer, cfg: dict) -> None:
    msg = cfg.get("footer_message", "")
    if msg:
        printer.set(align="center", font="a", bold=False, double_height=False, double_width=False)
        printer.text(f"\n{msg}\n")
        printer.set(align="left", font="a")

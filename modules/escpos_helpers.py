"""
Funciones de formateo ESC/POS compartidas entre módulos de ticket.
Ancho estándar 80mm = 48 caracteres en fuente A.
"""
from decimal import Decimal

COLS = 48  # columnas para 80mm


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
    return text[: max_len - 1] + "…"


def print_header(printer, payload: dict, cfg: dict) -> None:
    """Imprime la sección de encabezado según la configuración del template."""
    company = payload.get("company", {})

    printer.set(align="center")

    if cfg.get("show_commercial_name"):
        name = company.get("commercial_name") or company.get("name", "")
        if name:
            printer.set(bold=True, double_height=True, double_width=False)
            printer.text(f"{truncate(name, 24)}\n")
            printer.set(bold=False, double_height=False)

    if cfg.get("show_fantasy_name"):
        fantasy = company.get("fantasy_name", "")
        if fantasy:
            printer.text(f"{truncate(fantasy, COLS)}\n")

    if cfg.get("show_rut"):
        rut = company.get("rut", "")
        if rut:
            printer.text(f"RUT: {rut}\n")

    if cfg.get("show_date"):
        date_str = payload.get("print_date", "")[:19].replace("T", " ")
        printer.text(f"{date_str}\n")

    printer.set(align="left")
    printer.text(separator() + "\n")


def print_items(printer, payload: dict, cfg: dict) -> None:
    """Imprime el listado de productos."""
    items = payload.get("items", [])
    show_unit_price = cfg.get("show_unit_price", False)
    show_discount = cfg.get("show_discount", True)

    for item in items:
        name = truncate(item.get("name", ""), COLS - 12)
        qty = int(item.get("quantity", 1))
        total = clp(item.get("total", 0))
        discount_pct = Decimal(str(item.get("discount_percent", 0)))

        printer.set(bold=False)
        printer.text(f"{name}\n")

        if show_unit_price:
            unit_price = clp(item.get("unit_price", 0))
            printer.text(f"  {qty} x {unit_price}\n")

        line = line_lr(f"  x{qty}", total)
        printer.text(line + "\n")

        if show_discount and discount_pct > 0:
            printer.text(f"  Dcto {discount_pct}%\n")

    printer.text(separator() + "\n")


def print_totals(printer, payload: dict, cfg: dict) -> None:
    """Imprime el bloque de totalizaciones."""
    if cfg.get("show_subtotal"):
        printer.text(line_lr("  Neto", clp(payload.get("subtotal", 0))) + "\n")

    if cfg.get("show_discounts"):
        disc = Decimal(str(payload.get("line_discount", 0) or 0))
        doc_disc = Decimal(str(payload.get("document_discount", 0) or 0))
        total_disc = disc + doc_disc
        if total_disc > 0:
            printer.text(line_lr("  Descuentos", f"-{clp(total_disc)}") + "\n")

    if cfg.get("show_tax"):
        printer.text(line_lr("  IVA (19%)", clp(payload.get("tax", 0))) + "\n")

    if cfg.get("show_total"):
        printer.set(bold=True)
        printer.text(separator("=") + "\n")
        printer.text(line_lr("  TOTAL", clp(payload.get("total", 0))) + "\n")
        printer.set(bold=False)
        printer.text(separator("=") + "\n")

    if cfg.get("show_payment_method"):
        method = payload.get("payment_method", "")
        if method:
            printer.text(line_lr("  Medio de pago", method) + "\n")

    if cfg.get("show_change"):
        change = Decimal(str(payload.get("change", 0) or 0))
        if change > 0:
            printer.text(line_lr("  Vuelto", clp(change)) + "\n")


def print_barcode(printer, payload: dict, cfg: dict) -> None:
    """Imprime código de barras si está configurado."""
    if not cfg.get("show_barcode"):
        return
    field = cfg.get("barcode_field", "ticket_number")
    value = str(payload.get(field, "")).strip()
    if not value:
        return
    try:
        printer.set(align="center")
        printer.barcode(value, "CODE128", height=64, width=2, pos="BELOW")
        printer.set(align="left")
    except Exception:
        # Si el barcode falla, imprime el valor como texto
        printer.set(align="center")
        printer.text(f"\n[{value}]\n")
        printer.set(align="left")


def print_footer_message(printer, cfg: dict) -> None:
    msg = cfg.get("footer_message", "")
    if msg:
        printer.set(align="center")
        printer.text(f"\n{msg}\n")
        printer.set(align="left")

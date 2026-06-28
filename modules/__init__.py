"""
Módulos de ticket para el agente de impresión.
Cada módulo expone una función render(printer, payload, template).
"""
import importlib
import logging

logger = logging.getLogger("agent.modules")

_MODULE_MAP = {
    "TICKET_VENTA":      "modules.ticket_venta",
    "TICKET_CAMBIO":     "modules.ticket_cambio",
    "TICKET_DEVOLUCION": "modules.ticket_devolucion",
    "TICKET_PRUEBA":     "modules.ticket_prueba",
}


def render(ticket_type: str, printer, payload: dict, template: dict) -> None:
    """Despacha el renderizado al módulo correspondiente."""
    module_path = _MODULE_MAP.get(ticket_type)
    if not module_path:
        raise ValueError(f"Tipo de ticket desconocido: {ticket_type}")
    mod = importlib.import_module(module_path)
    mod.render(printer, payload, template)

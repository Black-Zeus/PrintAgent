# TODO — Tipos de ticket: estado de implementación

## Estado general por tipo

| Tipo                | Renderer PIL | Módulo | Backend enum | Frontend editor | Cableado en sistema |
|---------------------|:------------:|:------:|:------------:|:---------------:|:-------------------:|
| TICKET_VENTA        | ✅           | ✅     | ✅           | ✅              | ✅                  |
| TICKET_CAMBIO       | ✅           | ✅     | ✅           | ✅              | ✅                  |
| TICKET_DEVOLUCION   | ✅           | ✅     | ✅           | ✅              | ✅                  |
| TICKET_PRUEBA       | ✅           | ✅     | ✅           | ✅              | ✅ (botón agente)   |
| TICKET_APERTURA     | ✅           | ✅     | ✅           | ✅              | ⏳ pendiente        |
| TICKET_ARQUEO       | ✅           | ✅     | ✅           | ✅              | ⏳ pendiente        |
| TICKET_CIERRE       | ✅           | ✅     | ✅           | ✅              | ⏳ pendiente        |
| TICKET_ANULACION    | ✅           | ✅     | ✅           | ✅              | ⏳ pendiente        |
| TICKET_RETIRO       | ✅           | ✅     | ✅           | ✅              | ⏳ pendiente        |
| TICKET_INGRESO      | ✅           | ✅     | ✅           | ✅              | ⏳ pendiente        |
| TICKET_GASTO        | ✅           | ✅     | ✅           | ✅              | ⏳ pendiente        |
| TICKET_REPORTE_X    | ✅           | ✅     | ✅           | ✅              | ⏳ pendiente        |
| TICKET_REPORTE_Z    | ✅           | ✅     | ✅           | ✅              | ⏳ pendiente        |

---

## Tipos completamente implementados

### TICKET_VENTA / TICKET_CAMBIO / TICKET_DEVOLUCION
Cableados al sistema de ventas. Se emiten automáticamente al completar la transacción.

### TICKET_PRUEBA
Emitido desde el portal del agente (botón "Imprimir ticket de prueba"). No genera venta real.
Usa 3 productos de muestra, muestra info de diagnóstico (template, fuente, impresora).

---

## Tipos con lógica de impresión lista — pendientes de cablear al sistema

### TICKET_APERTURA
- ✅ Renderer PIL (`render_apertura`)
- ✅ Módulo (`ticket_apertura.py`)
- ✅ Enum backend + migración DDL
- ✅ Editor de template (preview, toggles: detalle efectivo, observaciones, firma)
- ⏳ **Falta cablear**: disparar desde el flujo de apertura de sesión de caja en el sistema.
  Payload requerido: `session_folio`, `branch_name`, `cash_register_name`, `cashier_name`,
  `supervisor_name` (opcional), `initial_amount`, `cash_detail[]`, `observations`.

### TICKET_ARQUEO
- ✅ Renderer PIL (`render_arqueo`)
- ✅ Módulo (`ticket_arqueo.py`)
- ✅ Enum backend + migración DDL
- ✅ Editor de template (preview, toggles: ventas por MP, ajustes, conteo efectivo, firma)
- ⏳ **Falta cablear**: disparar desde la acción de arqueo intermedio.
  Payload requerido: `session_folio`, `branch_name`, `cash_register_name`, `cashier_name`,
  `initial_amount`, `total_sales`, `sales_by_method[]`, `withdrawals`, `deposits`,
  `cancellations`, `refunds`, `expected_cash`, `counted_cash`, `difference`, `observations`.

### TICKET_CIERRE
- ✅ Renderer PIL (`render_cierre`)
- ✅ Módulo (`ticket_cierre.py`)
- ✅ Enum backend + migración DDL
- ✅ Editor de template (preview, toggles: ventas por MP, ajustes, conteo, firmas cajero/supervisor)
- ⏳ **Falta cablear**: disparar desde el flujo de cierre de sesión de caja.
  Payload requerido: `session_folio`, `branch_name`, `cash_register_name`, `shift`,
  `cashier_name`, `supervisor_name`, `open_date`, `close_date`, `total_sales`,
  `sales_by_method[]`, `total_discounts`, `total_refunds`, `total_cancellations`,
  `initial_amount`, `total_withdrawals`, `total_deposits`, `expected_cash`,
  `declared_cash`, `difference`, `close_status`, `observations`.

---

## Tipos con lógica de impresión lista — pendientes de cablear al sistema (nuevos)

### TICKET_ANULACION
Payload requerido: `session_folio`, `original_folio`, `branch_name`, `cash_register_name`, `shift`,
`cashier_name`, `authorizer_name`, `reason`, `cancelled_amount`, `payment_method`, `cancellation_status`.
Toggles: folio original, motivo, autorizador, medio de pago, estado.

### TICKET_RETIRO
Payload requerido: `session_folio`, `branch_name`, `cash_register_name`, `shift`, `cashier_name`,
`amount`, `reason`, `receiver_name`, `authorizer_name`, `cash_before`, `cash_after`, `observations`.
Toggles: efectivo antes/después, responsable, autorizador, observaciones, firma.

### TICKET_INGRESO
Payload requerido: `session_folio`, `branch_name`, `cash_register_name`, `shift`, `cashier_name`,
`amount`, `reason`, `deliverer_name`, `authorizer_name`, `cash_before`, `cash_after`, `observations`.
Toggles: efectivo antes/después, responsable que entrega, autorizador, observaciones, firma.

### TICKET_GASTO
Payload requerido: `session_folio`, `branch_name`, `cash_register_name`, `shift`, `cashier_name`,
`amount`, `concept`, `supplier`, `associated_doc`, `authorizer_name`, `cash_before`, `cash_after`, `observations`.
Toggles: proveedor, doc. asociado, autorizador, efectivo antes/después, observaciones, firma.

### TICKET_REPORTE_X
Payload requerido: `report_folio`, `branch_name`, `cash_register_name`, `shift`, `cashier_name`,
`open_date`, `total_sales`, `sales_by_method[]`, `total_cancellations`, `total_refunds`,
`total_exchanges`, `total_withdrawals`, `total_deposits`, `total_expenses`, `expected_cash`,
`counted_cash` (opcional), `difference` (opcional).
Toggles: ventas por MP, anulaciones, devoluciones, cambios, retiros, ingresos, gastos, conteo.
**Regla:** no cierra caja — solo consulta el estado parcial.

### TICKET_REPORTE_Z
Payload requerido: `report_folio`, `period`, `branch_name`, `cash_register_name`, `shift`,
`responsible_name`, `gross_total`, `total_discounts`, `total_refunds`, `total_cancellations`,
`net_total`, `tax`, `sales_by_method[]`, `transaction_count`, `product_count`,
`total_withdrawals`, `total_deposits`, `total_expenses`, `expected_cash`, `declared_cash`,
`difference`, `close_status`.
Toggles: ventas por MP, descuentos/devol./anulaciones, cantidad transacciones, retiros/ingresos/gastos, conteo.
**Distinción con TICKET_CIERRE:** el cierre valida la caja del cajero; el Z consolida el periodo completo.

---

## No quedan tipos pendientes de implementar

Todos los tipos definidos tienen renderer, módulo, enum backend y editor de template.
El único paso restante para cada uno es el **cableado en el sistema**
(disparar el job de impresión en el momento correcto del flujo de negocio).

---

## Checklist para implementar un nuevo tipo

Pasos a seguir para cada tipo pendiente, en orden:

1. **Backend — enum**: agregar valor a `PrintTicketType` en `database/models/print_jobs.py`
2. **Backend — migración**: agregar entrada a `enum_extensions` en `main.py` con `ALTER TABLE`
   que incluya todos los valores acumulados
3. **Frontend — editor** (`AdminPrintTemplates.jsx`):
   - Agregar a `TICKET_TYPES`
   - Crear `DEFAULT_CONTENT_<TIPO>` con los toggles específicos del tipo
   - Crear `SAMPLE_<TIPO>` con datos de ejemplo realistas
   - Actualizar `defaultContentFor()` para retornar el default correcto
   - Agregar flags `is<Tipo>` en `ReceiptPreview` + renderizar preview del tipo
   - Agregar toggles en el panel de cuerpo del `TemplateFormModal` para el nuevo tipo
4. **PrintAgent — renderer**: agregar `render_<tipo>()` en `image_renderer.py`
5. **PrintAgent — módulo**: crear `ticket_<tipo>.py` siguiendo el patrón existente
6. **PrintAgent — dispatcher**: agregar entrada en `_MODULE_MAP` de `modules/__init__.py`
7. **PrintAgent — historial**: agregar badge y opción de filtro en `history.html`
8. **Sistema — cableado**: implementar la lógica que dispara el job de impresión en el
   momento correcto del flujo de negocio (aún no empezado para ningún tipo de caja)

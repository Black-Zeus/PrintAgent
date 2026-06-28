# GestionCom Print Agent

Agente de impresión térmica para el sistema POS GestionCom. Se ejecuta en el equipo Windows donde está conectada la impresora y se comunica con el servidor central para recibir y ejecutar trabajos de impresión.

---

## ¿Cómo funciona?

```
Servidor GestionCom ◄──────────────────────────────────► Print Agent (Windows)
                   POST /print/jobs  →  job pendiente
                   GET  /api/print/agent/jobs/pending  ←  polling c/2s
                   PATCH /api/print/agent/jobs/{code}/status  →  resultado
```

1. El servidor encola un trabajo al generar una venta, cambio o ticket de prueba.
2. El agente hace polling cada 2 segundos consultando `/api/print/agent/jobs/pending`.
3. Al recibir un trabajo, lo ejecuta en la impresora local vía ESC/POS.
4. Informa el resultado (`COMPLETED` / `FAILED`) al servidor.
5. Cada ~2 minutos verifica si el template cambió de versión y lo descarga si es necesario.

---

## Requisitos

| Componente | Versión mínima |
|------------|---------------|
| Windows | 10 / Server 2019 |
| Python | 3.12+ |
| Impresora | Cualquier impresora térmica compatible con ESC/POS y driver Windows instalado |

---

## Estructura del proyecto

```
PrintAgent/
├── agent.py              # Punto de entrada — CLI y arranque
├── poller.py             # Loop de polling y ejecución de trabajos
├── template_manager.py   # Descarga y caché de templates
├── printer.py            # Interfaz ESC/POS (Win32Raw)
├── config_manager.py     # Lectura/escritura de config.json + normalización de URLs
├── service.py            # Wrapper de Windows Service (pywin32)
├── config.json           # Configuración local (generado en instalación)
├── template_cache.json   # Caché del template activo (generado en runtime)
├── requirements.txt      # Dependencias Python
├── install.bat           # Script de instalación para Windows
├── queueclean.py         # Herramienta de limpieza de cola local (debug)
├── queueclean.bat        # Atajo BAT para queueclean.py (sin Python en PATH)
├── logs/
│   └── agent.log         # Log rotativo del agente
├── modules/
│   ├── __init__.py       # Dispatcher de tipos de ticket
│   ├── escpos_helpers.py # Helpers ESC/POS compartidos
│   ├── ticket_venta.py   # Renderizado de TICKET_VENTA
│   ├── ticket_cambio.py  # Renderizado de TICKET_CAMBIO
│   └── ticket_prueba.py  # Renderizado de TICKET_PRUEBA
└── portal/
    ├── app.py            # Servidor Flask local (dashboard + config)
    └── templates/
        ├── base.html
        ├── index.html    # Dashboard de estado
        └── config.html   # Formulario de configuración
```

---

## Configuración (`config.json`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `server_url` | string | IP o URL base del servidor GestionCom — **solo la dirección**, sin rutas (ej. `http://192.168.1.100` o `192.168.1.100`). El agente agrega `/api` automáticamente. |
| `printer_api_key` | string | Clave de autorización del punto de venta (`XXXX-XXXX-XXXX-XXXX`). Se genera desde el panel web en Configuración → Puntos de Venta → Editar. |
| `printer_name` | string | Nombre de la impresora en Windows o `"auto"` para detección automática |
| `portal_port` | int | Puerto del portal web local (default `80`) |
| `poll_interval_seconds` | int | Intervalo de polling en segundos (default `2`) |
| `template_cache_version` | string\|null | Versión del template en caché (gestionado automáticamente) |
| `max_job_attempts` | int | Máximo de reintentos por trabajo fallido (default `3`) |
| `log_level` | string | Nivel de log: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

> **Nota:** `server_url` se normaliza automáticamente al guardar desde el portal. No es necesario incluir `/api` ni ninguna ruta — se ignoran si se ingresan.

---

## Comandos disponibles

Ejecutar sin argumentos muestra la ayuda:

```bat
python agent.py
```

```bat
# Ejecutar en primer plano (modo prueba/desarrollo)
python agent.py run

# Ejecutar sin portal web
python agent.py run --no-portal

# Imprimir ticket de prueba local, sin servidor ni poller
python agent.py test-print

# Listar impresoras disponibles en Windows
python agent.py test-print --list-printers

# Probar una impresora especifica
python agent.py test-print --printer "Nombre exacto de la impresora"

# Abrir portal de configuración en el navegador
python agent.py config

# Gestión del servicio Windows (requiere Administrador)
python agent.py install   # Instalar como servicio
python agent.py start     # Iniciar servicio
python agent.py stop      # Detener servicio
python agent.py restart   # Reiniciar servicio
python agent.py remove    # Desinstalar servicio
python agent.py status    # Consultar estado del servicio
```

---

## Portal web local

El agente expone un portal en `http://localhost` con:

| Ruta | Descripción |
|------|-------------|
| `GET /` | Dashboard: estado del agente, última impresión, contadores |
| `GET /config` | Formulario de configuración |
| `POST /config` | Guardar configuración |
| `POST /test-print` | Imprimir ticket de prueba |
| `GET /api/status` | JSON con estado actual (para monitoreo externo) |

---

## API del servidor que consume el agente

Todos los endpoints usan el header `X-Printer-Api-Key: <clave>` y se acceden bajo el prefijo `/api` del servidor.

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/print/agent/template-version` | Versión y código del template activo |
| `GET` | `/api/print/agent/template/{code}` | Descarga el template completo |
| `GET` | `/api/print/agent/jobs/pending` | Lista trabajos pendientes de este punto de venta |
| `PATCH` | `/api/print/agent/jobs/{job_code}/status` | Informa resultado (`COMPLETED`/`FAILED`) |

---

## Tipos de ticket soportados

| Código | Descripción |
|--------|-------------|
| `TICKET_VENTA` | Ticket de venta al cliente |
| `TICKET_CAMBIO` | Ticket de cambio o devolución |
| `TICKET_PRUEBA` | Ticket de prueba para calibración |

---

## Anchos de papel soportados

| mm | Columnas (fuente A) |
|----|---------------------|
| 58 mm | 32 caracteres |
| 80 mm | 48 caracteres |

El ancho se lee del campo `paper_width_mm` del template descargado desde el servidor.

---

## Flujo de templates

```
Arranque / cada ~2 min
       │
       ▼
GET /api/print/agent/template-version
       │
  ¿versión cambió?
  ├── No → usar caché local (template_cache.json)
  └── Sí → GET /api/print/agent/template/{code} → guardar caché → usar nuevo template
```

Si el servidor no responde, el agente usa el último template en caché. Si no hay caché, usa un template por defecto con configuración estándar.

---

## Herramienta de debug: limpieza de cola local

`queueclean.py` limpia trabajos atascados en el spooler de Windows. Útil cuando la impresora queda en error y los trabajos no se pueden cancelar desde la UI.

**Requiere ejecutar como Administrador.**

```bat
# Solo listar qué hay en la cola, sin modificar nada
python queueclean.py --dry-run

# Limpiar: cancela jobs, detiene spooler, borra archivos, reinicia spooler
python queueclean.py
```

O sin Python en PATH, doble clic en `queueclean.bat` → "Ejecutar como administrador".

El script realiza 4 pasos:
1. Cancela los trabajos pendientes via `Get-PrintJob | Remove-PrintJob` (PowerShell)
2. Detiene el servicio Spooler (`net stop spooler`)
3. Elimina los archivos `.SPL` / `.SHD` en `C:\Windows\System32\spool\PRINTERS`
4. Reinicia el Spooler (`net start spooler`)

---

## Log

El log se escribe en `logs/agent.log`. Niveles relevantes:

```
INFO   Agente corriendo / detenido
INFO   Job XXXXX completado
INFO   Template actualizado: TICKET_VENTA v1.0.3
WARNING Sin conexión al servidor: ...
ERROR  No se pudo abrir impresora 'XPrinter XP-58'
```

---

## Dependencias

```
requests==2.32.3       # HTTP client
python-escpos==3.1     # Impresión ESC/POS
flask==3.1.0           # Portal web local
pywin32==308           # Windows Service (solo Windows)
```

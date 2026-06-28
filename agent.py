"""
Punto de entrada del agente GestionCom Print Agent.

Uso:
  python agent.py run              → Ejecutar en foreground (pruebas)
  python agent.py run --no-portal  → Solo poller, sin portal web
  python agent.py test-print       → Imprimir ticket de prueba local
  python agent.py test-print --list-printers
  python agent.py test-print --printer "Nombre impresora"
  python agent.py install          → Instalar como servicio Windows
  python agent.py start            → Iniciar servicio Windows
  python agent.py stop             → Detener servicio Windows
  python agent.py remove           → Desinstalar servicio Windows
  python agent.py status           → Estado del servicio
  python agent.py config           → Abrir portal de configuración en el navegador
"""
import logging
import signal
import sys
import threading
import webbrowser

import config_manager

logger = logging.getLogger("agent")


def _setup_logging() -> None:
    from pathlib import Path

    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "agent.log"

    level = getattr(logging, config_manager.get("log_level", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_foreground(with_portal: bool = True) -> None:
    """Ejecuta el agente en primer plano. Útil para pruebas y desarrollo."""
    _setup_logging()

    import poller
    import template_manager

    logger.info("=" * 50)
    logger.info("GestionCom Print Agent — Modo Foreground")
    logger.info("=" * 50)

    if not config_manager.is_configured():
        logger.warning("El agente no está configurado. Abre http://localhost:%d para configurar.",
                       config_manager.get("portal_port", 80))

    # Verificar y actualizar template al inicio
    updated, templates = template_manager.check_and_update_all()
    if updated:
        for code, tmpl in templates.items():
            logger.info("Template descargado: %s v%s", code, tmpl.get("version"))

    # Iniciar poller en hilo
    poller.start()

    stop_event = threading.Event()

    def _handle_signal(sig, frame):
        logger.info("Señal de parada recibida (%s)", sig)
        poller.stop()
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if with_portal:
        from portal import app as portal_app

        port = config_manager.get("portal_port", 80)
        portal_thread = threading.Thread(
            target=portal_app.run,
            kwargs={"port": port},
            daemon=True,
            name="portal",
        )
        portal_thread.start()
        logger.info("Portal disponible en http://localhost:%d", port)

        webbrowser.open(f"http://localhost:{port}/")

    logger.info("Agente corriendo. Presiona Ctrl+C para detener.")
    stop_event.wait()
    logger.info("Agente detenido.")


def _delegate_to_service(cmd: str) -> None:
    """Delega comandos de servicio Windows a service.py."""
    try:
        import win32serviceutil
        from service import PrintAgentService
        sys.argv = [sys.argv[0], cmd]
        win32serviceutil.HandleCommandLine(PrintAgentService)
    except ImportError:
        print("pywin32 no está instalado. Instala con: pip install pywin32")
        sys.exit(1)


def service_status() -> None:
    """Muestra el estado actual del servicio Windows."""
    try:
        import win32serviceutil
        import win32service
        from service import SERVICE_NAME, SERVICE_DISPLAY
    except ImportError:
        print("pywin32 no está instalado. Instala con: pip install pywin32")
        sys.exit(1)

    STATE_LABELS = {
        win32service.SERVICE_STOPPED:          ("DETENIDO",          "●"),
        win32service.SERVICE_START_PENDING:    ("INICIANDO...",      "○"),
        win32service.SERVICE_STOP_PENDING:     ("DETENIÉNDOSE...",   "○"),
        win32service.SERVICE_RUNNING:          ("CORRIENDO",         "●"),
        win32service.SERVICE_CONTINUE_PENDING: ("REANUDANDO...",     "○"),
        win32service.SERVICE_PAUSE_PENDING:    ("PAUSANDO...",       "○"),
        win32service.SERVICE_PAUSED:           ("PAUSADO",           "●"),
    }

    try:
        status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        state_code = status[1]
        label, dot = STATE_LABELS.get(state_code, (f"DESCONOCIDO ({state_code})", "?"))
        print(f"\n  {dot} {SERVICE_DISPLAY}  [{label}]\n")
    except Exception as exc:
        # El servicio no existe o no está instalado
        print(f"\n  ○ {SERVICE_DISPLAY}  [NO INSTALADO]\n  {exc}\n")


def open_config() -> None:
    port = config_manager.get("portal_port", 80)
    url = f"http://localhost:{port}/config"
    print(f"Abriendo configuración en {url}")
    webbrowser.open(url)


def print_test_cli(args: list[str] | None = None) -> int:
    """Ejecuta un ticket de prueba desde consola, sin iniciar el poller."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python agent.py test-print",
        description="Imprime un ticket de prueba local en la impresora configurada.",
    )
    parser.add_argument(
        "--printer",
        help='Nombre de la impresora Windows. Si se omite usa config.json ("auto" por defecto).',
    )
    parser.add_argument(
        "--list-printers",
        action="store_true",
        help="Lista impresoras disponibles y no imprime.",
    )
    parsed = parser.parse_args(args)

    _setup_logging()

    import poller
    import printer as printer_module

    if parsed.list_printers:
        printers = printer_module.list_printers()
        if not printers:
            print("No se encontraron impresoras disponibles o pywin32 no está instalado.")
            return 1
        print("Impresoras disponibles:")
        for name in printers:
            marker = " (predeterminada)" if name == printer_module.get_default_printer() else ""
            print(f"  - {name}{marker}")
        return 0

    target = parsed.printer or config_manager.get("printer_name", "auto")
    print(f"Imprimiendo ticket de prueba en: {target}")
    result = poller.print_test(printer_name=target)
    if result.get("ok"):
        print("OK: ticket de prueba enviado a la impresora.")
        return 0

    print(f"ERROR: {result.get('error', 'No se pudo imprimir el ticket de prueba')}")
    return 1


def print_usage() -> None:
    sep = "─" * 54
    print()
    print(sep)
    print("  GestionCom Print Agent")
    print(sep)
    print()
    print("  Uso:  python agent.py <comando> [opciones]")
    print()
    print("  Comandos disponibles:")
    print()
    print("    run               Ejecutar en foreground (pruebas/debug)")
    print("      --no-portal     Solo poller, sin portal web")
    print()
    print("    test-print        Imprimir ticket de prueba local")
    print("      --printer NAME  Usar impresora específica")
    print("      --list-printers Listar impresoras disponibles")
    print()
    print("    config            Abrir portal de configuración en el navegador")
    print()
    print("    install           Instalar como servicio Windows")
    print("    start             Iniciar servicio Windows")
    print("    stop              Detener servicio Windows")
    print("    restart           Reiniciar servicio Windows")
    print("    status            Ver estado del servicio")
    print("    remove            Desinstalar servicio Windows")
    print()
    print("  Ejemplos:")
    print("    python agent.py run")
    print("    python agent.py test-print --list-printers")
    print("    python agent.py test-print --printer \"XP-58C\"")
    print()
    print(sep)
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd in ("--help", "-h", "help"):
        print_usage()
        sys.exit(0)
    elif cmd == "run":
        no_portal = "--no-portal" in sys.argv
        run_foreground(with_portal=not no_portal)
    elif cmd in ("test-print", "print-test", "printtest"):
        sys.exit(print_test_cli(sys.argv[2:]))
    elif cmd == "status":
        service_status()
    elif cmd in ("install", "start", "stop", "remove", "restart"):
        _delegate_to_service(cmd)
    elif cmd == "config":
        open_config()
    else:
        print(f"\n  Comando desconocido: '{cmd}'\n")
        print_usage()
        sys.exit(1)

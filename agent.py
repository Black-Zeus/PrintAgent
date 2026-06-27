"""
Punto de entrada del agente CeciChic Print Agent.

Uso:
  python agent.py run              → Ejecutar en foreground (pruebas)
  python agent.py run --no-portal  → Solo poller, sin portal web
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
    logger.info("CeciChic Print Agent — Modo Foreground")
    logger.info("=" * 50)

    if not config_manager.is_configured():
        logger.warning("El agente no está configurado. Abre http://localhost:%d para configurar.",
                       config_manager.get("portal_port", 8765))

    # Verificar y actualizar template al inicio
    updated, template = template_manager.check_and_update()
    if updated:
        logger.info("Template descargado: %s v%s", template.get("template_code"), template.get("version"))

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

        port = config_manager.get("portal_port", 8765)
        portal_thread = threading.Thread(
            target=portal_app.run,
            kwargs={"port": port},
            daemon=True,
            name="portal",
        )
        portal_thread.start()
        logger.info("Portal disponible en http://localhost:%d", port)

        # Abrir navegador si hay configuración pendiente
        if not config_manager.is_configured():
            webbrowser.open(f"http://localhost:{port}/config")

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


def open_config() -> None:
    port = config_manager.get("portal_port", 8765)
    url = f"http://localhost:{port}/config"
    print(f"Abriendo configuración en {url}")
    webbrowser.open(url)


def print_usage() -> None:
    print(__doc__)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"

    if cmd == "run":
        no_portal = "--no-portal" in sys.argv
        run_foreground(with_portal=not no_portal)
    elif cmd in ("install", "start", "stop", "remove", "restart", "status"):
        _delegate_to_service(cmd)
    elif cmd == "config":
        open_config()
    else:
        print_usage()
        sys.exit(1)

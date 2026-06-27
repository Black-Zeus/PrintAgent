"""
Windows Service wrapper para el agente de impresión.
Instalar: python service.py install
Iniciar:  python service.py start
Detener:  python service.py stop
Remover:  python service.py remove

Requiere pywin32. En desarrollo/pruebas usar agent.py run directamente.
"""
import logging
import sys
import threading

_WIN32_AVAILABLE = False
try:
    import win32event
    import win32service
    import win32serviceutil
    _WIN32_AVAILABLE = True
except ImportError:
    pass

SERVICE_NAME = "CeciChicPrintAgent"
SERVICE_DISPLAY = "CeciChic Print Agent"
SERVICE_DESC = "Agente de impresión térmica para CeciChic POS"


if _WIN32_AVAILABLE:
    class PrintAgentService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = SERVICE_DESC

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            import poller
            poller.stop()
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self):
            import poller
            from portal import app as portal_app
            import config_manager

            _setup_logging()

            poller.start()

            port = config_manager.get("portal_port", 8765)
            portal_thread = threading.Thread(
                target=portal_app.run,
                kwargs={"port": port},
                daemon=True,
            )
            portal_thread.start()

            win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)


def _setup_logging() -> None:
    from pathlib import Path
    import config_manager

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


if __name__ == "__main__":
    if not _WIN32_AVAILABLE:
        print("pywin32 no disponible. Usa 'python agent.py run' para ejecutar en foreground.")
        sys.exit(1)
    win32serviceutil.HandleCommandLine(PrintAgentService)

#!/usr/bin/env python3
r"""
queueclean.py — Limpieza de cola local de impresión (Windows, debug)

1. Cancela trabajos en error via PowerShell (Get-PrintJob / Remove-PrintJob)
2. Detiene el spooler de Windows
3. Elimina archivos .SPL / .SHD atascados en spool\PRINTERS
4. Reinicia el spooler

Requiere ejecutar como Administrador.

Uso:
    python queueclean.py              # Limpiar toda la cola local
    python queueclean.py --dry-run    # Solo mostrar que se eliminaria
    python queueclean.py --help
"""

import os
import shutil
import sys
import subprocess
import time
from pathlib import Path

SPOOL_DIR = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "spool" / "PRINTERS"
PS_EXE    = shutil.which("powershell") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
NET_EXE   = shutil.which("net") or r"C:\Windows\System32\net.exe"
SEP = "─" * 58


def _run(cmd: list[str]) -> tuple[int, str]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr).strip()


def _service(action: str) -> bool:
    code, out = _run([NET_EXE, action, "spooler"])
    ok = code == 0
    label = "OK" if ok else "ERROR"
    first_line = out.splitlines()[0] if out else ""
    print(f"      [{label}] net {action} spooler — {first_line}")
    return ok


def _cancel_print_jobs(dry_run: bool) -> int:
    """Cancela todos los trabajos atascados via PowerShell. Devuelve cantidad cancelada."""
    # Obtener impresoras con trabajos
    code, out = _run([
        PS_EXE, "-NoProfile", "-Command",
        "Get-Printer | Select-Object -ExpandProperty Name"
    ])
    if code != 0 or not out.strip():
        print("      [WARN] No se pudieron listar impresoras via PowerShell")
        return 0

    printers = [p.strip() for p in out.splitlines() if p.strip()]
    total = 0

    for printer in printers:
        # Listar trabajos de esta impresora
        code, jobs_out = _run([
            PS_EXE, "-NoProfile", "-Command",
            f'Get-PrintJob -PrinterName "{printer}" 2>$null | Select-Object -ExpandProperty Id'
        ])
        job_ids = [j.strip() for j in jobs_out.splitlines() if j.strip().isdigit()]
        if not job_ids:
            continue

        print(f"      • {printer}: {len(job_ids)} trabajo(s) encontrado(s)")
        if dry_run:
            total += len(job_ids)
            continue

        code, _ = _run([
            PS_EXE, "-NoProfile", "-Command",
            f'Get-PrintJob -PrinterName "{printer}" | Remove-PrintJob'
        ])
        if code == 0:
            print(f"        [OK] cancelados")
            total += len(job_ids)
        else:
            print(f"        [WARN] no se pudieron cancelar")

    return total


def main(dry_run: bool = False) -> None:
    print()
    print(SEP)
    print("  GestionCom Print Agent — Limpieza de cola local")
    print(SEP)
    print(f"  Spool dir  : {SPOOL_DIR}")
    print(f"  Modo       : {'DRY-RUN — sin cambios' if dry_run else 'REAL — se limpiarán los trabajos'}")
    print(SEP)
    print()

    # ── Paso 1: cancelar jobs via PowerShell ──────────────────────────────────
    print("[1/4] Cancelando trabajos en cola (PowerShell)...")
    cancelled = _cancel_print_jobs(dry_run)
    if cancelled == 0:
        print("      → No se encontraron trabajos activos en ninguna impresora.")
    print()

    # ── Paso 2: leer archivos en spool ────────────────────────────────────────
    print("[2/4] Leyendo archivos en spool...")
    if not SPOOL_DIR.exists():
        print(f"      [WARN] Directorio no encontrado: {SPOOL_DIR}")
        print()
    else:
        files = [f for f in SPOOL_DIR.iterdir() if f.is_file()]
        if not files:
            print("      → Sin archivos en spool.")
        else:
            print(f"      → {len(files)} archivo(s):\n")
            for f in sorted(files):
                size_kb = f.stat().st_size / 1024
                print(f"         • {f.name:<30}  {size_kb:6.1f} KB")

    print()

    if dry_run:
        print("[DRY-RUN] No se realizó ningún cambio.")
        print(SEP)
        print()
        return

    # ── Paso 3: stop → borrar spool → start ──────────────────────────────────
    print("[3/4] Deteniendo spooler...")
    _service("stop")
    time.sleep(1)
    print()

    deleted = 0
    errors  = 0
    if SPOOL_DIR.exists():
        files = [f for f in SPOOL_DIR.iterdir() if f.is_file()]
        if files:
            print("      Eliminando archivos de spool...")
            for f in files:
                try:
                    f.unlink()
                    print(f"      [OK]   {f.name}")
                    deleted += 1
                except Exception as exc:
                    print(f"      [WARN] {f.name} — {exc}")
                    errors += 1
            print()

    print("[4/4] Reiniciando spooler...")
    _service("start")
    print()

    # ── Resumen ───────────────────────────────────────────────────────────────
    print(SEP)
    print(f"  Jobs cancelados  : {cancelled}")
    print(f"  Archivos borrados: {deleted}")
    if errors:
        print(f"  Con error        : {errors}  ← ejecuta como Administrador")
    print()
    if errors == 0:
        print("[OK]  Cola limpia. La impresora debería aceptar nuevos trabajos.")
    else:
        print("[WARN] Algunos archivos no se pudieron eliminar.")
        print("       Ejecuta el script como Administrador e intenta de nuevo.")
    print(SEP)
    print()


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)

    if sys.platform != "win32":
        print("[WARN] Este script está diseñado para Windows.")
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)

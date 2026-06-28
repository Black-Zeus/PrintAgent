"""
Atajo para imprimir un ticket de prueba local.

Uso:
  python printtest.py
  python printtest.py --list-printers
  python printtest.py --printer "Nombre impresora"
"""
import sys

from agent import print_test_cli


if __name__ == "__main__":
    sys.exit(print_test_cli(sys.argv[1:]))

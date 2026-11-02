"""Punto de entrada del asistente IA personal."""
from __future__ import annotations

import sys

from assistant.interfaces.cli import main as cli_main


def main() -> int:
    """Lanza la interfaz CLI."""
    try:
        cli_main()
        return 0
    except KeyboardInterrupt:
        print("\nHasta luego.")
        return 0
    except Exception as e:
        print(f"Error fatal: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

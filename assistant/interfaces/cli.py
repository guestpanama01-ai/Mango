"""Interfaz de línea de comandos interactiva con rich."""
from __future__ import annotations

import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from assistant.config import MAX_ITERATIONS
from assistant.core.agent import get_agent
from assistant.core.memory import TokenCounter
from assistant.tools import registry

# Importa los módulos de tools para que se registren
import assistant.tools.files  # noqa: F401
import assistant.tools.shell  # noqa: F401
import assistant.tools.web    # noqa: F401

console = Console()


def _print_banner() -> None:
    """Muestra el banner de inicio."""
    console.print(Panel.fit(
        "[bold cyan]Asistente IA Personal[/bold cyan]\n"
        "[dim]Escribe /help para ver comandos. Ctrl+C o /exit para salir.[/dim]",
        border_style="cyan",
    ))


def _print_help() -> None:
    """Muestra la ayuda de comandos."""
    table = Table(title="Comandos", show_header=True, header_style="bold magenta")
    table.add_column("Comando", style="cyan", no_wrap=True)
    table.add_column("Descripción")

    table.add_row("/help", "Muestra esta ayuda")
    table.add_row("/tools", "Lista tools registradas y sus schemas")
    table.add_row("/facts", "Lista hechos guardados en memoria larga")
    table.add_row("/clear", "Borra el historial de la conversación actual")
    table.add_row("/tokens", "Muestra tokens consumidos hoy")
    table.add_row("/exit", "Sale del asistente")

    console.print(table)


def _print_tools() -> None:
    """Lista tools registradas."""
    names = registry.tool_names()
    if not names:
        console.print("[yellow]No hay tools registradas.[/yellow]")
        return

    table = Table(title=f"Tools ({len(names)})", show_header=True, header_style="bold magenta")
    table.add_column("Nombre", style="cyan", no_wrap=True)
    table.add_column("Descripción")

    for name in names:
        entry = registry.TOOL_REGISTRY[name]
        table.add_row(name, entry.get("description", ""))

    console.print(table)


def _print_facts() -> None:
    """Lista hechos guardados."""
    agent = get_agent()
    facts = agent.ltm.all_facts()
    if not facts:
        console.print("[yellow]No hay hechos guardados.[/yellow]")
        return

    table = Table(title="Hechos", show_header=True, header_style="bold magenta")
    table.add_column("Clave", style="cyan", no_wrap=True)
    table.add_column("Valor")

    for k, v in facts.items():
        table.add_row(k, v)

    console.print(table)


def _print_tokens() -> None:
    """Muestra tokens consumidos hoy."""
    tc = TokenCounter()
    total = tc.daily_total()
    by_provider = tc.by_provider()

    console.print(f"[bold]Tokens hoy:[/bold] {total}")
    if by_provider:
        for prov, count in by_provider.items():
            console.print(f"  [cyan]{prov}[/cyan]: {count}")
    else:
        console.print("[dim]Sin consumo registrado hoy.[/dim]")


def _handle_command(cmd: str) -> bool:
    """Procesa comandos slash. Devuelve True si debe salir."""
    cmd = cmd.strip().lower()

    if cmd == "/exit":
        return True
    if cmd == "/help":
        _print_help()
    elif cmd == "/tools":
        _print_tools()
    elif cmd == "/facts":
        _print_facts()
    elif cmd == "/clear":
        get_agent().stm.clear()
        console.print("[green]Historial borrado.[/green]")
    elif cmd == "/tokens":
        _print_tokens()
    else:
        console.print(f"[red]Comando desconocido: {cmd}[/red]")
        console.print("[dim]Usa /help para ver comandos.[/dim]")

    return False


def main() -> None:
    """Punto de entrada del CLI."""
    _print_banner()
    agent = get_agent()

    while True:
        try:
            user_input = console.input("\n[bold green]tú[/bold green] › ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Hasta luego.[/dim]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            should_exit = _handle_command(user_input)
            if should_exit:
                console.print("[dim]Hasta luego.[/dim]")
                break
            continue

        # Procesa mensaje con spinner
        try:
            with console.status("[cyan]pensando...[/cyan]", spinner="dots"):
                reply = agent.run(user_input)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrumpido.[/yellow]")
            continue
        except Exception as e:
            console.print(f"[red]Error: {type(e).__name__}: {e}[/red]")
            continue

        if reply:
            console.print()
            console.print(Panel(
                Markdown(reply),
                title="[bold cyan]asistente[/bold cyan]",
                border_style="cyan",
                padding=(0, 1),
            ))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

"""Case management commands."""

import typer
from typing_extensions import Annotated

from deeptrace.console import console, err_console
import deeptrace.state as _state
from deeptrace.state import AppState


def new(
    name: Annotated[str, typer.Argument(help="Name for the new case")],
) -> None:
    """Create a new case workspace."""
    state = AppState(cases_dir=_state.CASES_DIR)
    try:
        slug = state.create_case(name)
        console.print(f"Created case [bold green]{slug}[/]")
    except FileExistsError as e:
        err_console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1)


def open_case(
    slug: Annotated[str, typer.Argument(help="Case slug to open")],
) -> None:
    """Open an existing case."""
    state = AppState(cases_dir=_state.CASES_DIR)
    try:
        state.open_case(slug)
        console.print(f"Opened case [bold green]{slug}[/]")
        state.close_case()
    except FileNotFoundError as e:
        err_console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1)


def list_cases() -> None:
    """List all cases."""
    state = AppState(cases_dir=_state.CASES_DIR)
    cases = state.list_cases()
    if not cases:
        console.print("[dim]No cases found.[/]")
        return
    console.print("[bold]Cases:[/]")
    for slug in cases:
        console.print(f"  {slug}")

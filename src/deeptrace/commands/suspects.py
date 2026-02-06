"""Suspect pool management commands."""


from typing import Annotated

import typer
from rich.panel import Panel

import deeptrace.state as _state
from deeptrace.console import console, err_console
from deeptrace.db import CaseDatabase

app = typer.Typer(no_args_is_help=True)


def _open_case_db(case: str) -> CaseDatabase:
    case_dir = _state.CASES_DIR / case
    if not case_dir.exists():
        err_console.print(f"[bold red]Error:[/] Case '{case}' not found.")
        raise typer.Exit(1)
    db = CaseDatabase(case_dir / "case.db")
    db.open()
    return db


@app.command()
def add(
    case: Annotated[str, typer.Option(help="Case slug")] = "",
    category: Annotated[str, typer.Option(help="Pool category name")] = "",
    description: Annotated[str, typer.Option(help="Description of this suspect category")] = "",
    evidence: Annotated[str | None, typer.Option(help="Supporting evidence")] = None,
) -> None:
    """Add a suspect pool category."""
    db = _open_case_db(case)
    try:
        with db.transaction() as cursor:
            cursor.execute(
                """INSERT INTO suspect_pools
                   (category, description, supporting_evidence)
                   VALUES (?, ?, ?)""",
                (category, description, evidence),
            )
        console.print(f"Added suspect pool: [bold cyan]{category}[/]")
    finally:
        db.close()


@app.command()
def show(
    case: Annotated[str, typer.Option(help="Case slug")] = "",
) -> None:
    """Display all suspect pool categories."""
    db = _open_case_db(case)
    try:
        pools = db.fetchall("SELECT * FROM suspect_pools ORDER BY id")
        if not pools:
            console.print("[dim]No suspect pools defined.[/]")
            return

        for pool in pools:
            content = pool["description"]
            if pool["supporting_evidence"]:
                content += f"\n\n[green]Evidence:[/] {pool['supporting_evidence']}"
            console.print(Panel(
                content,
                title=f"[bold cyan][{pool['id']}] {pool['category']}[/]",
                border_style="cyan",
            ))
    finally:
        db.close()

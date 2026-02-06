"""Source ingestion commands."""


from typing import Annotated

import typer

import deeptrace.state as _state
from deeptrace.console import console, err_console
from deeptrace.db import CaseDatabase


def add_source(
    case: Annotated[str, typer.Option(help="Case slug")],
    type: Annotated[
        str,
        typer.Option(help="Source type: news, official, social, document, manual"),
    ],
    text: Annotated[str, typer.Option(help="Source text content")],
    url: Annotated[str | None, typer.Option(help="Source URL")] = None,
    reliability: Annotated[float, typer.Option(help="Reliability score 0.0-1.0")] = 0.5,
    notes: Annotated[str | None, typer.Option(help="Notes about this source")] = None,
) -> None:
    """Add a source to a case."""
    case_dir = _state.CASES_DIR / case
    if not case_dir.exists():
        err_console.print(f"[bold red]Error:[/] Case '{case}' not found.")
        raise typer.Exit(1)

    db = CaseDatabase(case_dir / "case.db")
    db.open()
    try:
        with db.transaction() as cursor:
            cursor.execute(
                """INSERT INTO sources (url, raw_text, source_type, reliability_score, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (url, text, type, reliability, notes),
            )
        console.print(f"Added source [bold green]({type})[/] to case [bold]{case}[/]")
    finally:
        db.close()

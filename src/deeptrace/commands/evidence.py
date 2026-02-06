"""Evidence chain tracker commands."""


from typing import Annotated

import typer
from rich.table import Table

import deeptrace.state as _state
from deeptrace.console import console, err_console
from deeptrace.db import CaseDatabase

app = typer.Typer(no_args_is_help=True)

VALID_STATUSES = ["known", "processed", "pending", "inconclusive", "missing"]
STATUS_STYLES = {
    "known": "white",
    "processed": "green",
    "pending": "yellow",
    "inconclusive": "dim yellow",
    "missing": "bold red",
}


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
    name: Annotated[str, typer.Argument(help="Evidence item name")],
    case: Annotated[str, typer.Option(help="Case slug")] = "",
    type: Annotated[
        str, typer.Option(help="Evidence type: physical, digital, circumstantial")
    ] = "physical",
    status: Annotated[
        str,
        typer.Option(help="Status: known, processed, pending, inconclusive, missing"),
    ] = "known",
    description: Annotated[str | None, typer.Option(help="Description")] = None,
    source_id: Annotated[int | None, typer.Option(help="Source ID to link")] = None,
) -> None:
    """Add an evidence item."""
    if status not in VALID_STATUSES:
        valid = ", ".join(VALID_STATUSES)
        err_console.print(
            f"[bold red]Error:[/] Invalid status. Must be one of: {valid}"
        )
        raise typer.Exit(1)

    db = _open_case_db(case)
    try:
        with db.transaction() as cursor:
            cursor.execute(
                """INSERT INTO evidence_items (name, evidence_type, description, status, source_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, type, description, status, source_id),
            )
        console.print(f"Added evidence: [bold]{name}[/] [{STATUS_STYLES[status]}]({status})[/]")
    finally:
        db.close()


@app.command()
def show(
    case: Annotated[str, typer.Option(help="Case slug")] = "",
) -> None:
    """Display all evidence items."""
    db = _open_case_db(case)
    try:
        items = db.fetchall("SELECT * FROM evidence_items ORDER BY id")
        if not items:
            console.print("[dim]No evidence items tracked.[/]")
            return

        table = Table(title="Evidence Chain", show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Name", style="white")
        table.add_column("Type", style="dim", width=15)
        table.add_column("Status", justify="center", width=14)
        table.add_column("Description", style="dim")

        for item in items:
            style = STATUS_STYLES.get(item["status"], "white")
            table.add_row(
                str(item["id"]),
                item["name"],
                item["evidence_type"],
                f"[{style}]{item['status']}[/]",
                item["description"] or "",
            )
        console.print(table)
    finally:
        db.close()


@app.command()
def update(
    evidence_id: Annotated[str, typer.Argument(help="Evidence item ID")],
    case: Annotated[str, typer.Option(help="Case slug")] = "",
    status: Annotated[str | None, typer.Option(help="New status")] = None,
    description: Annotated[str | None, typer.Option(help="Updated description")] = None,
) -> None:
    """Update an evidence item."""
    db = _open_case_db(case)
    try:
        item = db.fetchone("SELECT * FROM evidence_items WHERE id = ?", (int(evidence_id),))
        if not item:
            err_console.print(f"[bold red]Error:[/] Evidence item {evidence_id} not found.")
            raise typer.Exit(1)

        updates = []
        params = []
        if status:
            if status not in VALID_STATUSES:
                err_console.print("[bold red]Error:[/] Invalid status.")
                raise typer.Exit(1)
            updates.append("status = ?")
            params.append(status)
        if description:
            updates.append("description = ?")
            params.append(description)

        if not updates:
            console.print("[dim]Nothing to update.[/]")
            return

        params.append(int(evidence_id))
        sql = f"UPDATE evidence_items SET {', '.join(updates)} WHERE id = ?"
        with db.transaction() as cursor:
            cursor.execute(sql, tuple(params))
        console.print(f"Updated evidence [bold]{evidence_id}[/]")
    finally:
        db.close()

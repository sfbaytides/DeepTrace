"""Timeline management commands."""

from datetime import datetime
from typing import Annotated

import typer
from rich.table import Table

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
    description: Annotated[str, typer.Argument(help="Event description")],
    case: Annotated[str, typer.Option(help="Case slug")] = "",
    date: Annotated[str | None, typer.Option(help="Date/time (ISO format)")] = None,
    date_end: Annotated[str | None, typer.Option(help="End date/time for ranges")] = None,
    confidence: Annotated[str, typer.Option(help="Confidence: high, medium, low")] = "medium",
    source_id: Annotated[int | None, typer.Option(help="Source ID to link")] = None,
) -> None:
    """Add a new event to the timeline."""
    db = _open_case_db(case)
    try:
        with db.transaction() as cursor:
            cursor.execute(
                """INSERT INTO events
                   (timestamp_start, timestamp_end, description,
                    confidence, source_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (date, date_end, description, confidence, source_id),
            )
        console.print(f"Added event: [bold green]{description}[/]")
    finally:
        db.close()


@app.command()
def show(
    case: Annotated[str, typer.Option(help="Case slug")] = "",
) -> None:
    """Display the full timeline."""
    db = _open_case_db(case)
    try:
        events = db.fetchall("SELECT * FROM events ORDER BY timestamp_start")
        if not events:
            console.print("[dim]No events in timeline.[/]")
            return

        table = Table(title="Timeline", show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Date", style="green", width=22)
        table.add_column("Event", style="white")
        table.add_column("Confidence", justify="center", width=12)

        for i, event in enumerate(events, 1):
            conf_display = {
                "high": "[bold green]high[/]",
                "medium": "[yellow]medium[/]",
                "low": "[red]low[/]",
            }.get(event["confidence"], event["confidence"])
            table.add_row(
                str(i),
                event["timestamp_start"] or "[dim]Unknown[/]",
                event["description"],
                conf_display,
            )
        console.print(table)
    finally:
        db.close()


@app.command()
def gaps(
    case: Annotated[str, typer.Option(help="Case slug")] = "",
    threshold_hours: Annotated[float, typer.Option(help="Minimum gap in hours to flag")] = 4.0,
) -> None:
    """Identify gaps in the timeline."""
    db = _open_case_db(case)
    try:
        events = db.fetchall(
            "SELECT * FROM events WHERE timestamp_start IS NOT NULL ORDER BY timestamp_start"
        )
        if len(events) < 2:
            console.print("[dim]Need at least 2 dated events to find gaps.[/]")
            return

        found_gaps = []
        for i in range(len(events) - 1):
            try:
                t1 = datetime.fromisoformat(events[i]["timestamp_start"])
                t2 = datetime.fromisoformat(events[i + 1]["timestamp_start"])
                gap_hours = (t2 - t1).total_seconds() / 3600
                if gap_hours >= threshold_hours:
                    found_gaps.append((events[i], events[i + 1], gap_hours))
            except (ValueError, TypeError):
                continue

        if not found_gaps:
            console.print("[green]No significant gaps found.[/]")
            return

        table = Table(title="Timeline Gaps", show_header=True, header_style="bold yellow")
        table.add_column("From Event", style="white")
        table.add_column("To Event", style="white")
        table.add_column("Gap", style="bold red", justify="right")

        for event_a, event_b, hours in found_gaps:
            gap_str = f"{hours:.1f} hours"
            table.add_row(
                f"{event_a['timestamp_start']}: {event_a['description'][:40]}",
                f"{event_b['timestamp_start']}: {event_b['description'][:40]}",
                gap_str,
            )
        console.print(table)
    finally:
        db.close()

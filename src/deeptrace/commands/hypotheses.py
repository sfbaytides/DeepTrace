"""Hypothesis tracker commands."""


from typing import Annotated

import typer
from rich.panel import Panel

import deeptrace.state as _state
from deeptrace.console import console, err_console
from deeptrace.db import CaseDatabase

app = typer.Typer(no_args_is_help=True)

VALID_TIERS = ["most-probable", "plausible", "less-likely", "unlikely"]
TIER_STYLES = {
    "most-probable": "bold green",
    "plausible": "yellow",
    "less-likely": "dim yellow",
    "unlikely": "dim red",
}
TIER_ORDER = {tier: i for i, tier in enumerate(VALID_TIERS)}


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
    description: Annotated[str, typer.Argument(help="Hypothesis description")],
    case: Annotated[str, typer.Option(help="Case slug")] = "",
    tier: Annotated[
        str,
        typer.Option(help="Tier: most-probable, plausible, less-likely, unlikely"),
    ] = "plausible",
    supporting: Annotated[str | None, typer.Option(help="Supporting evidence")] = None,
    contradicting: Annotated[str | None, typer.Option(help="Contradicting evidence")] = None,
    questions: Annotated[str | None, typer.Option(help="Open questions")] = None,
) -> None:
    """Add a new hypothesis."""
    if tier not in VALID_TIERS:
        valid = ", ".join(VALID_TIERS)
        err_console.print(
            f"[bold red]Error:[/] Invalid tier '{tier}'. Must be one of: {valid}"
        )
        raise typer.Exit(1)

    db = _open_case_db(case)
    try:
        with db.transaction() as cursor:
            cursor.execute(
                """INSERT INTO hypotheses
                   (description, tier, supporting_evidence,
                    contradicting_evidence, open_questions)
                   VALUES (?, ?, ?, ?, ?)""",
                (description, tier, supporting, contradicting, questions),
            )
        console.print(f"Added hypothesis [{TIER_STYLES[tier]}]({tier})[/]: {description}")
    finally:
        db.close()


@app.command()
def show(
    case: Annotated[str, typer.Option(help="Case slug")] = "",
) -> None:
    """Display all hypotheses grouped by tier."""
    db = _open_case_db(case)
    try:
        hypotheses = db.fetchall("SELECT * FROM hypotheses ORDER BY id")
        if not hypotheses:
            console.print("[dim]No hypotheses yet.[/]")
            return

        by_tier: dict[str, list] = {t: [] for t in VALID_TIERS}
        for h in hypotheses:
            tier = h["tier"]
            if tier in by_tier:
                by_tier[tier].append(h)

        for tier in VALID_TIERS:
            items = by_tier[tier]
            if not items:
                continue
            lines = []
            for h in items:
                lines.append(f"  [{h['id']}] {h['description']}")
                if h["supporting_evidence"]:
                    lines.append(f"      [green]+[/] {h['supporting_evidence']}")
                if h["contradicting_evidence"]:
                    lines.append(f"      [red]-[/] {h['contradicting_evidence']}")
                if h["open_questions"]:
                    lines.append(f"      [yellow]?[/] {h['open_questions']}")
            content = "\n".join(lines)
            style = TIER_STYLES[tier]
            console.print(Panel(
                content,
                title=f"[{style}]{tier.replace('-', ' ').title()}[/]",
                border_style=style,
            ))
    finally:
        db.close()


@app.command()
def update(
    hypothesis_id: Annotated[str, typer.Argument(help="Hypothesis ID to update")],
    case: Annotated[str, typer.Option(help="Case slug")] = "",
    tier: Annotated[str | None, typer.Option(help="New tier")] = None,
    supporting: Annotated[str | None, typer.Option(help="Add supporting evidence")] = None,
    contradicting: Annotated[str | None, typer.Option(help="Add contradicting evidence")] = None,
    questions: Annotated[str | None, typer.Option(help="Add open questions")] = None,
) -> None:
    """Update an existing hypothesis."""
    db = _open_case_db(case)
    try:
        h = db.fetchone("SELECT * FROM hypotheses WHERE id = ?", (int(hypothesis_id),))
        if not h:
            err_console.print(f"[bold red]Error:[/] Hypothesis {hypothesis_id} not found.")
            raise typer.Exit(1)

        updates = []
        params = []
        if tier:
            if tier not in VALID_TIERS:
                err_console.print(f"[bold red]Error:[/] Invalid tier '{tier}'.")
                raise typer.Exit(1)
            updates.append("tier = ?")
            params.append(tier)
        if supporting:
            updates.append("supporting_evidence = ?")
            params.append(supporting)
        if contradicting:
            updates.append("contradicting_evidence = ?")
            params.append(contradicting)
        if questions:
            updates.append("open_questions = ?")
            params.append(questions)

        if not updates:
            console.print("[dim]Nothing to update.[/]")
            return

        updates.append("updated_at = datetime('now')")
        params.append(int(hypothesis_id))
        sql = f"UPDATE hypotheses SET {', '.join(updates)} WHERE id = ?"
        with db.transaction() as cursor:
            cursor.execute(sql, tuple(params))
        console.print(f"Updated hypothesis [bold]{hypothesis_id}[/]")
    finally:
        db.close()

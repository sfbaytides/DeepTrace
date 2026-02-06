"""Root CLI application."""

import typer

from deeptrace.commands import cases

app = typer.Typer(
    name="deeptrace",
    help="Cold case investigation platform.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

app.command(name="new", rich_help_panel="Case Management")(cases.new)
app.command(name="open", rich_help_panel="Case Management")(cases.open_case)
app.command(name="cases", rich_help_panel="Case Management")(cases.list_cases)

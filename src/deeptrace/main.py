"""Root CLI application."""

import typer

from deeptrace.commands import cases, sources, timeline, hypotheses, suspects

app = typer.Typer(
    name="deeptrace",
    help="Cold case investigation platform.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

app.command(name="new", rich_help_panel="Case Management")(cases.new)
app.command(name="open", rich_help_panel="Case Management")(cases.open_case)
app.command(name="cases", rich_help_panel="Case Management")(cases.list_cases)
app.command(name="add-source", rich_help_panel="Data Collection")(sources.add_source)
app.add_typer(timeline.app, name="timeline", help="Manage case timeline.", rich_help_panel="Investigation")
app.add_typer(hypotheses.app, name="hypotheses", help="Manage tiered hypotheses.", rich_help_panel="Investigation")
app.add_typer(suspects.app, name="suspects", help="Manage suspect pool categories.", rich_help_panel="Investigation")

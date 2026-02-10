"""Dashboard server launch — registered as a CLI command."""

import webbrowser
from typing import Annotated

import typer

from deeptrace.dashboard import create_app


def dashboard(
    case: Annotated[str, typer.Option(help="Case slug (optional - shows selector if omitted)")] = "",
    port: Annotated[int, typer.Option(help="Port number")] = 8080,
    no_open: Annotated[bool, typer.Option("--no-open", help="Don't open browser")] = False,
) -> None:
    """Launch the web dashboard.

    If no case is specified, opens the case selector to choose or create a case.
    """
    try:
        app = create_app(case)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None

    if not no_open:
        webbrowser.open(f"http://localhost:{port}")

    if case:
        typer.echo(f"Starting dashboard for '{case}' on http://localhost:{port}")
    else:
        typer.echo(f"Starting DeepTrace case selector on http://localhost:{port}")

    app.run(host="127.0.0.1", port=port, debug=False)

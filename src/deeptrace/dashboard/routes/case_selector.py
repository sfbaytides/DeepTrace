"""Case selection and creation routes."""

import re
from pathlib import Path

from flask import Blueprint, current_app, redirect, render_template, request

import deeptrace.state as _state
from deeptrace.db import CaseDatabase

bp = Blueprint("case_selector", __name__)


@bp.route("/")
def selector():
    """Show case selector page."""
    cases_dir = _state.CASES_DIR
    cases = []

    if cases_dir.exists():
        for case_path in cases_dir.iterdir():
            if case_path.is_dir() and (case_path / "case.db").exists():
                cases.append(case_path.name)

    cases.sort()
    return render_template("case_selector.html", cases=cases)


@bp.route("/case/create", methods=["POST"])
def create_case():
    """Create a new case."""
    case_name = request.form.get("case_name", "").strip()
    case_description = request.form.get("case_description", "").strip()

    # Validate case name
    if not case_name:
        return "Case name is required", 400

    if not re.match(r"^[a-z0-9-]+$", case_name):
        return "Case name must contain only lowercase letters, numbers, and hyphens", 400

    # Create case directory
    case_dir = _state.CASES_DIR / case_name
    if case_dir.exists():
        return f"Case '{case_name}' already exists", 400

    case_dir.mkdir(parents=True, exist_ok=True)

    # Initialize database
    db_path = case_dir / "case.db"
    db = CaseDatabase(db_path)
    db.open()
    db.init_schema()

    # Optionally store description in a metadata file
    if case_description:
        metadata_path = case_dir / "description.txt"
        metadata_path.write_text(case_description, encoding="utf-8")

    db.close()

    # Redirect to the new case dashboard
    return redirect(f"/case/{case_name}")


@bp.route("/case/<case_slug>")
def case_dashboard(case_slug):
    """Show information about opening a case in a new dashboard instance."""
    # Since we can't dynamically change the app's case context,
    # we need to tell the user to restart the dashboard with the case parameter
    return f"""
    <html>
    <head>
        <title>DeepTrace - Open Case</title>
        <meta charset="utf-8">
        <link rel="stylesheet" href="/static/themes.css">
        <link rel="stylesheet" href="/static/style.css">
        <script src="/static/theme-toggle.js"></script>
    </head>
    <body>
        <div style="min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--bg-main); padding: 2rem;">
            <div style="max-width: 500px; text-align: center; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 12px; padding: 3rem; box-shadow: var(--shadow-lg);">
                <h1 style="font-family: var(--font-mono); font-size: 18px; color: var(--cyan); margin-bottom: 1.5rem;">Case Created Successfully!</h1>
                <p style="color: var(--text-secondary); margin-bottom: 2rem; line-height: 1.6;">
                    To open the dashboard for <strong style="color: var(--text-bright);">{case_slug}</strong>, restart the DeepTrace dashboard with:
                </p>
                <code style="display: block; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; font-family: var(--font-mono); font-size: 13px; color: var(--cyan); margin-bottom: 2rem;">
                    deeptrace dashboard --case {case_slug}
                </code>
                <a href="/" style="display: inline-block; padding: 0.75rem 1.5rem; background: var(--cyan); color: white; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; font-family: var(--font-mono);">
                    Back to Case Selector
                </a>
            </div>
        </div>
    </body>
    </html>
    """, 200, {"Content-Type": "text/html"}

"""Case selection and creation routes."""

import re

from flask import Blueprint, current_app, redirect, render_template, request, session

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
    return render_template("modern_case_selector.html", cases=cases)


@bp.route("/create", methods=["POST"])
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
    try:
        db = CaseDatabase(db_path)
        with db:
            db.initialize_schema()
    except Exception:
        # Clean up on failure so user can retry
        import shutil
        shutil.rmtree(case_dir, ignore_errors=True)
        return "Failed to initialize case database", 500

    # Optionally store description in a metadata file
    if case_description:
        metadata_path = case_dir / "description.txt"
        metadata_path.write_text(case_description, encoding="utf-8")

    # Set session and redirect to dashboard - NO CLI RESTART NEEDED!
    session["current_case"] = case_name
    return redirect("/")


@bp.route("/open/<case_slug>")
def open_case(case_slug):
    """Open a specific case - switches in browser, no restart needed!"""
    # Validate case exists
    case_dir = _state.CASES_DIR / case_slug
    if not case_dir.exists() or not (case_dir / "case.db").exists():
        return f"Case '{case_slug}' not found", 404

    # Set session and redirect to dashboard
    session["current_case"] = case_slug
    return redirect("/")

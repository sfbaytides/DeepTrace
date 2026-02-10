"""DeepTrace web dashboard — Flask app factory."""

from pathlib import Path

from flask import Flask, redirect, session
from werkzeug.middleware.proxy_fix import ProxyFix

import deeptrace.state as _state
from deeptrace.db import CaseDatabase


def create_app(case_slug: str = "") -> Flask:
    """Create and configure the Flask dashboard app.

    Supports dynamic case switching via session - no CLI restart needed!
    """
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )

    # Trust Azure reverse-proxy headers so redirects use https://
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    app.config["SECRET_KEY"] = "deeptrace-local-only"
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["DEFAULT_CASE_SLUG"] = case_slug  # Store default but allow session override

    def get_current_case_slug() -> str | None:
        """Get the active case from session or config."""
        # Check session first (allows dynamic switching without restart)
        if "current_case" in session:
            return session["current_case"]
        # Fall back to default from CLI
        return app.config.get("DEFAULT_CASE_SLUG") or None

    def get_db() -> CaseDatabase:
        """Get database for current case from session."""
        case = get_current_case_slug()
        if not case:
            raise ValueError("No case selected. Please select a case first.")

        case_dir = _state.CASES_DIR / case
        if not case_dir.exists():
            raise FileNotFoundError(f"Case '{case}' not found")

        db_path = case_dir / "case.db"
        db = CaseDatabase(db_path)
        db.open()
        return db

    # Attach helper functions to app
    app.get_db = get_db
    app.get_current_case_slug = get_current_case_slug

    # Register all blueprints (they'll check session for case)
    from deeptrace.dashboard.routes.ach import bp as ach_bp
    from deeptrace.dashboard.routes.case_selector import bp as selector_bp
    from deeptrace.dashboard.routes.dashboard import bp as dashboard_bp
    from deeptrace.dashboard.routes.evidence import bp as evidence_bp
    from deeptrace.dashboard.routes.files import bp as files_bp
    from deeptrace.dashboard.routes.hypotheses import bp as hypotheses_bp
    from deeptrace.dashboard.routes.import_data import bp as import_bp
    from deeptrace.dashboard.routes.network import bp as network_bp
    from deeptrace.dashboard.routes.source_ai import bp as source_ai_bp
    from deeptrace.dashboard.routes.sources import bp as sources_bp
    from deeptrace.dashboard.routes.suspects import bp as suspects_bp
    from deeptrace.dashboard.routes.timeline import bp as timeline_bp

    # Case selector and import are always available
    app.register_blueprint(selector_bp, url_prefix="/cases")
    app.register_blueprint(import_bp, url_prefix="/import")

    # Main routes
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(sources_bp, url_prefix="/sources")
    app.register_blueprint(source_ai_bp, url_prefix="/sources")
    app.register_blueprint(evidence_bp, url_prefix="/evidence")
    app.register_blueprint(files_bp, url_prefix="/files")
    app.register_blueprint(timeline_bp, url_prefix="/timeline")
    app.register_blueprint(hypotheses_bp, url_prefix="/hypotheses")
    app.register_blueprint(suspects_bp, url_prefix="/suspects")
    app.register_blueprint(network_bp, url_prefix="/network")
    app.register_blueprint(ach_bp, url_prefix="/ach")

    # Global error handler: redirect to case selector when case is missing/stale
    @app.errorhandler(FileNotFoundError)
    @app.errorhandler(ValueError)
    def handle_missing_case(error):
        """Clear stale session and redirect to case selector."""
        err_msg = str(error)
        if "case" in err_msg.lower() or "not found" in err_msg.lower():
            session.pop("current_case", None)
            return redirect("/cases/")
        # Re-raise non-case errors
        raise error

    return app

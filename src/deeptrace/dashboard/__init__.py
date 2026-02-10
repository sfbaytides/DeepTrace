"""DeepTrace web dashboard — Flask app factory."""

from pathlib import Path

from flask import Flask

import deeptrace.state as _state
from deeptrace.db import CaseDatabase


def create_app(case_slug: str = "") -> Flask:
    """Create and configure the Flask dashboard app.

    If case_slug is empty, creates a case selector app.
    Otherwise, creates a case-specific dashboard.
    """
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["SECRET_KEY"] = "deeptrace-local-only"
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

    # Case selector mode
    if not case_slug:
        from deeptrace.dashboard.routes.case_selector import bp as selector_bp
        app.register_blueprint(selector_bp)
        return app

    # Case-specific mode
    app.config["CASE_SLUG"] = case_slug

    case_dir = _state.CASES_DIR / case_slug
    if not case_dir.exists():
        raise FileNotFoundError(f"Case '{case_slug}' not found at {case_dir}")

    app.config["CASE_DB_PATH"] = case_dir / "case.db"

    def get_db() -> CaseDatabase:
        db = CaseDatabase(app.config["CASE_DB_PATH"])
        db.open()
        return db

    app.get_db = get_db

    # Register blueprints
    from deeptrace.dashboard.routes.ach import bp as ach_bp
    from deeptrace.dashboard.routes.dashboard import bp as dashboard_bp
    from deeptrace.dashboard.routes.evidence import bp as evidence_bp
    from deeptrace.dashboard.routes.files import bp as files_bp
    from deeptrace.dashboard.routes.hypotheses import bp as hypotheses_bp
    from deeptrace.dashboard.routes.network import bp as network_bp
    from deeptrace.dashboard.routes.sources import bp as sources_bp
    from deeptrace.dashboard.routes.suspects import bp as suspects_bp
    from deeptrace.dashboard.routes.timeline import bp as timeline_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(sources_bp, url_prefix="/sources")
    app.register_blueprint(evidence_bp, url_prefix="/evidence")
    app.register_blueprint(files_bp, url_prefix="/files")
    app.register_blueprint(timeline_bp, url_prefix="/timeline")
    app.register_blueprint(hypotheses_bp, url_prefix="/hypotheses")
    app.register_blueprint(suspects_bp, url_prefix="/suspects")
    app.register_blueprint(network_bp, url_prefix="/network")
    app.register_blueprint(ach_bp, url_prefix="/ach")

    return app

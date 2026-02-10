"""Sources CRUD routes."""

from flask import Blueprint, current_app, render_template, request

bp = Blueprint("sources", __name__)


@bp.route("/")
def index():
    db = current_app.get_db()
    try:
        rows = db.fetchall("SELECT * FROM sources ORDER BY id DESC")
        sources = [dict(row) for row in rows]
        if request.headers.get("HX-Request"):
            return render_template("sources.html", sources=sources)
        return render_template("base.html", page="sources", sources=sources,
                               case=current_app.get_current_case_slug())
    finally:
        db.close()


@bp.route("/", methods=["POST"])
def create():
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO sources (raw_text, source_type, url, reliability_score, notes) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    request.form["raw_text"],
                    request.form.get("source_type", "manual"),
                    request.form.get("url") or None,
                    float(request.form.get("reliability_score", 0.5)),
                    request.form.get("notes") or None,
                ),
            )
        rows = db.fetchall("SELECT * FROM sources ORDER BY id DESC")
        sources = [dict(row) for row in rows]
        return render_template("sources.html", sources=sources)
    finally:
        db.close()


@bp.route("/<int:source_id>")
def detail(source_id):
    db = current_app.get_db()
    try:
        row = db.fetchone("SELECT * FROM sources WHERE id = ?", (source_id,))
        if not row:
            return "Not found", 404
        attached = db.fetchall(
            "SELECT a.id, a.filename, a.mime_type FROM attachments a "
            "JOIN attachment_links al ON a.id = al.attachment_id "
            "WHERE al.entity_type = 'source' AND al.entity_id = ?",
            (source_id,),
        )
        return render_template("partials/source_detail.html", source=dict(row),
                               attached_files=[dict(r) for r in attached])
    finally:
        db.close()


@bp.route("/<int:source_id>", methods=["PUT"])
def update(source_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "UPDATE sources SET raw_text=?, source_type=?, url=?, "
                "reliability_score=?, notes=? WHERE id=?",
                (
                    request.form["raw_text"],
                    request.form.get("source_type", "manual"),
                    request.form.get("url") or None,
                    float(request.form.get("reliability_score", 0.5)),
                    request.form.get("notes") or None,
                    source_id,
                ),
            )
        row = db.fetchone("SELECT * FROM sources WHERE id = ?", (source_id,))
        return render_template("partials/source_detail.html", source=dict(row))
    finally:
        db.close()


@bp.route("/<int:source_id>", methods=["DELETE"])
def delete(source_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        return ""
    finally:
        db.close()

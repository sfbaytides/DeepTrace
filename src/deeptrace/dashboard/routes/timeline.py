"""Timeline CRUD routes."""

from flask import Blueprint, current_app, render_template, request

bp = Blueprint("timeline", __name__)


@bp.route("/")
def index():
    db = current_app.get_db()
    try:
        rows = db.fetchall("SELECT * FROM events ORDER BY timestamp_start")
        events = [dict(row) for row in rows]
        if request.headers.get("HX-Request"):
            return render_template("timeline.html", events=events)
        return render_template("base.html", page="timeline", events=events,
                               case=current_app.get_current_case_slug())
    finally:
        db.close()


@bp.route("/", methods=["POST"])
def create():
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO events (description, timestamp_start, timestamp_end, "
                "confidence, source_id) VALUES (?, ?, ?, ?, ?)",
                (
                    request.form["description"],
                    request.form.get("timestamp_start") or None,
                    request.form.get("timestamp_end") or None,
                    request.form.get("confidence", "medium"),
                    int(request.form["source_id"]) if request.form.get("source_id") else None,
                ),
            )
        rows = db.fetchall("SELECT * FROM events ORDER BY timestamp_start")
        events = [dict(row) for row in rows]
        return render_template("timeline.html", events=events)
    finally:
        db.close()


@bp.route("/<int:event_id>")
def detail(event_id):
    db = current_app.get_db()
    try:
        row = db.fetchone("SELECT * FROM events WHERE id = ?", (event_id,))
        if not row:
            return "Not found", 404
        attached = db.fetchall(
            "SELECT a.id, a.filename, a.mime_type FROM attachments a "
            "JOIN attachment_links al ON a.id = al.attachment_id "
            "WHERE al.entity_type = 'event' AND al.entity_id = ?",
            (event_id,),
        )
        return render_template("partials/event_detail.html", event=dict(row),
                               attached_files=[dict(r) for r in attached])
    finally:
        db.close()


@bp.route("/<int:event_id>", methods=["PUT"])
def update(event_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "UPDATE events SET description=?, timestamp_start=?, "
                "timestamp_end=?, confidence=? WHERE id=?",
                (
                    request.form["description"],
                    request.form.get("timestamp_start") or None,
                    request.form.get("timestamp_end") or None,
                    request.form.get("confidence", "medium"),
                    event_id,
                ),
            )
        row = db.fetchone("SELECT * FROM events WHERE id = ?", (event_id,))
        return render_template("partials/event_detail.html", event=dict(row))
    finally:
        db.close()


@bp.route("/<int:event_id>", methods=["DELETE"])
def delete(event_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute("DELETE FROM events WHERE id = ?", (event_id,))
        return ""
    finally:
        db.close()

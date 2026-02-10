"""Evidence CRUD routes."""

from flask import Blueprint, current_app, render_template, request

bp = Blueprint("evidence", __name__)

VALID_STATUSES = ["known", "processed", "pending", "inconclusive", "missing"]


@bp.route("/")
def index():
    db = current_app.get_db()
    try:
        status_filter = request.args.get("status")
        if status_filter and status_filter in VALID_STATUSES:
            rows = db.fetchall(
                "SELECT * FROM evidence_items WHERE status = ? ORDER BY id DESC",
                (status_filter,),
            )
        else:
            rows = db.fetchall("SELECT * FROM evidence_items ORDER BY id DESC")
        items = [dict(row) for row in rows]
        if request.headers.get("HX-Request"):
            return render_template("evidence.html", items=items,
                                   statuses=VALID_STATUSES,
                                   active_status=status_filter)
        return render_template("base.html", page="evidence", items=items,
                               statuses=VALID_STATUSES,
                               active_status=status_filter,
                               case=current_app.get_current_case_slug())
    finally:
        db.close()


@bp.route("/", methods=["POST"])
def create():
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO evidence_items (name, evidence_type, description, status, source_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    request.form["name"],
                    request.form.get("evidence_type", "physical"),
                    request.form.get("description") or None,
                    request.form.get("status", "known"),
                    int(request.form["source_id"]) if request.form.get("source_id") else None,
                ),
            )
        rows = db.fetchall("SELECT * FROM evidence_items ORDER BY id DESC")
        items = [dict(row) for row in rows]
        return render_template("evidence.html", items=items,
                               statuses=VALID_STATUSES, active_status=None)
    finally:
        db.close()


@bp.route("/<int:item_id>")
def detail(item_id):
    db = current_app.get_db()
    try:
        row = db.fetchone("SELECT * FROM evidence_items WHERE id = ?", (item_id,))
        if not row:
            return "Not found", 404
        attached = db.fetchall(
            "SELECT a.id, a.filename, a.mime_type FROM attachments a "
            "JOIN attachment_links al ON a.id = al.attachment_id "
            "WHERE al.entity_type = 'evidence' AND al.entity_id = ?",
            (item_id,),
        )
        return render_template("partials/evidence_detail.html", item=dict(row),
                               attached_files=[dict(r) for r in attached])
    finally:
        db.close()


@bp.route("/<int:item_id>", methods=["PUT"])
def update(item_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "UPDATE evidence_items SET name=?, evidence_type=?, "
                "description=?, status=? WHERE id=?",
                (
                    request.form["name"],
                    request.form.get("evidence_type", "physical"),
                    request.form.get("description") or None,
                    request.form.get("status", "known"),
                    item_id,
                ),
            )
        row = db.fetchone("SELECT * FROM evidence_items WHERE id = ?", (item_id,))
        return render_template("partials/evidence_detail.html", item=dict(row))
    finally:
        db.close()


@bp.route("/<int:item_id>", methods=["DELETE"])
def delete(item_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute("DELETE FROM evidence_items WHERE id = ?", (item_id,))
        return ""
    finally:
        db.close()

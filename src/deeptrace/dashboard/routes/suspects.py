"""Suspect pools CRUD routes."""

from flask import Blueprint, current_app, render_template, request

bp = Blueprint("suspects", __name__)


@bp.route("/")
def index():
    db = current_app.get_db()
    try:
        rows = db.fetchall("SELECT * FROM suspect_pools ORDER BY id")
        pools = [dict(row) for row in rows]
        if request.headers.get("HX-Request"):
            return render_template("suspects.html", pools=pools)
        return render_template("base.html", page="suspects", pools=pools,
                               case=current_app.get_current_case_slug())
    finally:
        db.close()


@bp.route("/", methods=["POST"])
def create():
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO suspect_pools (category, description, priority, "
                "supporting_evidence) VALUES (?, ?, ?, ?)",
                (
                    request.form["category"],
                    request.form["description"],
                    request.form.get("priority", "medium"),
                    request.form.get("supporting_evidence") or None,
                ),
            )
        rows = db.fetchall("SELECT * FROM suspect_pools ORDER BY id")
        pools = [dict(row) for row in rows]
        return render_template("suspects.html", pools=pools)
    finally:
        db.close()


@bp.route("/<int:pool_id>")
def detail(pool_id):
    db = current_app.get_db()
    try:
        row = db.fetchone("SELECT * FROM suspect_pools WHERE id = ?", (pool_id,))
        if not row:
            return "Not found", 404
        attached = db.fetchall(
            "SELECT a.id, a.filename, a.mime_type FROM attachments a "
            "JOIN attachment_links al ON a.id = al.attachment_id "
            "WHERE al.entity_type = 'suspect' AND al.entity_id = ?",
            (pool_id,),
        )
        return render_template("partials/suspect_detail.html", pool=dict(row),
                               attached_files=[dict(r) for r in attached])
    finally:
        db.close()


@bp.route("/<int:pool_id>", methods=["PUT"])
def update(pool_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "UPDATE suspect_pools SET category=?, description=?, "
                "priority=?, supporting_evidence=? WHERE id=?",
                (
                    request.form["category"],
                    request.form["description"],
                    request.form.get("priority", "medium"),
                    request.form.get("supporting_evidence") or None,
                    pool_id,
                ),
            )
        row = db.fetchone("SELECT * FROM suspect_pools WHERE id = ?", (pool_id,))
        return render_template("partials/suspect_detail.html", pool=dict(row))
    finally:
        db.close()


@bp.route("/<int:pool_id>", methods=["DELETE"])
def delete(pool_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute("DELETE FROM suspect_pools WHERE id = ?", (pool_id,))
        return ""
    finally:
        db.close()

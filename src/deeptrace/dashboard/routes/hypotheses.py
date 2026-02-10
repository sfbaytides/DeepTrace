"""Hypotheses CRUD routes."""

from flask import Blueprint, current_app, render_template, request

bp = Blueprint("hypotheses", __name__)

VALID_TIERS = ["most-probable", "plausible", "less-likely", "unlikely"]


@bp.route("/")
def index():
    db = current_app.get_db()
    try:
        rows = db.fetchall("SELECT * FROM hypotheses ORDER BY id")
        hypotheses = [dict(row) for row in rows]
        by_tier = {t: [] for t in VALID_TIERS}
        for h in hypotheses:
            tier = h["tier"]
            if tier in by_tier:
                by_tier[tier].append(h)
        if request.headers.get("HX-Request"):
            return render_template("hypotheses.html", by_tier=by_tier,
                                   tiers=VALID_TIERS)
        return render_template("base.html", page="hypotheses", by_tier=by_tier,
                               tiers=VALID_TIERS,
                               case=current_app.get_current_case_slug())
    finally:
        db.close()


@bp.route("/", methods=["POST"])
def create():
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO hypotheses (description, tier, supporting_evidence, "
                "contradicting_evidence, open_questions) VALUES (?, ?, ?, ?, ?)",
                (
                    request.form["description"],
                    request.form.get("tier", "plausible"),
                    request.form.get("supporting_evidence") or None,
                    request.form.get("contradicting_evidence") or None,
                    request.form.get("open_questions") or None,
                ),
            )
        rows = db.fetchall("SELECT * FROM hypotheses ORDER BY id")
        hypotheses = [dict(row) for row in rows]
        by_tier = {t: [] for t in VALID_TIERS}
        for h in hypotheses:
            tier = h["tier"]
            if tier in by_tier:
                by_tier[tier].append(h)
        return render_template("hypotheses.html", by_tier=by_tier, tiers=VALID_TIERS)
    finally:
        db.close()


@bp.route("/<int:hyp_id>")
def detail(hyp_id):
    db = current_app.get_db()
    try:
        row = db.fetchone("SELECT * FROM hypotheses WHERE id = ?", (hyp_id,))
        if not row:
            return "Not found", 404
        attached = db.fetchall(
            "SELECT a.id, a.filename, a.mime_type FROM attachments a "
            "JOIN attachment_links al ON a.id = al.attachment_id "
            "WHERE al.entity_type = 'hypothesis' AND al.entity_id = ?",
            (hyp_id,),
        )
        return render_template("partials/hypothesis_detail.html", hypothesis=dict(row),
                               tiers=VALID_TIERS,
                               attached_files=[dict(r) for r in attached])
    finally:
        db.close()


@bp.route("/<int:hyp_id>", methods=["PUT"])
def update(hyp_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "UPDATE hypotheses SET description=?, tier=?, supporting_evidence=?, "
                "contradicting_evidence=?, open_questions=?, "
                "updated_at=datetime('now') WHERE id=?",
                (
                    request.form["description"],
                    request.form.get("tier", "plausible"),
                    request.form.get("supporting_evidence") or None,
                    request.form.get("contradicting_evidence") or None,
                    request.form.get("open_questions") or None,
                    hyp_id,
                ),
            )
        row = db.fetchone("SELECT * FROM hypotheses WHERE id = ?", (hyp_id,))
        return render_template("partials/hypothesis_detail.html", hypothesis=dict(row),
                               tiers=VALID_TIERS)
    finally:
        db.close()


@bp.route("/<int:hyp_id>", methods=["DELETE"])
def delete(hyp_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute("DELETE FROM hypotheses WHERE id = ?", (hyp_id,))
        return ""
    finally:
        db.close()

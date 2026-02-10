"""ACH matrix routes."""

from flask import Blueprint, current_app, render_template, request

bp = Blueprint("ach", __name__)


@bp.route("/")
def index():
    db = current_app.get_db()
    try:
        hypotheses = [dict(r) for r in db.fetchall("SELECT * FROM hypotheses ORDER BY id")]
        evidence = [dict(r) for r in db.fetchall("SELECT * FROM evidence_items ORDER BY id")]
        scores = [
            dict(r) for r in db.fetchall("SELECT * FROM hypothesis_evidence_scores")
        ]

        # Build matrix lookup: (hypothesis_id, evidence_id) -> score dict
        matrix = {}
        for s in scores:
            matrix[(s["hypothesis_id"], s["evidence_id"])] = s

        if request.headers.get("HX-Request"):
            return render_template("ach.html", hypotheses=hypotheses,
                                   evidence=evidence, matrix=matrix)
        return render_template("base.html", page="ach", hypotheses=hypotheses,
                               evidence=evidence, matrix=matrix,
                               case=current_app.get_current_case_slug())
    finally:
        db.close()


@bp.route("/", methods=["POST"])
def create():
    db = current_app.get_db()
    try:
        h_id = int(request.form["hypothesis_id"])
        e_id = int(request.form["evidence_id"])
        consistency = request.form.get("consistency", "N")
        weight = request.form.get("diagnostic_weight", "M")

        # Upsert: delete existing then insert
        with db.transaction() as cur:
            cur.execute(
                "DELETE FROM hypothesis_evidence_scores "
                "WHERE hypothesis_id = ? AND evidence_id = ?",
                (h_id, e_id),
            )
            cur.execute(
                "INSERT INTO hypothesis_evidence_scores "
                "(hypothesis_id, evidence_id, consistency, diagnostic_weight) "
                "VALUES (?, ?, ?, ?)",
                (h_id, e_id, consistency, weight),
            )

        # Return refreshed matrix
        hypotheses = [dict(r) for r in db.fetchall("SELECT * FROM hypotheses ORDER BY id")]
        evidence = [dict(r) for r in db.fetchall("SELECT * FROM evidence_items ORDER BY id")]
        scores = [
            dict(r) for r in db.fetchall("SELECT * FROM hypothesis_evidence_scores")
        ]
        matrix = {}
        for s in scores:
            matrix[(s["hypothesis_id"], s["evidence_id"])] = s

        return render_template("ach.html", hypotheses=hypotheses,
                               evidence=evidence, matrix=matrix)
    finally:
        db.close()


@bp.route("/<int:h_id>/<int:e_id>/edit")
def edit_cell(h_id, e_id):
    """Return an inline edit form for a single ACH cell."""
    db = current_app.get_db()
    try:
        score = db.fetchone(
            "SELECT * FROM hypothesis_evidence_scores "
            "WHERE hypothesis_id = ? AND evidence_id = ?",
            (h_id, e_id),
        )
        current = dict(score) if score else {"consistency": "", "diagnostic_weight": "M"}
        return render_template("partials/ach_cell_edit.html",
                               h_id=h_id, e_id=e_id, current=current)
    finally:
        db.close()

"""Network graph routes — serves JSON for vis.js and the graph panel."""

from flask import Blueprint, current_app, jsonify, render_template, request

bp = Blueprint("network", __name__)

NODE_COLORS = {
    "entity": "#3498db",
    "evidence": "#e74c3c",
    "event": "#2ecc71",
    "hypothesis": "#f39c12",
    "suspect_pool": "#9b59b6",
    "source": "#95a5a6",
    "attachment": "#ec4899",
}

NODE_SHAPES = {
    "entity": "dot",
    "evidence": "triangle",
    "event": "square",
    "hypothesis": "diamond",
    "suspect_pool": "star",
    "source": "database",
    "attachment": "image",
}


def _build_graph_data(db):
    """Build vis.js-compatible node/edge arrays from the case database."""
    nodes = []
    edges = []

    # Entities
    for row in db.fetchall("SELECT * FROM entities"):
        nodes.append({
            "id": f"entity:{row['id']}",
            "label": row["name"],
            "group": "entity",
            "title": f"<b>{row['name']}</b><br>Type: {row['entity_type']}<br>"
                     f"Confidence: {row['confidence']}",
            "color": NODE_COLORS["entity"],
            "shape": NODE_SHAPES["entity"],
        })

    # Evidence
    for row in db.fetchall("SELECT * FROM evidence_items"):
        nodes.append({
            "id": f"evidence:{row['id']}",
            "label": row["name"][:30],
            "group": "evidence",
            "title": f"<b>{row['name']}</b><br>Type: {row['evidence_type']}<br>"
                     f"Status: {row['status']}",
            "color": NODE_COLORS["evidence"],
            "shape": NODE_SHAPES["evidence"],
        })

    # Events
    for row in db.fetchall("SELECT * FROM events ORDER BY timestamp_start"):
        desc = row["description"]
        short = (desc[:30] + "...") if len(desc) > 30 else desc
        nodes.append({
            "id": f"event:{row['id']}",
            "label": short,
            "group": "event",
            "title": f"<b>{desc}</b><br>Time: {row['timestamp_start'] or '?'}<br>"
                     f"Confidence: {row['confidence']}",
            "color": NODE_COLORS["event"],
            "shape": NODE_SHAPES["event"],
        })

    # Hypotheses
    for row in db.fetchall("SELECT * FROM hypotheses"):
        desc = row["description"]
        short = (desc[:30] + "...") if len(desc) > 30 else desc
        nodes.append({
            "id": f"hypothesis:{row['id']}",
            "label": short,
            "group": "hypothesis",
            "title": f"<b>{desc}</b><br>Tier: {row['tier']}",
            "color": NODE_COLORS["hypothesis"],
            "shape": NODE_SHAPES["hypothesis"],
        })

    # Suspect pools
    for row in db.fetchall("SELECT * FROM suspect_pools"):
        nodes.append({
            "id": f"suspect:{row['id']}",
            "label": row["category"][:30],
            "group": "suspect_pool",
            "title": f"<b>{row['category']}</b><br>Priority: {row['priority']}",
            "color": NODE_COLORS["suspect_pool"],
            "shape": NODE_SHAPES["suspect_pool"],
        })

    # Sources
    for row in db.fetchall("SELECT * FROM sources"):
        nodes.append({
            "id": f"source:{row['id']}",
            "label": f"Src {row['id']} ({row['source_type']})",
            "group": "source",
            "title": f"<b>Source {row['id']}</b><br>Type: {row['source_type']}<br>"
                     f"Reliability: {row['reliability_score']}",
            "color": NODE_COLORS["source"],
            "shape": NODE_SHAPES["source"],
        })

    # --- Edges ---

    # Relationships
    for row in db.fetchall("SELECT * FROM relationships"):
        edges.append({
            "from": f"entity:{row['entity_a_id']}",
            "to": f"entity:{row['entity_b_id']}",
            "label": row["relationship_type"],
            "color": "#3498db",
            "title": f"{row['relationship_type']} (strength: {row['strength']})",
        })

    # Entity aliases
    for row in db.fetchall(
        "SELECT id, canonical_id FROM entities WHERE canonical_id IS NOT NULL"
    ):
        edges.append({
            "from": f"entity:{row['id']}",
            "to": f"entity:{row['canonical_id']}",
            "label": "alias",
            "dashes": True,
            "color": "#95a5a6",
        })

    # Evidence -> source
    for row in db.fetchall(
        "SELECT id, source_id FROM evidence_items WHERE source_id IS NOT NULL"
    ):
        edges.append({
            "from": f"evidence:{row['id']}",
            "to": f"source:{row['source_id']}",
            "color": "#2ecc71",
            "title": "sourced from",
        })

    # Event -> source
    for row in db.fetchall(
        "SELECT id, source_id FROM events WHERE source_id IS NOT NULL"
    ):
        edges.append({
            "from": f"event:{row['id']}",
            "to": f"source:{row['source_id']}",
            "color": "#2ecc71",
            "title": "sourced from",
        })

    # Entity -> source
    for row in db.fetchall(
        "SELECT id, source_id FROM entities WHERE source_id IS NOT NULL"
    ):
        edges.append({
            "from": f"entity:{row['id']}",
            "to": f"source:{row['source_id']}",
            "color": "#2ecc71",
            "title": "sourced from",
        })

    # ACH scores: hypothesis <-> evidence
    for row in db.fetchall("SELECT * FROM hypothesis_evidence_scores"):
        edges.append({
            "from": f"hypothesis:{row['hypothesis_id']}",
            "to": f"evidence:{row['evidence_id']}",
            "label": f"ACH:{row['consistency']}",
            "color": "#f39c12",
            "title": f"Consistency: {row['consistency']}, Weight: {row['diagnostic_weight']}",
            "width": 2,
        })

    # Attachments
    for row in db.fetchall(
        "SELECT id, filename, mime_type FROM attachments"
    ):
        name = row["filename"]
        short = (name[:25] + "...") if len(name) > 25 else name
        nodes.append({
            "id": f"attachment:{row['id']}",
            "label": short,
            "group": "attachment",
            "title": f"<b>{name}</b><br>Type: {row['mime_type']}",
            "color": NODE_COLORS["attachment"],
            "shape": "dot",
        })

    # Attachment links -> entities
    type_to_prefix = {
        "evidence": "evidence",
        "source": "source",
        "event": "event",
        "hypothesis": "hypothesis",
        "suspect": "suspect",
    }
    for row in db.fetchall("SELECT * FROM attachment_links"):
        prefix = type_to_prefix.get(row["entity_type"])
        if prefix:
            edges.append({
                "from": f"attachment:{row['attachment_id']}",
                "to": f"{prefix}:{row['entity_id']}",
                "dashes": True,
                "color": "#ec4899",
                "title": "attached to",
            })

    # Scale node sizes by connection count
    edge_count = {}
    for e in edges:
        edge_count[e["from"]] = edge_count.get(e["from"], 0) + 1
        edge_count[e["to"]] = edge_count.get(e["to"], 0) + 1
    for node in nodes:
        count = edge_count.get(node["id"], 0)
        node["size"] = max(12, 10 + count * 4)

    return {"nodes": nodes, "edges": edges}


@bp.route("/")
def index():
    if request.headers.get("HX-Request"):
        return render_template("network.html")
    return render_template("base.html", page="network",
                           case=current_app.get_current_case_slug())


@bp.route("/graph")
def graph_data():
    """Return JSON graph data for vis.js."""
    db = current_app.get_db()
    try:
        data = _build_graph_data(db)
        return jsonify(data)
    finally:
        db.close()

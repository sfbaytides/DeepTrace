"""AI-powered source analysis routes: classify, extract, cross-reference."""

import json
import os
from datetime import UTC, datetime

import requests
from flask import Blueprint, current_app, render_template, request

bp = Blueprint("source_ai", __name__)

# Carl (Ollama) configuration
CARL_API_URL = os.getenv("CARL_API_URL", "https://ai.baytides.org/api/generate")
CARL_DEFAULT_MODEL = os.getenv("CARL_DEFAULT_MODEL", "qwen2.5:3b-instruct")


# ---------------------------------------------------------------------------
# Shared Carl helper
# ---------------------------------------------------------------------------

def _call_carl(prompt: str, system: str, max_tokens: int = 4096) -> str:
    """Call Carl AI (Ollama) and return the text response."""
    full_prompt = f"{system}\n\nUser Query:\n{prompt}"

    payload = {
        "model": CARL_DEFAULT_MODEL,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": max_tokens
        }
    }

    response = requests.post(CARL_API_URL, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    return data.get("response", "")


def _record_analysis(db, source_id: int, mode: str, prompt: str,
                     response: str, success: bool = True, error: str | None = None) -> int:
    """Insert an ai_analyses record and return its id."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    with db.transaction() as cur:
        cur.execute(
            "INSERT INTO ai_analyses (entity_type, entity_id, mode, prompt, "
            "response, model, success, error, created_at) "
            "VALUES ('source', ?, ?, ?, ?, ?, ?, ?, ?)",
            (source_id, mode, prompt[:2000], response[:50000], CARL_DEFAULT_MODEL,
             1 if success else 0, error, now),
        )
        return cur.lastrowid


# ---------------------------------------------------------------------------
# Phase A: Classify source
# ---------------------------------------------------------------------------

@bp.route("/<int:source_id>/ai/classify", methods=["POST"])
def classify(source_id):
    """AI classifies source type, rates reliability, assesses bias."""
    db = current_app.get_db()
    try:
        row = db.fetchone("SELECT * FROM sources WHERE id = ?", (source_id,))
        if not row:
            return "Not found", 404
        source = dict(row)

        system = (
            "You are a source intelligence analyst using the NATO/Admiralty rating system. "
            "Assess sources for reliability and information accuracy. "
            "Always respond in valid JSON."
        )
        prompt = f"""Analyze this source and provide a classification.

URL: {source.get('url') or 'N/A'}
Source Type: {source.get('source_type', 'unknown')}
Current Reliability: {source.get('source_reliability') or 'unrated'}
Current Accuracy: {source.get('information_accuracy') or 'unrated'}

Source Text (first 3000 chars):
{(source.get('raw_text') or '')[:3000]}

Respond in JSON:
{{
  "source_type": "news|official|social|document|academic|witness|manual",
  "source_reliability": "A|B|C|D|E|F",
  "source_reliability_reason": "brief explanation",
  "information_accuracy": "1|2|3|4|5|6",
  "information_accuracy_reason": "brief explanation",
  "bias_assessment": "brief description of potential biases",
  "access_assessment": "how this source obtained its information",
  "credibility_notes": "overall assessment"
}}"""

        try:
            response_text = _call_carl(prompt, system, max_tokens=1024)
            # Extract JSON from response (handle markdown code blocks)
            json_str = response_text
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            result = json.loads(json_str.strip())

            analysis_id = _record_analysis(db, source_id, "classify", prompt, response_text)

            return render_template("partials/source_ai_classify.html",
                                   source=source, result=result,
                                   analysis_id=analysis_id)

        except requests.exceptions.Timeout:
            return '<div style="color:var(--accent-red);padding:12px">Carl AI request timed out. The model may be loading.</div>'
        except requests.exceptions.RequestException as e:
            return f'<div style="color:var(--accent-red);padding:12px">Carl AI request failed: {e}</div>'
        except Exception as e:
            _record_analysis(db, source_id, "classify", prompt,
                             str(e), success=False, error=str(e))
            return f'<div style="color:var(--accent-red);padding:12px">AI analysis failed: {e}</div>'

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase A: Apply classification
# ---------------------------------------------------------------------------

@bp.route("/<int:source_id>/ai/apply-classify", methods=["POST"])
def apply_classify(source_id):
    """Apply AI classification results to the source record."""
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "UPDATE sources SET source_type=?, source_reliability=?, "
                "information_accuracy=?, bias_assessment=?, access_assessment=? "
                "WHERE id=?",
                (
                    request.form.get("source_type"),
                    request.form.get("source_reliability"),
                    request.form.get("information_accuracy"),
                    request.form.get("bias_assessment"),
                    request.form.get("access_assessment"),
                    source_id,
                ),
            )
        # Re-render the source detail
        row = db.fetchone("SELECT * FROM sources WHERE id = ?", (source_id,))
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


# ---------------------------------------------------------------------------
# Phase B: Extract entities, evidence, events
# ---------------------------------------------------------------------------

@bp.route("/<int:source_id>/ai/extract", methods=["POST"])
def extract(source_id):
    """AI extracts entities, evidence, events, relationships from source text."""
    db = current_app.get_db()
    try:
        row = db.fetchone("SELECT * FROM sources WHERE id = ?", (source_id,))
        if not row:
            return "Not found", 404
        source = dict(row)

        system = (
            "You are a criminal investigation analyst extracting structured data "
            "from source documents. Extract all relevant entities, evidence items, "
            "timeline events, and relationships. Be thorough but precise. "
            "Always respond in valid JSON."
        )
        prompt = f"""Extract structured investigation data from this source.

Source #{source_id} ({source.get('source_type', 'unknown')}):
URL: {source.get('url') or 'N/A'}

Full Text:
{(source.get('raw_text') or '')[:8000]}

Extract and respond in JSON:
{{
  "entities": [
    {{"name": "...", "entity_type": "person|organization|location|vehicle|phone|email|other", "description": "..."}}
  ],
  "evidence": [
    {{"name": "...", "evidence_type": "physical|digital|testimonial|documentary|circumstantial", "description": "...", "status": "known|pending|missing"}}
  ],
  "events": [
    {{"description": "...", "timestamp_start": "YYYY-MM-DD or null", "timestamp_end": "YYYY-MM-DD or null", "confidence": "high|medium|low"}}
  ],
  "relationships": [
    {{"entity_a": "name", "entity_b": "name", "relationship_type": "family|associate|witness|suspect|victim|location|employment|other", "description": "..."}}
  ]
}}

Rules:
- Only include items clearly supported by the text
- Use "null" for unknown dates, not guesses
- entity_type and evidence_type must match the enum values above exactly
- Keep descriptions concise (under 200 chars each)"""

        try:
            response_text = _call_carl(prompt, system, max_tokens=4096)
            json_str = response_text
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            result = json.loads(json_str.strip())

            analysis_id = _record_analysis(db, source_id, "extract", prompt, response_text)

            # Stage items for human review
            staged_items = []
            for item_type in ("entities", "evidence", "events", "relationships"):
                singular = item_type.rstrip("s") if item_type != "evidence" else "evidence"
                for item in result.get(item_type, []):
                    with db.transaction() as cur:
                        cur.execute(
                            "INSERT INTO ai_staged_items (analysis_id, source_id, "
                            "item_type, item_data, status) VALUES (?, ?, ?, ?, 'pending')",
                            (analysis_id, source_id, singular, json.dumps(item)),
                        )
                        staged_items.append({
                            "id": cur.lastrowid,
                            "item_type": singular,
                            "item_data": item,
                            "status": "pending",
                        })

            return render_template("partials/source_ai_extract.html",
                                   source=source, staged_items=staged_items,
                                   analysis_id=analysis_id)

        except requests.exceptions.Timeout:
            return '<div style="color:var(--accent-red);padding:12px">Carl AI request timed out. The model may be loading.</div>'
        except requests.exceptions.RequestException as e:
            return f'<div style="color:var(--accent-red);padding:12px">Carl AI request failed: {e}</div>'
        except Exception as e:
            _record_analysis(db, source_id, "extract", prompt,
                             str(e), success=False, error=str(e))
            return f'<div style="color:var(--accent-red);padding:12px">AI extraction failed: {e}</div>'

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase B: Accept / Reject staged items
# ---------------------------------------------------------------------------

@bp.route("/ai/staged/<int:item_id>/accept", methods=["POST"])
def accept_item(item_id):
    """Accept a staged item — INSERT into the real table."""
    db = current_app.get_db()
    try:
        row = db.fetchone("SELECT * FROM ai_staged_items WHERE id = ?", (item_id,))
        if not row:
            return "Not found", 404

        item = dict(row)
        data = json.loads(item["item_data"])
        source_id = item["source_id"]

        with db.transaction() as cur:
            if item["item_type"] == "entity":
                cur.execute(
                    "INSERT INTO entities (name, entity_type, description, source_id) "
                    "VALUES (?, ?, ?, ?)",
                    (data["name"], data.get("entity_type", "other"),
                     data.get("description"), source_id),
                )
            elif item["item_type"] == "evidence":
                cur.execute(
                    "INSERT INTO evidence_items (name, evidence_type, description, "
                    "status, source_id) VALUES (?, ?, ?, ?, ?)",
                    (data["name"], data.get("evidence_type", "documentary"),
                     data.get("description"), data.get("status", "known"), source_id),
                )
            elif item["item_type"] == "event":
                cur.execute(
                    "INSERT INTO events (description, timestamp_start, timestamp_end, "
                    "confidence, source_id) VALUES (?, ?, ?, ?, ?)",
                    (data["description"],
                     data.get("timestamp_start"),
                     data.get("timestamp_end"),
                     data.get("confidence", "medium"), source_id),
                )
            elif item["item_type"] == "relationship":
                # Look up or create entity_a and entity_b
                a_name = data.get("entity_a", "Unknown")
                b_name = data.get("entity_b", "Unknown")

                a_row = cur.execute("SELECT id FROM entities WHERE name = ?", (a_name,)).fetchone()
                if a_row:
                    a_id = a_row[0]
                else:
                    cur.execute("INSERT INTO entities (name, entity_type, source_id) VALUES (?, 'other', ?)",
                                (a_name, source_id))
                    a_id = cur.lastrowid

                b_row = cur.execute("SELECT id FROM entities WHERE name = ?", (b_name,)).fetchone()
                if b_row:
                    b_id = b_row[0]
                else:
                    cur.execute("INSERT INTO entities (name, entity_type, source_id) VALUES (?, 'other', ?)",
                                (b_name, source_id))
                    b_id = cur.lastrowid

                cur.execute(
                    "INSERT INTO relationships (entity_a_id, entity_b_id, "
                    "relationship_type, description, source_id) VALUES (?, ?, ?, ?, ?)",
                    (a_id, b_id, data.get("relationship_type", "other"),
                     data.get("description"), source_id),
                )

            # Mark as accepted
            cur.execute("UPDATE ai_staged_items SET status = 'accepted' WHERE id = ?",
                        (item_id,))

        return f'<div class="staged-item accepted" style="opacity:0.6"><span class="badge" style="background:var(--accent-green,#22c55e);color:#fff">Accepted</span> {item["item_type"]}: {data.get("name") or data.get("description", "")[:60]}</div>'

    finally:
        db.close()


@bp.route("/ai/staged/<int:item_id>/reject", methods=["POST"])
def reject_item(item_id):
    """Reject a staged item."""
    db = current_app.get_db()
    try:
        row = db.fetchone("SELECT * FROM ai_staged_items WHERE id = ?", (item_id,))
        if not row:
            return "Not found", 404

        item = dict(row)
        data = json.loads(item["item_data"])

        with db.transaction() as cur:
            cur.execute("UPDATE ai_staged_items SET status = 'rejected' WHERE id = ?",
                        (item_id,))

        return f'<div class="staged-item rejected" style="opacity:0.4;text-decoration:line-through"><span class="badge" style="background:var(--text-dim);color:#fff">Rejected</span> {item["item_type"]}: {data.get("name") or data.get("description", "")[:60]}</div>'

    finally:
        db.close()


@bp.route("/ai/staged/batch", methods=["POST"])
def batch_action():
    """Accept or reject multiple staged items at once."""
    db = current_app.get_db()
    try:
        data = request.get_json(silent=True) or {}
        action = data.get("action", "accept")
        item_ids = data.get("ids", [])

        if not item_ids:
            return "No items specified", 400

        results = []
        for item_id in item_ids:
            if action == "accept":
                # Re-use the accept logic
                row = db.fetchone("SELECT * FROM ai_staged_items WHERE id = ? AND status = 'pending'",
                                  (item_id,))
                if row:
                    item = dict(row)
                    item_data = json.loads(item["item_data"])
                    source_id = item["source_id"]

                    with db.transaction() as cur:
                        if item["item_type"] == "entity":
                            cur.execute(
                                "INSERT INTO entities (name, entity_type, description, source_id) "
                                "VALUES (?, ?, ?, ?)",
                                (item_data["name"], item_data.get("entity_type", "other"),
                                 item_data.get("description"), source_id),
                            )
                        elif item["item_type"] == "evidence":
                            cur.execute(
                                "INSERT INTO evidence_items (name, evidence_type, description, "
                                "status, source_id) VALUES (?, ?, ?, ?, ?)",
                                (item_data["name"], item_data.get("evidence_type", "documentary"),
                                 item_data.get("description"), item_data.get("status", "known"),
                                 source_id),
                            )
                        elif item["item_type"] == "event":
                            cur.execute(
                                "INSERT INTO events (description, timestamp_start, timestamp_end, "
                                "confidence, source_id) VALUES (?, ?, ?, ?, ?)",
                                (item_data["description"],
                                 item_data.get("timestamp_start"),
                                 item_data.get("timestamp_end"),
                                 item_data.get("confidence", "medium"), source_id),
                            )
                        cur.execute("UPDATE ai_staged_items SET status = 'accepted' WHERE id = ?",
                                    (item_id,))
                    results.append({"id": item_id, "status": "accepted"})
            else:
                with db.transaction() as cur:
                    cur.execute("UPDATE ai_staged_items SET status = 'rejected' WHERE id = ?",
                                (item_id,))
                results.append({"id": item_id, "status": "rejected"})

        count = len(results)
        verb = "accepted" if action == "accept" else "rejected"
        return f'<div style="padding:12px;color:var(--accent-green,#22c55e)">{count} items {verb} successfully. Refresh the page to see updates.</div>'

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase C: Cross-reference against existing case data
# ---------------------------------------------------------------------------

@bp.route("/<int:source_id>/ai/cross-reference", methods=["POST"])
def cross_reference(source_id):
    """AI compares staged/source data against existing case data."""
    db = current_app.get_db()
    try:
        row = db.fetchone("SELECT * FROM sources WHERE id = ?", (source_id,))
        if not row:
            return "Not found", 404
        source = dict(row)

        # Gather existing case data for context
        entities = [dict(r) for r in db.fetchall(
            "SELECT id, name, entity_type, description FROM entities ORDER BY id")]
        evidence = [dict(r) for r in db.fetchall(
            "SELECT id, name, evidence_type, description, status FROM evidence_items ORDER BY id")]
        events = [dict(r) for r in db.fetchall(
            "SELECT id, description, timestamp_start FROM events ORDER BY timestamp_start")]
        suspects = [dict(r) for r in db.fetchall(
            "SELECT id, category, description FROM suspect_pools ORDER BY id")]

        # Also get pending staged items for this source
        staged = [dict(r) for r in db.fetchall(
            "SELECT item_type, item_data FROM ai_staged_items "
            "WHERE source_id = ? AND status = 'pending'", (source_id,))]
        staged_parsed = []
        for s in staged:
            try:
                staged_parsed.append({"type": s["item_type"], "data": json.loads(s["item_data"])})
            except json.JSONDecodeError:
                pass

        system = (
            "You are an intelligence analyst cross-referencing new source data "
            "against existing case information. Identify duplicates, "
            "inconsistencies, corroborations, and new connections. "
            "Always respond in valid JSON."
        )

        # Build context - limit to reasonable sizes
        entities_ctx = json.dumps(entities[:50], default=str)
        evidence_ctx = json.dumps(evidence[:50], default=str)
        events_ctx = json.dumps(events[:50], default=str)
        suspects_ctx = json.dumps(suspects[:20], default=str)
        staged_ctx = json.dumps(staged_parsed[:30], default=str)

        prompt = f"""Cross-reference this source against existing case data.

SOURCE #{source_id}:
{(source.get('raw_text') or '')[:3000]}

EXISTING ENTITIES:
{entities_ctx[:3000]}

EXISTING EVIDENCE:
{evidence_ctx[:3000]}

EXISTING TIMELINE:
{events_ctx[:2000]}

EXISTING SUSPECTS:
{suspects_ctx[:1000]}

PENDING STAGED ITEMS FROM THIS SOURCE:
{staged_ctx[:2000]}

Analyze and respond in JSON:
{{
  "duplicates": [
    {{"new_item": "description of new item", "existing_item": "description of matching existing item", "existing_id": 123, "existing_type": "entity|evidence|event", "confidence": "high|medium|low"}}
  ],
  "inconsistencies": [
    {{"description": "what conflicts", "source_claim": "what this source says", "existing_claim": "what existing data says", "severity": "high|medium|low"}}
  ],
  "corroborations": [
    {{"description": "what is confirmed", "new_item": "from this source", "existing_item": "from existing data", "strength": "strong|moderate|weak"}}
  ],
  "new_connections": [
    {{"description": "newly discovered link", "entities_involved": ["name1", "name2"], "significance": "high|medium|low"}}
  ],
  "summary": "1-2 sentence overall assessment"
}}"""

        try:
            response_text = _call_carl(prompt, system, max_tokens=4096)
            json_str = response_text
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            result = json.loads(json_str.strip())

            _record_analysis(db, source_id, "cross-reference", prompt, response_text)

            return render_template("partials/source_ai_crossref.html",
                                   source=source, result=result)

        except requests.exceptions.Timeout:
            return '<div style="color:var(--accent-red);padding:12px">Carl AI request timed out. The model may be loading.</div>'
        except requests.exceptions.RequestException as e:
            return f'<div style="color:var(--accent-red);padding:12px">Carl AI request failed: {e}</div>'
        except Exception as e:
            _record_analysis(db, source_id, "cross-reference", prompt,
                             str(e), success=False, error=str(e))
            return f'<div style="color:var(--accent-red);padding:12px">Cross-reference failed: {e}</div>'

    finally:
        db.close()

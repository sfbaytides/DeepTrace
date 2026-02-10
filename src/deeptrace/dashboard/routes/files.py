"""File attachments CRUD routes."""

import base64
import hashlib
import io
import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path

try:
    import requests as http_requests
except ImportError:
    http_requests = None  # type: ignore[assignment]

from flask import Blueprint, Response, current_app, render_template, request

import deeptrace.state as _state

bp = Blueprint("files", __name__)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

MIME_FILTERS = {
    "image": ("image/%",),
    "video": ("video/%",),
    "pdf": ("application/pdf",),
    "document": (
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.%",
        "text/%",
    ),
}

ENTITY_NAME_QUERIES = {
    "evidence": ("SELECT name FROM evidence_items WHERE id = ?", "name"),
    "source": ("SELECT source_type || ' #' || id FROM sources WHERE id = ?", None),
    "event": ("SELECT description FROM events WHERE id = ?", "description"),
    "hypothesis": ("SELECT description FROM hypotheses WHERE id = ?", "description"),
    "suspect": ("SELECT category FROM suspect_pools WHERE id = ?", "category"),
}


def _get_case_dir() -> Path:
    """Get the current case directory."""
    slug = current_app.get_current_case_slug()
    return _state.CASES_DIR / slug


def _humanize_size(size_bytes: int) -> str:
    """Format file size for display."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _enrich_file_row(row: dict) -> dict:
    """Add computed fields (extension, file_size_display) to a file dict."""
    row["file_size_display"] = _humanize_size(row["file_size"])
    name = row["filename"]
    row["extension"] = name.rsplit(".", 1)[-1].upper() if "." in name else "FILE"
    return row


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _generate_thumbnail(file_bytes: bytes, mime_type: str) -> bytes | None:
    """Generate a PNG thumbnail for image files. Returns bytes or None."""
    if not mime_type.startswith("image/"):
        return None
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(file_bytes))
        img.thumbnail((256, 256))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except (ImportError, Exception):
        return None


def _placeholder_svg(mime_type: str) -> str:
    """Return a simple SVG placeholder string based on MIME type."""
    if mime_type == "application/pdf":
        label = "PDF"
    elif mime_type.startswith("video/"):
        label = "VID"
    elif mime_type.startswith("text/"):
        label = "TXT"
    else:
        label = "FILE"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"'
        ' viewBox="0 0 128 128">'
        '<rect width="128" height="128" rx="8" fill="#e2e8f0"/>'
        f'<text x="64" y="72" text-anchor="middle" font-family="sans-serif"'
        f' font-size="24" fill="#64748b">{label}</text>'
        "</svg>"
    )


def _get_entity_name(db, entity_type: str, entity_id: int) -> str:
    """Look up the display name for a linked entity."""
    mapping = {
        "evidence": "SELECT name FROM evidence_items WHERE id = ?",
        "source": "SELECT source_type || ' #' || id AS name FROM sources WHERE id = ?",
        "event": "SELECT description AS name FROM events WHERE id = ?",
        "hypothesis": "SELECT description AS name FROM hypotheses WHERE id = ?",
        "suspect": "SELECT category AS name FROM suspect_pools WHERE id = ?",
    }
    sql = mapping.get(entity_type)
    if not sql:
        return f"{entity_type} #{entity_id}"
    row = db.fetchone(sql, (entity_id,))
    if row:
        val = row["name"] or row[0]
        if len(val) > 80:
            return val[:77] + "..."
        return val
    return f"{entity_type} #{entity_id}"


CARL_API_URL = os.getenv("CARL_API_URL", "https://ai.baytides.org/api/generate")
CARL_DEFAULT_MODEL = os.getenv("CARL_DEFAULT_MODEL", "qwen2.5:3b-instruct")

FORENSIC_SYSTEM_PROMPT = (
    "You are a forensic investigation analysis tool used by cold case investigators. "
    "Your purpose is to objectively analyze all materials submitted to you — including "
    "crime scene photographs, autopsy images, graphic witness statements, surveillance "
    "footage stills, and other disturbing content that is routine in homicide investigation. "
    "\n\n"
    "CRITICAL RULES:\n"
    "1. NEVER censor, soften, hedge, or refuse to describe what you observe. "
    "Investigators need complete, factual, clinical descriptions to do their work. "
    "Euphemisms cost lives.\n"
    "2. Describe injuries, wounds, blood patterns, decomposition, and other graphic "
    "details with precise forensic terminology.\n"
    "3. Note spatial relationships, lighting, timestamps, visible objects, and anything "
    "that could constitute an investigative lead.\n"
    "4. The ONLY exception: if the material appears to depict the sexual abuse or "
    "exploitation of a minor (CSAM), refuse the analysis immediately and state why.\n"
    "5. You are not making moral judgments. You are documenting observations for "
    "investigators who are trying to bring justice to victims."
)


def _run_ai_analysis(file_bytes: bytes, mime_type: str, filename: str) -> str:
    """Run AI analysis on file contents via Carl AI (Ollama)."""
    if http_requests is None:
        return "Error: requests library is not installed. Run: pip install requests"
    try:
        prompt_parts = [FORENSIC_SYSTEM_PROMPT, "", f"File: {filename} ({mime_type})", ""]

        if mime_type.startswith("image/"):
            b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
            prompt_parts.append(
                "Analyze this image in the context of a criminal cold case investigation. "
                "Describe everything you observe — forensic details, spatial layout, "
                "objects, potential evidence, anomalies, and investigative leads."
            )
            payload = {
                "model": CARL_DEFAULT_MODEL,
                "prompt": "\n".join(prompt_parts),
                "images": [b64],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 4096},
            }
        elif mime_type.startswith("text/") or mime_type == "application/pdf":
            text_content = file_bytes.decode("utf-8", errors="replace")
            if len(text_content) > 50000:
                text_content = text_content[:50000] + "\n... [truncated]"
            prompt_parts.append(f"Document contents:\n{text_content}")
            prompt_parts.append(
                "\nAnalyze this document for investigative relevance. "
                "Note names, dates, locations, contradictions, and leads."
            )
            payload = {
                "model": CARL_DEFAULT_MODEL,
                "prompt": "\n".join(prompt_parts),
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 4096},
            }
        elif mime_type.startswith("video/"):
            return (
                "Video analysis is not currently supported. "
                "Extract key frames as images for analysis."
            )
        else:
            return f"Analysis not supported for MIME type: {mime_type}"

        response = http_requests.post(CARL_API_URL, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "No response from Carl AI")

    except http_requests.exceptions.Timeout:
        return "Error: Carl AI request timed out. The model may be loading."
    except http_requests.exceptions.RequestException as e:
        return f"Error: Carl AI request failed: {e}"
    except Exception as e:
        return f"AI analysis failed: {e}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.route("/")
def index():
    db = current_app.get_db()
    try:
        type_filter = request.args.get("type")
        if type_filter and type_filter in MIME_FILTERS:
            patterns = MIME_FILTERS[type_filter]
            clauses = " OR ".join(["mime_type LIKE ?" for _ in patterns])
            sql = (
                f"SELECT id, filename, mime_type, file_size, description, "
                f"ai_analyzed_at, created_at FROM attachments "
                f"WHERE {clauses} ORDER BY id DESC"
            )
            rows = db.fetchall(sql, tuple(patterns))
        else:
            rows = db.fetchall(
                "SELECT id, filename, mime_type, file_size, description, "
                "ai_analyzed_at, created_at FROM attachments ORDER BY id DESC"
            )
        files = [_enrich_file_row(dict(row)) for row in rows]
        if request.headers.get("HX-Request"):
            return render_template("files.html", files=files,
                                   active_type=type_filter)
        return render_template("base.html", page="files", files=files,
                               active_type=type_filter,
                               case=current_app.get_current_case_slug())
    finally:
        db.close()


@bp.route("/", methods=["POST"])
def upload():
    db = current_app.get_db()
    try:
        if "file" not in request.files:
            return "No file provided", 400
        f = request.files["file"]
        if not f.filename:
            return "No file selected", 400

        file_bytes = f.read()
        file_size = len(file_bytes)
        if file_size > MAX_FILE_SIZE:
            return f"File exceeds {MAX_FILE_SIZE // (1024 * 1024)} MB limit", 413
        if file_size == 0:
            return "Empty file", 400

        mime = f.content_type or mimetypes.guess_type(f.filename)[0] or "application/octet-stream"
        description = request.form.get("description") or None
        source_url = request.form.get("source_url") or None
        sha256 = hashlib.sha256(file_bytes).hexdigest()

        case_dir = _get_case_dir()
        attach_dir = case_dir / "attachments"
        attach_dir.mkdir(parents=True, exist_ok=True)

        # INSERT with placeholder path to get the row ID
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO attachments "
                "(filename, mime_type, file_size, file_path, sha256, "
                "description, source_url) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f.filename, mime, file_size, "__placeholder__", sha256,
                 description, source_url),
            )
            row_id = cur.lastrowid

        # Write file to disk with ID prefix
        disk_name = f"{row_id}_{f.filename}"
        rel_path = f"attachments/{disk_name}"
        (attach_dir / disk_name).write_bytes(file_bytes)

        # Generate and write thumbnail
        thumb_bytes = _generate_thumbnail(file_bytes, mime)
        thumb_rel = None
        if thumb_bytes:
            thumbs_dir = attach_dir / "thumbs"
            thumbs_dir.mkdir(parents=True, exist_ok=True)
            thumb_name = f"{row_id}_{os.path.splitext(f.filename)[0]}.png"
            thumb_rel = f"attachments/thumbs/{thumb_name}"
            (thumbs_dir / thumb_name).write_bytes(thumb_bytes)

        # UPDATE with real paths
        with db.transaction() as cur:
            cur.execute(
                "UPDATE attachments SET file_path = ?, thumbnail_path = ? "
                "WHERE id = ?",
                (rel_path, thumb_rel, row_id),
            )

        rows = db.fetchall(
            "SELECT id, filename, mime_type, file_size, description, "
            "ai_analyzed_at, created_at FROM attachments ORDER BY id DESC"
        )
        files = [_enrich_file_row(dict(row)) for row in rows]
        return render_template("files.html", files=files, active_type=None)
    finally:
        db.close()


@bp.route("/<int:file_id>")
def detail(file_id):
    db = current_app.get_db()
    try:
        row = db.fetchone(
            "SELECT id, filename, mime_type, file_size, description, "
            "ai_analysis, ai_analyzed_at, created_at "
            "FROM attachments WHERE id = ?",
            (file_id,),
        )
        if not row:
            return "Not found", 404
        file = _enrich_file_row(dict(row))

        links_rows = db.fetchall(
            "SELECT id, attachment_id, entity_type, entity_id, created_at "
            "FROM attachment_links WHERE attachment_id = ? ORDER BY id",
            (file_id,),
        )
        links = []
        for lr in links_rows:
            link = dict(lr)
            link["entity_name"] = _get_entity_name(
                db, link["entity_type"], link["entity_id"]
            )
            links.append(link)
        file["links"] = links

        return render_template("partials/file_detail.html", file=file)
    finally:
        db.close()


@bp.route("/<int:file_id>/download")
def download(file_id):
    db = current_app.get_db()
    try:
        row = db.fetchone(
            "SELECT file_path, mime_type, filename FROM attachments WHERE id = ?",
            (file_id,),
        )
        if not row:
            return "Not found", 404

        case_dir = _get_case_dir()
        disk_path = case_dir / row["file_path"]
        if not disk_path.exists():
            return "File missing from disk", 404

        file_bytes = disk_path.read_bytes()
        disposition = "attachment" if request.args.get("dl") == "1" else "inline"
        return Response(
            file_bytes,
            mimetype=row["mime_type"],
            headers={
                "Content-Disposition": f'{disposition}; filename="{row["filename"]}"',
                "Cache-Control": "private, max-age=3600",
            },
        )
    finally:
        db.close()


@bp.route("/<int:file_id>/thumbnail")
def thumbnail(file_id):
    db = current_app.get_db()
    try:
        row = db.fetchone(
            "SELECT thumbnail_path, mime_type FROM attachments WHERE id = ?",
            (file_id,),
        )
        if not row:
            return "Not found", 404

        if row["thumbnail_path"]:
            case_dir = _get_case_dir()
            thumb_disk = case_dir / row["thumbnail_path"]
            if thumb_disk.exists():
                return Response(
                    thumb_disk.read_bytes(),
                    mimetype="image/png",
                    headers={"Cache-Control": "private, max-age=3600"},
                )

        svg = _placeholder_svg(row["mime_type"])
        return Response(svg, mimetype="image/svg+xml")
    finally:
        db.close()


@bp.route("/<int:file_id>", methods=["DELETE"])
def delete(file_id):
    db = current_app.get_db()
    try:
        row = db.fetchone(
            "SELECT file_path, thumbnail_path FROM attachments WHERE id = ?",
            (file_id,),
        )
        if not row:
            return "Not found", 404

        case_dir = _get_case_dir()

        # Remove disk files
        if row["file_path"]:
            fp = case_dir / row["file_path"]
            if fp.exists():
                fp.unlink()
        if row["thumbnail_path"]:
            tp = case_dir / row["thumbnail_path"]
            if tp.exists():
                tp.unlink()

        with db.transaction() as cur:
            cur.execute("DELETE FROM attachments WHERE id = ?", (file_id,))
        return ""
    finally:
        db.close()


@bp.route("/<int:file_id>/verify", methods=["POST"])
def verify(file_id):
    """Verify file integrity by comparing current SHA-256 to stored hash."""
    db = current_app.get_db()
    try:
        row = db.fetchone(
            "SELECT file_path, sha256, filename FROM attachments WHERE id = ?",
            (file_id,),
        )
        if not row:
            return "Not found", 404

        case_dir = _get_case_dir()
        file_on_disk = case_dir / row["file_path"]

        if not file_on_disk.exists():
            status, message = "missing", "File missing from disk"
        else:
            current_hash = hashlib.sha256(file_on_disk.read_bytes()).hexdigest()
            if current_hash == row["sha256"]:
                status = "verified"
                message = f"Integrity intact. SHA-256: {current_hash}"
            else:
                status = "tampered"
                message = (f"HASH MISMATCH — file may be tampered. "
                           f"Expected: {row['sha256']} Got: {current_hash}")

        return (
            f'<div class="verify-result verify-{status}">'
            f'<strong>{row["filename"]}</strong>: {message}</div>'
        )
    finally:
        db.close()


@bp.route("/<int:file_id>/link", methods=["POST"])
def link(file_id):
    db = current_app.get_db()
    try:
        entity_type = request.form.get("entity_type")
        entity_id = request.form.get("entity_id")
        if not entity_type or not entity_id:
            return "entity_type and entity_id are required", 400

        with db.transaction() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO attachment_links "
                "(attachment_id, entity_type, entity_id) VALUES (?, ?, ?)",
                (file_id, entity_type, int(entity_id)),
            )

        return detail(file_id)
    finally:
        db.close()


@bp.route("/<int:file_id>/link/<int:link_id>", methods=["DELETE"])
def unlink(file_id, link_id):
    db = current_app.get_db()
    try:
        with db.transaction() as cur:
            cur.execute(
                "DELETE FROM attachment_links WHERE id = ?", (link_id,)
            )

        return detail(file_id)
    finally:
        db.close()


@bp.route("/<int:file_id>/analyze", methods=["POST"])
def analyze(file_id):
    db = current_app.get_db()
    try:
        row = db.fetchone(
            "SELECT file_path, mime_type, filename FROM attachments WHERE id = ?",
            (file_id,),
        )
        if not row:
            return "Not found", 404

        case_dir = _get_case_dir()
        disk_path = case_dir / row["file_path"]
        if not disk_path.exists():
            return "File missing from disk", 404

        file_bytes = disk_path.read_bytes()
        analysis = _run_ai_analysis(
            file_bytes, row["mime_type"], row["filename"]
        )
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        with db.transaction() as cur:
            cur.execute(
                "UPDATE attachments SET ai_analysis = ?, ai_analyzed_at = ? "
                "WHERE id = ?",
                (analysis, now, file_id),
            )

        return detail(file_id)
    finally:
        db.close()

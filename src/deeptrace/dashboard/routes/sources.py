"""Sources CRUD routes with URL scraping and Admiralty rating support."""

from urllib.parse import urlparse

import httpx
from flask import Blueprint, current_app, jsonify, render_template, request

from deeptrace.dashboard.routes.import_data import (
    _extract_dates,
    _fetch_page,
    _guess_reliability,
    _parse_generic_page,
)

bp = Blueprint("sources", __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_TYPE_MAP: dict[str, str] = {
    # Official / government / legal (primary sources)
    ".gov": "official",
    ".mil": "official",
    "un.org": "official",
    "who.int": "official",
    "interpol.int": "official",
    "europa.eu": "official",
    "courtlistener.com": "official",
    "law.cornell.edu": "official",
    "pacer.uscourts.gov": "official",
    "govinfo.gov": "official",
    # Wire services
    "reuters.com": "news",
    "apnews.com": "news",
    "afp.com": "news",
    # Broadcasters
    "bbc.com": "news",
    "bbc.co.uk": "news",
    "abcnews.go.com": "news",
    "abc.net.au": "news",
    "cbsnews.com": "news",
    "nbcnews.com": "news",
    "pbs.org": "news",
    "npr.org": "news",
    "cnn.com": "news",
    "foxnews.com": "news",
    "msnbc.com": "news",
    "c-span.org": "news",
    "cnbc.com": "news",
    # Newspapers
    "nytimes.com": "news",
    "washingtonpost.com": "news",
    "wsj.com": "news",
    "theguardian.com": "news",
    "latimes.com": "news",
    "usatoday.com": "news",
    "politico.com": "news",
    "thehill.com": "news",
    "usnews.com": "news",
    "newyorkpost.com": "news",
    "nypost.com": "news",
    "newsweek.com": "news",
    "forbes.com": "news",
    "people.com": "news",
    "chicagotribune.com": "news",
    "sfchronicle.com": "news",
    "sfgate.com": "news",
    "bostonglobe.com": "news",
    "dallasnews.com": "news",
    "miamiherald.com": "news",
    "seattletimes.com": "news",
    "washingtontimes.com": "news",
    # Digital-first / online news
    "huffpost.com": "news",
    "buzzfeed.com": "news",
    "buzzfeednews.com": "news",
    "vox.com": "news",
    "vice.com": "news",
    "axios.com": "news",
    "thedailybeast.com": "news",
    "salon.com": "news",
    "breitbart.com": "news",
    "dailywire.com": "news",
    "dailycaller.com": "news",
    "oann.com": "news",
    "newsmax.com": "news",
    "theblaze.com": "news",
    "theepochtimes.com": "news",
    "slate.com": "news",
    "theatlantic.com": "news",
    "newyorker.com": "news",
    "time.com": "news",
    "businessinsider.com": "news",
    "motherjones.com": "news",
    "thenation.com": "news",
    "nationalreview.com": "news",
    "reason.com": "news",
    "jacobin.com": "news",
    "dailydot.com": "news",
    "rollingstone.com": "news",
    "vanityfair.com": "news",
    # Business / financial
    "economist.com": "news",
    "ft.com": "news",
    "bloomberg.com": "news",
    # Tech news
    "wired.com": "news",
    "arstechnica.com": "news",
    "theverge.com": "news",
    # UK / international news
    "dailymail.co.uk": "news",
    "thesun.co.uk": "news",
    "independent.co.uk": "news",
    "telegraph.co.uk": "news",
    "sky.com": "news",
    "aljazeera.com": "news",
    "france24.com": "news",
    "spiegel.de": "news",
    # Canadian
    "cbc.ca": "news",
    "theglobeandmail.com": "news",
    "thestar.com": "news",
    # Australian
    "smh.com.au": "news",
    # Investigative
    "propublica.org": "news",
    "icij.org": "news",
    "theintercept.com": "news",
    "revealnews.org": "news",
    # Fact-checkers
    "snopes.com": "news",
    "factcheck.org": "news",
    "politifact.com": "news",
    # Academic / reference
    ".edu": "academic",
    "wikipedia.org": "academic",
    "archive.org": "academic",
    "scholar.google.com": "academic",
    # Social media
    "facebook.com": "social",
    "twitter.com": "social",
    "x.com": "social",
    "reddit.com": "social",
    "instagram.com": "social",
    "tiktok.com": "social",
    "youtube.com": "social",
    "threads.net": "social",
    "mastodon.social": "social",
    "bsky.app": "social",
    # Blogs / opinion
    "medium.com": "social",
    "substack.com": "social",
}


def _classify_source_type(url: str) -> str:
    """Guess source_type from the URL domain."""
    host = urlparse(url).hostname or ""
    for domain_fragment, src_type in _SOURCE_TYPE_MAP.items():
        if host.endswith(domain_fragment) or domain_fragment in host:
            return src_type
    return "news"  # Default for scraped URLs


def _admiralty_to_numeric(reliability: str, accuracy: str) -> float:
    """Convert Admiralty A-F / 1-6 to a 0-1 float score."""
    rel_map = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "E": 0.2, "F": 0.0}
    acc_map = {"1": 1.0, "2": 0.8, "3": 0.6, "4": 0.4, "5": 0.2, "6": 0.0}
    r = rel_map.get(reliability, 0.4)
    a = acc_map.get(accuracy, 0.4)
    return round((r + a) / 2, 2)


# ---------------------------------------------------------------------------
# URL Fetch route
# ---------------------------------------------------------------------------

@bp.route("/fetch-url", methods=["POST"])
def fetch_url():
    """Fetch a URL and return auto-filled field values as JSON.

    Accepts JSON: {"url": "..."} or {"url": "...", "html": "..."}.
    If *html* is provided, skip the HTTP fetch (paste fallback for 403s).
    """
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    pasted_html = (data.get("html") or "").strip()

    if not url and not pasted_html:
        return jsonify({"error": "A URL or pasted HTML is required."}), 400

    try:
        # Get HTML -- from paste or fetch
        if pasted_html:
            html = pasted_html
        else:
            html = _fetch_page(url)

        # Try trafilatura first for better extraction
        title, description, body_text = "", "", ""
        try:
            import trafilatura

            downloaded = trafilatura.bare_extraction(
                html, url=url, include_comments=False,
                include_tables=True, favor_recall=True,
            )
            if downloaded:
                title = downloaded.get("title") or ""
                description = downloaded.get("description") or ""
                body_text = downloaded.get("text") or ""
        except (ImportError, Exception):
            pass

        # Fall back to our custom parser if trafilatura didn't get enough
        if not body_text or len(body_text) < 50:
            parsed = _parse_generic_page(html, url)
            title = title or parsed.get("title", "")
            description = description or parsed.get("description", "")
            body_text = body_text or parsed.get("body_text", "")

        # Reliability rating
        reliability, accuracy = _guess_reliability(url) if url else ("F", "6")
        source_type = _classify_source_type(url) if url else "manual"
        score = _admiralty_to_numeric(reliability, accuracy)

        # Build summary for raw_text field
        raw_text_parts = []
        if title:
            raw_text_parts.append(title)
        if description and description != title:
            raw_text_parts.append(description)
        if body_text:
            raw_text_parts.append(body_text)
        raw_text = "\n\n".join(raw_text_parts)

        # Dates
        dates = _extract_dates(html)

        return jsonify({
            "status": "ok",
            "title": title,
            "description": description,
            "raw_text": raw_text[:10000],  # Cap at 10K chars
            "source_type": source_type,
            "source_reliability": reliability,
            "information_accuracy": accuracy,
            "reliability_score": score,
            "url": url,
            "dates": dates[:5],
            "notes": f"Auto-imported from {urlparse(url).hostname or 'pasted HTML'}",
        }), 200

    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 403:
            return jsonify({
                "error": (
                    "The site returned 403 Forbidden (it may block automated "
                    "requests). You can paste the page HTML below instead."
                ),
                "needs_paste": True,
            }), 200  # 200 so JS can show the paste UI
        return jsonify({"error": f"HTTP {code}: {e.response.reason_phrase}"}), 502
    except httpx.HTTPError as e:
        return jsonify({"error": f"Failed to fetch: {e}"}), 502
    except Exception as e:
        return jsonify({"error": f"Extraction failed: {e}"}), 500


# ---------------------------------------------------------------------------
# CRUD routes
# ---------------------------------------------------------------------------

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
                "INSERT INTO sources (raw_text, source_type, url, reliability_score, "
                "source_reliability, information_accuracy, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    request.form["raw_text"],
                    request.form.get("source_type", "manual"),
                    request.form.get("url") or None,
                    float(request.form.get("reliability_score", 0.5)),
                    request.form.get("source_reliability") or None,
                    request.form.get("information_accuracy") or None,
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
                "reliability_score=?, source_reliability=?, "
                "information_accuracy=?, notes=? WHERE id=?",
                (
                    request.form["raw_text"],
                    request.form.get("source_type", "manual"),
                    request.form.get("url") or None,
                    float(request.form.get("reliability_score", 0.5)),
                    request.form.get("source_reliability") or None,
                    request.form.get("information_accuracy") or None,
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

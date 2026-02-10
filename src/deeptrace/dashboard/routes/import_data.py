"""Data import routes — unified URL importer with site-specific parsers."""

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session

from deeptrace.db import (
    CaseDatabase,
    create_case,
    create_evidence_item,
    create_source,
    create_timeline_event,
    get_db_path,
)
from deeptrace.state import AppState, CASES_DIR

bp = Blueprint("import_data", __name__)

# ---------------------------------------------------------------------------
# Shared HTTP helpers
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_page(url: str) -> str:
    """Fetch a URL with browser-like headers. Returns HTML text."""
    response = httpx.get(
        url, timeout=30.0, follow_redirects=True, headers=_HEADERS,
    )
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# Site detection — maps domain fragments to specialized parsers
# ---------------------------------------------------------------------------

_KNOWN_SITES: dict[str, dict] = {
    "fbi.gov": {
        "name": "FBI",
        "parser": "_parse_fbi_page",
        "creator": "_create_case_from_fbi",
        "reliability": "A",
        "credibility": "1",
    },
    "namus.nij.ojp.gov": {
        "name": "NamUs",
        "parser": "_parse_namus_page",
        "creator": "_create_case_from_namus",
        "reliability": "A",
        "credibility": "1",
    },
    "missingkids.org": {
        "name": "NCMEC",
        "parser": "_parse_ncmec_page",
        "creator": "_create_case_from_ncmec",
        "reliability": "A",
        "credibility": "1",
    },
    "doenetwork.org": {
        "name": "Doe Network",
        "parser": "_parse_doe_page",
        "creator": "_create_case_from_doe",
        "reliability": "B",
        "credibility": "2",
    },
}

# Default reliability for well-known news / gov domains
_DOMAIN_RELIABILITY: dict[str, tuple[str, str]] = {
    ".gov": ("B", "2"),
    ".mil": ("B", "2"),
    "reuters.com": ("B", "2"),
    "apnews.com": ("B", "2"),
    "bbc.com": ("B", "2"),
    "bbc.co.uk": ("B", "2"),
    "nytimes.com": ("C", "3"),
    "washingtonpost.com": ("C", "3"),
    "cnn.com": ("C", "3"),
}


def _detect_site(url: str) -> dict | None:
    """Return the known-site config dict if *url* matches, else None."""
    host = urlparse(url).hostname or ""
    for domain_fragment, config in _KNOWN_SITES.items():
        if domain_fragment in host:
            return config
    return None


def _guess_reliability(url: str) -> tuple[str, str]:
    """Return (source_reliability, information_credibility) for a URL."""
    host = urlparse(url).hostname or ""
    for domain_fragment, (rel, cred) in _DOMAIN_RELIABILITY.items():
        if host.endswith(domain_fragment):
            return rel, cred
    return ("D", "5")  # Cannot be judged


# ---------------------------------------------------------------------------
# Generic page extractor (works on any URL)
# ---------------------------------------------------------------------------

def _strip_tags(html_fragment: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_fragment, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _extract_meta(html: str, property_name: str) -> str:
    """Extract content from <meta property="..." content="..."> or name=..."""
    # og: and twitter: style
    m = re.search(
        rf'<meta\s[^>]*(?:property|name)=["\']?{re.escape(property_name)}["\']?\s[^>]*content=["\']([^"\']+)',
        html, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    # content first, property second
    m = re.search(
        rf'<meta\s[^>]*content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']?{re.escape(property_name)}',
        html, re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _extract_body_text(html: str, max_chars: int = 5000) -> str:
    """Extract main body text from HTML, preferring <article> content."""
    # Try <article> first
    article = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    if article:
        text = _strip_tags(article.group(1))
        return text[:max_chars]

    # Try <main>
    main = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL | re.IGNORECASE)
    if main:
        text = _strip_tags(main.group(1))
        return text[:max_chars]

    # Fall back to all <p> tags
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if paragraphs:
        chunks = [_strip_tags(p) for p in paragraphs if len(_strip_tags(p)) > 30]
        text = "\n\n".join(chunks)
        return text[:max_chars]

    return ""


def _extract_dates(html: str) -> list[str]:
    """Find date strings in HTML content."""
    # ISO dates
    iso_dates = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', html)
    # Long form dates
    long_dates = re.findall(
        r'\b((?:January|February|March|April|May|June|July|August|September|'
        r'October|November|December)\s+\d{1,2},?\s+\d{4})\b',
        html, re.IGNORECASE,
    )
    # Deduplicate while preserving order
    seen = set()
    result = []
    for d in iso_dates + long_dates:
        if d not in seen:
            seen.add(d)
            result.append(d)
    return result[:5]


def _parse_generic_page(html: str, url: str) -> dict:
    """Extract structured data from any web page."""
    # Title: og:title → <title> → first <h1>
    title = (
        _extract_meta(html, "og:title")
        or _extract_meta(html, "twitter:title")
    )
    if not title:
        m = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
        title = _strip_tags(m.group(1)) if m else ""
    if not title:
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
        title = _strip_tags(m.group(1)) if m else "Untitled Page"

    # Description: og:description → meta description → first long <p>
    description = (
        _extract_meta(html, "og:description")
        or _extract_meta(html, "description")
        or _extract_meta(html, "twitter:description")
    )
    if not description:
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
        for p in paragraphs:
            text = _strip_tags(p)
            if len(text) > 50:
                description = text[:500]
                break

    # Site name
    site_name = _extract_meta(html, "og:site_name")
    if not site_name:
        site_name = urlparse(url).hostname or "Unknown"

    # Published date from meta
    pub_date = (
        _extract_meta(html, "article:published_time")
        or _extract_meta(html, "datePublished")
        or _extract_meta(html, "date")
    )

    # Body text
    body_text = _extract_body_text(html)

    # Dates from content
    dates = _extract_dates(html)
    if pub_date and pub_date not in dates:
        dates.insert(0, pub_date)

    # Reliability
    reliability, credibility = _guess_reliability(url)

    return {
        "title": title.strip(),
        "description": description or "No description available",
        "body_text": body_text,
        "url": url,
        "source_name": site_name,
        "case_type": "Web Source",
        "dates": dates[:5],
        "source_reliability": reliability,
        "information_credibility": credibility,
    }


# ---------------------------------------------------------------------------
# Unified routes
# ---------------------------------------------------------------------------

@bp.route("/")
def import_page():
    """Show the unified import page."""
    current_case = session.get("current_case")
    return render_template("import_data.html", current_case=current_case)


@bp.route("/url/preview", methods=["POST"])
def preview_url():
    """Fetch a URL, extract data, return a preview for user confirmation.

    Accepts JSON: {"url": "..."} or {"url": "...", "html": "..."}.
    If *html* is provided, skip the fetch (paste fallback).
    """
    data = request.get_json()
    url = (data.get("url") or "").strip()
    pasted_html = (data.get("html") or "").strip()

    if not url and not pasted_html:
        return jsonify({"error": "A URL or pasted HTML is required."}), 400

    try:
        # Get HTML — from paste or fetch
        if pasted_html:
            html = pasted_html
        else:
            html = _fetch_page(url)

        # Detect known site
        site_config = _detect_site(url) if url else None

        if site_config:
            parser_name = site_config["parser"]
            parser_fn = globals()[parser_name]
            extracted = parser_fn(html, url)
            # Augment with body text if the specialized parser didn't include it
            if "body_text" not in extracted:
                extracted["body_text"] = _extract_body_text(html)
            extracted["source_name"] = site_config["name"]
            extracted["source_reliability"] = site_config["reliability"]
            extracted["information_credibility"] = site_config["credibility"]
            extracted["known_site"] = True
        else:
            extracted = _parse_generic_page(html, url)
            extracted["known_site"] = False

        return jsonify({
            "status": "preview",
            "data": extracted,
        }), 200

    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 403:
            return jsonify({
                "error": (
                    f"The site returned 403 Forbidden (it may block automated "
                    f"requests from cloud servers). You can paste the page HTML "
                    f"instead using the fallback option below."
                ),
                "needs_paste": True,
            }), 200  # 200 so the JS can show the paste UI
        return jsonify({"error": f"HTTP {code}: {e.response.reason_phrase}"}), 502
    except httpx.HTTPError as e:
        return jsonify({"error": f"Failed to fetch page: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": f"Extraction failed: {str(e)}"}), 500


@bp.route("/url/confirm", methods=["POST"])
def confirm_import():
    """Create a case or add to existing case from previewed data.

    Expects JSON: {"action": "create_case"|"add_to_case", "data": {...}}
    """
    payload = request.get_json()
    action = payload.get("action", "create_case")
    data = payload.get("data", {})

    title = data.get("title", "Untitled")
    description = data.get("description", "")
    body_text = data.get("body_text", "")
    url = data.get("url", "")
    source_name = data.get("source_name", "Web")
    case_type = data.get("case_type", "Web Source")
    dates = data.get("dates", [])
    reliability = data.get("source_reliability", "D")
    credibility = data.get("information_credibility", "5")

    try:
        if action == "create_case":
            # Build a slug from the title
            slug_base = re.sub(r'[^a-zA-Z0-9]+', '-', title)
            slug_base = slug_base.strip('-')[:50]
            case_id = f"WEB-{slug_base}" if slug_base else f"WEB-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            create_case(
                case_id=case_id,
                title=title,
                summary=f"{case_type}. {description[:500]}",
            )

            source_id = create_source(
                case_id=case_id,
                source_type=source_name,
                description=f"{source_name}: {title}",
                url=url,
                source_reliability=reliability,
                information_credibility=credibility,
            )

            # Store body text as evidence
            content = body_text or description
            if content:
                create_evidence_item(
                    case_id=case_id,
                    item_type="Document",
                    description=f"Imported from {source_name}: {title[:100]}",
                    source_id=source_id,
                    content=content,
                )

            # Timeline events
            for date_str in dates[:5]:
                _add_timeline_event(case_id, date_str, source_name)

            return jsonify({
                "status": "success",
                "message": f"Created case: {title}",
                "case_id": case_id,
            }), 200

        elif action == "add_to_case":
            case_id = session.get("current_case")
            if not case_id:
                return jsonify({"error": "No case is currently selected."}), 400

            source_id = create_source(
                case_id=case_id,
                source_type=source_name,
                description=f"{source_name}: {title}",
                url=url,
                source_reliability=reliability,
                information_credibility=credibility,
            )

            content = body_text or description
            if content:
                create_evidence_item(
                    case_id=case_id,
                    item_type="Document",
                    description=f"Imported from {source_name}: {title[:100]}",
                    source_id=source_id,
                    content=content,
                )

            for date_str in dates[:5]:
                _add_timeline_event(case_id, date_str, source_name)

            return jsonify({
                "status": "success",
                "message": f"Added to case: {title}",
                "case_id": case_id,
            }), 200

        else:
            return jsonify({"error": f"Unknown action: {action}"}), 400

    except Exception as e:
        return jsonify({"error": f"Import failed: {str(e)}"}), 500


def _add_timeline_event(case_id: str, date_str: str, source_name: str) -> None:
    """Try to parse a date string and add a timeline event."""
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(date_str.split("T")[0] if "T" in date_str else date_str, fmt)
            create_timeline_event(
                case_id=case_id,
                event_date=parsed.strftime("%Y-%m-%d"),
                description=f"Date from {source_name}: {date_str}",
                event_type="Documented Date",
            )
            return
        except ValueError:
            continue


# ---------------------------------------------------------------------------
# Legacy routes — redirect to unified importer
# (kept for backward compatibility; the old individual routes still work)
# ---------------------------------------------------------------------------

@bp.route("/namus", methods=["POST"])
def import_namus():
    """Import from NamUs — delegates to unified preview+confirm."""
    return _legacy_import("namus")


@bp.route("/ncmec", methods=["POST"])
def import_ncmec():
    """Import from NCMEC."""
    return _legacy_import("ncmec")


@bp.route("/doe", methods=["POST"])
def import_doe():
    """Import from Doe Network."""
    return _legacy_import("doe")


@bp.route("/fbi", methods=["POST"])
def import_fbi():
    """Import from FBI."""
    return _legacy_import("fbi")


def _legacy_import(source: str) -> tuple:
    """Handle old-style direct-import POST by running preview+confirm."""
    data = request.get_json()
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        html = _fetch_page(url)
        site_config = _detect_site(url)

        if site_config:
            parser_fn = globals()[site_config["parser"]]
            extracted = parser_fn(html, url)
            creator_fn = globals()[site_config["creator"]]
            case_id = creator_fn(extracted)
        else:
            extracted = _parse_generic_page(html, url)
            # Use the confirm flow inline
            slug_base = re.sub(r'[^a-zA-Z0-9]+', '-', extracted["title"])
            slug_base = slug_base.strip('-')[:50]
            case_id = f"WEB-{slug_base}"
            create_case(case_id=case_id, title=extracted["title"],
                        summary=f"{extracted['case_type']}. {extracted['description'][:500]}")
            source_id = create_source(
                case_id=case_id, source_type=extracted["source_name"],
                description=f"{extracted['source_name']}: {extracted['title']}",
                url=url, source_reliability=extracted.get("source_reliability", "D"),
                information_credibility=extracted.get("information_credibility", "5"))
            if extracted.get("body_text"):
                create_evidence_item(case_id=case_id, item_type="Document",
                                     description=f"Imported: {extracted['title'][:100]}",
                                     source_id=source_id, content=extracted["body_text"])

        return jsonify({
            "status": "success",
            "message": f"Imported: {extracted['title']}",
            "case_id": case_id,
        }), 200

    except httpx.HTTPStatusError as e:
        return jsonify({"error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}"}), 500
    except httpx.HTTPError as e:
        return jsonify({"error": f"Failed to fetch page: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Import failed: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Specialized parsers (unchanged — called by site detection)
# ---------------------------------------------------------------------------

def _parse_fbi_page(html: str, url: str) -> dict:
    """Extract case information from FBI wanted page HTML."""
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    title = _strip_tags(title_match.group(1)) if title_match else "Unnamed Case"

    desc_match = re.search(
        r'<div[^>]*class="[^"]*wanted-person-description[^"]*"[^>]*>(.*?)</div>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not desc_match:
        desc_match = re.search(
            r'<p[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</p>',
            html, re.DOTALL | re.IGNORECASE,
        )
    description = _strip_tags(desc_match.group(1)) if desc_match else ""

    dates = _extract_dates(html)

    case_type = "Unknown"
    if "/wanted/kidnap/" in url:
        case_type = "Kidnapping/Missing Person"
    elif "/wanted/murders/" in url:
        case_type = "Homicide"
    elif "/wanted/fugitives/" in url:
        case_type = "Fugitive"
    elif "/wanted/seeking-info/" in url:
        case_type = "Information Sought"

    return {
        "title": title,
        "description": description or "No description available",
        "url": url,
        "case_type": case_type,
        "dates": dates[:3],
    }


def _create_case_from_fbi(case_data: dict) -> str:
    case_id_base = re.sub(r'[^a-zA-Z0-9]+', '-', case_data['title'].upper()).strip('-')[:40]
    case_id = f"FBI-{case_id_base}"
    create_case(case_id=case_id, title=case_data['title'],
                summary=f"{case_data['case_type']}. {case_data['description'][:500]}")
    source_id = create_source(
        case_id=case_id, source_type="FBI Database",
        description=f"FBI Most Wanted page: {case_data['title']}",
        url=case_data['url'], source_reliability="A", information_credibility="1")
    create_evidence_item(case_id=case_id, item_type="Document",
                         description=f"FBI listing for {case_data['title']}",
                         source_id=source_id, content=case_data['description'])
    for date_str in case_data.get('dates', []):
        _add_timeline_event(case_id, date_str, "FBI")
    return case_id


def _parse_namus_page(html: str, url: str) -> dict:
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    title = _strip_tags(title_match.group(1)) if title_match else "Unnamed Case"
    case_num_match = re.search(r'Case\s*#?\s*:?\s*(\w+)', html, re.IGNORECASE)
    case_number = case_num_match.group(1) if case_num_match else "UNKNOWN"
    description = ""
    for pattern in [r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>',
                    r'<p[^>]*class="[^"]*case-details[^"]*"[^>]*>(.*?)</p>']:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            description = _strip_tags(match.group(1))
            break
    dates = _extract_dates(html)
    case_type = "Missing Person" if "/missingpersons/" in url.lower() else "Unidentified Person"
    return {"title": title, "case_number": case_number,
            "description": description or "No description available",
            "url": url, "case_type": case_type, "dates": dates[:3]}


def _create_case_from_namus(case_data: dict) -> str:
    case_id = f"NAMUS-{case_data['case_number']}"
    create_case(case_id=case_id, title=case_data['title'],
                summary=f"{case_data['case_type']}. NamUs #{case_data['case_number']}. {case_data['description'][:500]}")
    source_id = create_source(
        case_id=case_id, source_type="NamUs Database",
        description=f"NamUs #{case_data['case_number']}: {case_data['title']}",
        url=case_data['url'], source_reliability="A", information_credibility="1")
    create_evidence_item(case_id=case_id, item_type="Document",
                         description=f"NamUs listing for {case_data['title']}",
                         source_id=source_id, content=case_data['description'])
    for d in case_data.get('dates', []):
        _add_timeline_event(case_id, d, "NamUs")
    return case_id


def _parse_ncmec_page(html: str, url: str) -> dict:
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    title = _strip_tags(title_match.group(1)) if title_match else "Unnamed Child"
    case_num_match = re.search(r'Case\s*Number:\s*(\w+)', html, re.IGNORECASE)
    case_number = case_num_match.group(1) if case_num_match else re.sub(r'[^A-Z0-9]', '', title.upper())[:20]
    description = ""
    for pattern in [r'<div[^>]*class="[^"]*poster-details[^"]*"[^>]*>(.*?)</div>',
                    r'<div[^>]*class="[^"]*child-info[^"]*"[^>]*>(.*?)</div>']:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            description = _strip_tags(match.group(1))
            break
    dates = _extract_dates(html)
    return {"title": title, "case_number": case_number,
            "description": description or "Missing child case from NCMEC",
            "url": url, "case_type": "Missing Child", "dates": dates[:3]}


def _create_case_from_ncmec(case_data: dict) -> str:
    case_id = f"NCMEC-{case_data['case_number']}"
    create_case(case_id=case_id, title=case_data['title'],
                summary=f"Missing Child (NCMEC). {case_data['description'][:500]}")
    source_id = create_source(
        case_id=case_id, source_type="NCMEC Database",
        description=f"NCMEC case: {case_data['title']}",
        url=case_data['url'], source_reliability="A", information_credibility="1")
    create_evidence_item(case_id=case_id, item_type="Document",
                         description=f"NCMEC poster for {case_data['title']}",
                         source_id=source_id, content=case_data['description'])
    for d in case_data.get('dates', []):
        _add_timeline_event(case_id, d, "NCMEC")
    return case_id


def _parse_doe_page(html: str, url: str) -> dict:
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    title = _strip_tags(title_match.group(1)) if title_match else "Unnamed Doe"
    case_num_match = re.search(r'\b(\d+U[FM][A-Z]{2})\b', html)
    case_number = case_num_match.group(1) if case_num_match else "UNKNOWN"
    description = ""
    for pattern in [r'<div[^>]*class="[^"]*case-details[^"]*"[^>]*>(.*?)</div>',
                    r'<p[^>]*>(.*?)</p>']:
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        if matches:
            chunks = [_strip_tags(m) for m in matches[:5] if len(_strip_tags(m)) > 10]
            description = ' '.join(chunks)
            break
    dates = _extract_dates(html)
    case_type = "Unidentified Person" if "unidentified" in url.lower() else "Missing Person"
    return {"title": title, "case_number": case_number,
            "description": description or "Case from The Doe Network",
            "url": url, "case_type": case_type, "dates": dates[:3]}


def _create_case_from_doe(case_data: dict) -> str:
    case_id = f"DOE-{case_data['case_number']}"
    create_case(case_id=case_id, title=case_data['title'],
                summary=f"{case_data['case_type']} (Doe Network). {case_data['description'][:500]}")
    source_id = create_source(
        case_id=case_id, source_type="Doe Network",
        description=f"Doe Network {case_data['case_number']}: {case_data['title']}",
        url=case_data['url'], source_reliability="B", information_credibility="2")
    create_evidence_item(case_id=case_id, item_type="Document",
                         description=f"Doe Network listing for {case_data['title']}",
                         source_id=source_id, content=case_data['description'])
    for d in case_data.get('dates', []):
        _add_timeline_event(case_id, d, "Doe Network")
    return case_id


# ---------------------------------------------------------------------------
# File-based import routes (unchanged)
# ---------------------------------------------------------------------------

@bp.route("/csv", methods=["POST"])
def import_csv():
    """Batch import from CSV file."""
    if "file" not in request.files:
        return "No file provided", 400
    file = request.files["file"]
    if file.filename == "":
        return "No file selected", 400
    if not file.filename.endswith(".csv"):
        return "File must be a CSV", 400
    return {"status": "success", "message": f"CSV file '{file.filename}' would be imported here",
            "note": "CSV parser pending"}, 200


@bp.route("/json", methods=["POST"])
def import_json():
    """Batch import from JSON file."""
    if "file" not in request.files:
        return "No file provided", 400
    file = request.files["file"]
    if file.filename == "":
        return "No file selected", 400
    if not file.filename.endswith(".json"):
        return "File must be JSON", 400
    try:
        data = json.load(file.stream)
        return {"status": "success", "message": f"JSON file '{file.filename}' would be imported",
                "records": len(data) if isinstance(data, list) else 1, "note": "JSON importer pending"}, 200
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {str(e)}", 400

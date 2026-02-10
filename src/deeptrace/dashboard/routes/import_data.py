"""Data import routes for external sources (FBI, NamUs, etc.)."""

import json
import re
from datetime import datetime
from pathlib import Path

import httpx
from flask import Blueprint, current_app, jsonify, redirect, render_template, request

from deeptrace.db import (
    create_case,
    create_evidence_item,
    create_source,
    create_timeline_event,
    get_db_path,
)
from deeptrace.state import AppState

bp = Blueprint("import_data", __name__)


@bp.route("/")
def import_page():
    """Show data import options."""
    return render_template("import_data.html")


@bp.route("/namus", methods=["POST"])
def import_namus():
    """Import case from NamUs database by scraping the URL."""
    data = request.get_json()
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    if "namus" not in url.lower():
        return jsonify({"error": "URL must be from NamUs"}), 400

    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        html = response.text

        case_data = _parse_namus_page(html, url)
        case_id = _create_case_from_namus(case_data)

        return jsonify({
            "status": "success",
            "message": f"Imported: {case_data['title']}",
            "case_id": case_id
        }), 200

    except httpx.HTTPError as e:
        return jsonify({"error": f"Failed to fetch NamUs page: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Import failed: {str(e)}"}), 500


@bp.route("/ncmec", methods=["POST"])
def import_ncmec():
    """Import case from NCMEC (National Center for Missing & Exploited Children)."""
    data = request.get_json()
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    if "missingkids.org" not in url.lower():
        return jsonify({"error": "URL must be from missingkids.org"}), 400

    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        html = response.text

        case_data = _parse_ncmec_page(html, url)
        case_id = _create_case_from_ncmec(case_data)

        return jsonify({
            "status": "success",
            "message": f"Imported: {case_data['title']}",
            "case_id": case_id
        }), 200

    except httpx.HTTPError as e:
        return jsonify({"error": f"Failed to fetch NCMEC page: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Import failed: {str(e)}"}), 500


@bp.route("/doe", methods=["POST"])
def import_doe():
    """Import case from The Doe Network."""
    data = request.get_json()
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    if "doenetwork.org" not in url.lower():
        return jsonify({"error": "URL must be from doenetwork.org"}), 400

    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        html = response.text

        case_data = _parse_doe_page(html, url)
        case_id = _create_case_from_doe(case_data)

        return jsonify({
            "status": "success",
            "message": f"Imported: {case_data['title']}",
            "case_id": case_id
        }), 200

    except httpx.HTTPError as e:
        return jsonify({"error": f"Failed to fetch Doe Network page: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Import failed: {str(e)}"}), 500


@bp.route("/fbi", methods=["POST"])
def import_fbi():
    """Import case from FBI Most Wanted / ViCAP by scraping the URL."""
    data = request.get_json()
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    if "fbi.gov" not in url:
        return jsonify({"error": "URL must be from fbi.gov"}), 400

    try:
        # Fetch the FBI page
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        html = response.text

        # Extract case details
        case_data = _parse_fbi_page(html, url)

        # Create case in DeepTrace
        case_id = _create_case_from_fbi(case_data)

        return jsonify({
            "status": "success",
            "message": f"Imported: {case_data['title']}",
            "case_id": case_id
        }), 200

    except httpx.HTTPError as e:
        return jsonify({"error": f"Failed to fetch FBI page: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Import failed: {str(e)}"}), 500


def _parse_fbi_page(html: str, url: str) -> dict:
    """Extract case information from FBI wanted page HTML."""
    # Basic text extraction (no BeautifulSoup to keep deps minimal)

    # Extract title
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else "Unnamed Case"

    # Extract description/details
    desc_match = re.search(r'<div[^>]*class="[^"]*wanted-person-description[^"]*"[^>]*>(.*?)</div>',
                           html, re.DOTALL | re.IGNORECASE)
    if not desc_match:
        # Try alternative patterns
        desc_match = re.search(r'<p[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</p>',
                              html, re.DOTALL | re.IGNORECASE)

    description = ""
    if desc_match:
        description = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
        description = re.sub(r'\s+', ' ', description)  # Normalize whitespace

    # Extract dates mentioned
    date_pattern = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'
    dates = re.findall(date_pattern, html, re.IGNORECASE)

    # Determine case type from URL
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
        "dates": dates[:3]  # Limit to first 3 dates mentioned
    }


def _create_case_from_fbi(case_data: dict) -> str:
    """Create a new DeepTrace case from FBI data."""
    # Generate case ID from title
    case_id_base = re.sub(r'[^a-zA-Z0-9]+', '-', case_data['title'].upper())
    case_id_base = case_id_base.strip('-')[:40]  # Limit length
    case_id = f"FBI-{case_id_base}"

    # Ensure cases directory exists
    cases_dir = Path.home() / "deeptrace" / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    # Create the case
    db_path = get_db_path(case_id)
    create_case(
        case_id=case_id,
        title=case_data['title'],
        summary=f"{case_data['case_type']}. {case_data['description'][:500]}"
    )

    # Add FBI page as a source
    source_id = create_source(
        case_id=case_id,
        source_type="FBI Database",
        description=f"FBI Most Wanted page: {case_data['title']}",
        url=case_data['url'],
        source_reliability="A",  # FBI is highly reliable
        information_credibility="1"  # Confirmed information
    )

    # Add initial evidence item (the FBI listing itself)
    create_evidence_item(
        case_id=case_id,
        item_type="Document",
        description=f"FBI Most Wanted listing for {case_data['title']}",
        source_id=source_id,
        content=case_data['description']
    )

    # Add timeline events for any dates found
    for i, date_str in enumerate(case_data.get('dates', [])):
        try:
            event_date = datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
            create_timeline_event(
                case_id=case_id,
                event_date=event_date,
                description=f"Date mentioned in FBI listing: {date_str}",
                event_type="Documented Date"
            )
        except ValueError:
            pass  # Skip if date parsing fails

    return case_id


def _parse_namus_page(html: str, url: str) -> dict:
    """Extract case information from NamUs page HTML."""
    # Extract name/title
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else "Unnamed Case"

    # Extract case number
    case_num_match = re.search(r'Case\s*#?\s*:?\s*(\w+)', html, re.IGNORECASE)
    case_number = case_num_match.group(1) if case_num_match else "UNKNOWN"

    # Extract description
    desc_patterns = [
        r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>',
        r'<p[^>]*class="[^"]*case-details[^"]*"[^>]*>(.*?)</p>'
    ]
    description = ""
    for pattern in desc_patterns:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            description = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            description = re.sub(r'\s+', ' ', description)
            break

    # Extract dates
    date_pattern = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'
    dates = re.findall(date_pattern, html, re.IGNORECASE)

    case_type = "Missing Person" if "/missingpersons/" in url.lower() else "Unidentified Person"

    return {
        "title": title,
        "case_number": case_number,
        "description": description or "No description available",
        "url": url,
        "case_type": case_type,
        "dates": dates[:3]
    }


def _create_case_from_namus(case_data: dict) -> str:
    """Create a new DeepTrace case from NamUs data."""
    case_id = f"NAMUS-{case_data['case_number']}"

    cases_dir = Path.home() / "deeptrace" / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    create_case(
        case_id=case_id,
        title=case_data['title'],
        summary=f"{case_data['case_type']}. NamUs #{case_data['case_number']}. {case_data['description'][:500]}"
    )

    source_id = create_source(
        case_id=case_id,
        source_type="NamUs Database",
        description=f"NamUs case #{case_data['case_number']}: {case_data['title']}",
        url=case_data['url'],
        source_reliability="A",
        information_credibility="1"
    )

    create_evidence_item(
        case_id=case_id,
        item_type="Document",
        description=f"NamUs listing for {case_data['title']}",
        source_id=source_id,
        content=case_data['description']
    )

    for date_str in case_data.get('dates', []):
        try:
            event_date = datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
            create_timeline_event(
                case_id=case_id,
                event_date=event_date,
                description=f"Date from NamUs: {date_str}",
                event_type="Documented Date"
            )
        except ValueError:
            pass

    return case_id


def _parse_ncmec_page(html: str, url: str) -> dict:
    """Extract case information from NCMEC page HTML."""
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else "Unnamed Child"

    # Extract case number if available
    case_num_match = re.search(r'Case\s*Number:\s*(\w+)', html, re.IGNORECASE)
    case_number = case_num_match.group(1) if case_num_match else re.sub(r'[^A-Z0-9]', '', title.upper())[:20]

    # Look for child details
    desc_patterns = [
        r'<div[^>]*class="[^"]*poster-details[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*child-info[^"]*"[^>]*>(.*?)</div>'
    ]
    description = ""
    for pattern in desc_patterns:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            description = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            description = re.sub(r'\s+', ' ', description)
            break

    date_pattern = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'
    dates = re.findall(date_pattern, html, re.IGNORECASE)

    return {
        "title": title,
        "case_number": case_number,
        "description": description or "Missing child case from NCMEC",
        "url": url,
        "case_type": "Missing Child",
        "dates": dates[:3]
    }


def _create_case_from_ncmec(case_data: dict) -> str:
    """Create a new DeepTrace case from NCMEC data."""
    case_id = f"NCMEC-{case_data['case_number']}"

    cases_dir = Path.home() / "deeptrace" / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    create_case(
        case_id=case_id,
        title=case_data['title'],
        summary=f"Missing Child (NCMEC). {case_data['description'][:500]}"
    )

    source_id = create_source(
        case_id=case_id,
        source_type="NCMEC Database",
        description=f"NCMEC case: {case_data['title']}",
        url=case_data['url'],
        source_reliability="A",
        information_credibility="1"
    )

    create_evidence_item(
        case_id=case_id,
        item_type="Document",
        description=f"NCMEC poster for {case_data['title']}",
        source_id=source_id,
        content=case_data['description']
    )

    for date_str in case_data.get('dates', []):
        try:
            event_date = datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
            create_timeline_event(
                case_id=case_id,
                event_date=event_date,
                description=f"Date from NCMEC: {date_str}",
                event_type="Documented Date"
            )
        except ValueError:
            pass

    return case_id


def _parse_doe_page(html: str, url: str) -> dict:
    """Extract case information from Doe Network page HTML."""
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else "Unnamed Doe"

    # Doe Network uses case codes like "123UFCA"
    case_num_match = re.search(r'\b(\d+U[FM][A-Z]{2})\b', html)
    case_number = case_num_match.group(1) if case_num_match else "UNKNOWN"

    # Extract vital stats and details
    desc_patterns = [
        r'<div[^>]*class="[^"]*case-details[^"]*"[^>]*>(.*?)</div>',
        r'<p[^>]*>(.*?)</p>'
    ]
    description = ""
    for pattern in desc_patterns:
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        if matches:
            desc_parts = [re.sub(r'<[^>]+>', '', m).strip() for m in matches[:5]]
            description = ' '.join(desc_parts)
            description = re.sub(r'\s+', ' ', description)
            break

    date_pattern = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'
    dates = re.findall(date_pattern, html, re.IGNORECASE)

    case_type = "Unidentified Person" if "unidentified" in url.lower() else "Missing Person"

    return {
        "title": title,
        "case_number": case_number,
        "description": description or "Case from The Doe Network",
        "url": url,
        "case_type": case_type,
        "dates": dates[:3]
    }


def _create_case_from_doe(case_data: dict) -> str:
    """Create a new DeepTrace case from Doe Network data."""
    case_id = f"DOE-{case_data['case_number']}"

    cases_dir = Path.home() / "deeptrace" / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    create_case(
        case_id=case_id,
        title=case_data['title'],
        summary=f"{case_data['case_type']} (Doe Network). {case_data['description'][:500]}"
    )

    source_id = create_source(
        case_id=case_id,
        source_type="Doe Network",
        description=f"Doe Network case {case_data['case_number']}: {case_data['title']}",
        url=case_data['url'],
        source_reliability="B",  # Volunteer org, generally reliable but not official
        information_credibility="2"  # Probably true
    )

    create_evidence_item(
        case_id=case_id,
        item_type="Document",
        description=f"Doe Network listing for {case_data['title']}",
        source_id=source_id,
        content=case_data['description']
    )

    for date_str in case_data.get('dates', []):
        try:
            event_date = datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
            create_timeline_event(
                case_id=case_id,
                event_date=event_date,
                description=f"Date from Doe Network: {date_str}",
                event_type="Documented Date"
            )
        except ValueError:
            pass

    return case_id


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

    # TODO: Implement CSV parsing and batch import
    return {
        "status": "success",
        "message": f"CSV file '{file.filename}' would be imported here",
        "note": "CSV parser pending"
    }, 200


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

        # TODO: Validate and import JSON data
        return {
            "status": "success",
            "message": f"JSON file '{file.filename}' would be imported",
            "records": len(data) if isinstance(data, list) else 1,
            "note": "JSON importer pending"
        }, 200

    except json.JSONDecodeError as e:
        return f"Invalid JSON: {str(e)}", 400

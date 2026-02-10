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
from deeptrace.state import get_current_case

bp = Blueprint("import_data", __name__)


@bp.route("/")
def import_page():
    """Show data import options."""
    return render_template("import_data.html")


@bp.route("/namus", methods=["POST"])
def import_namus():
    """Import case from NamUs database."""
    case_number = request.form.get("case_number", "").strip()

    if not case_number:
        return "Case number is required", 400

    # TODO: Implement NamUs API integration
    # For now, create a placeholder case
    return {
        "status": "success",
        "message": f"NamUs case {case_number} would be imported here",
        "note": "API integration pending"
    }, 200


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

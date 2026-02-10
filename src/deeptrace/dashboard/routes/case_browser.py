"""Case Browser - Browse and import cases from external databases."""

import json
import requests
from flask import Blueprint, render_template, request, current_app, jsonify
from datetime import datetime, UTC

from deeptrace.namus_client import NamUsClient

bp = Blueprint("case_browser", __name__)

# FBI Most Wanted API
FBI_WANTED_API = "https://api.fbi.gov/@wanted"

# ---------------------------------------------------------------------------
# Case Browser Index
# ---------------------------------------------------------------------------

@bp.route("/")
def index():
    """Show the case browser with grid of available cases."""
    return render_template("case_browser.html")


@bp.route("/api/fbi-wanted")
def fbi_wanted():
    """Fetch FBI Most Wanted cases."""
    try:
        # Fetch from FBI API
        response = requests.get(FBI_WANTED_API, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Transform to our format
        cases = []
        for item in data.get("items", [])[:50]:  # Limit to 50 for performance
            cases.append({
                "id": item.get("uid"),
                "title": item.get("title", "Unknown"),
                "description": item.get("description", "")[:300],
                "source": "FBI Most Wanted",
                "source_url": item.get("url", ""),
                "images": item.get("images", []),
                "subjects": item.get("subjects", []),
                "warning_message": item.get("warning_message", ""),
                "reward_text": item.get("reward_text", ""),
                "caution": item.get("caution", ""),
                "details": item.get("details", ""),
                "field_offices": item.get("field_offices", []),
                "publication": item.get("publication", ""),
            })

        return jsonify({"status": "ok", "cases": cases, "total": len(cases)})

    except requests.exceptions.Timeout:
        return jsonify({"status": "error", "error": "FBI API timeout"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.route("/api/namus-states")
def namus_states():
    """Fetch list of US states from NamUs."""
    try:
        client = NamUsClient()
        states = client.get_states()
        client.close()
        return jsonify({"status": "ok", "states": states})
    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.route("/api/namus-search", methods=["POST"])
def namus_search():
    """Search NamUs for cases."""
    data = request.get_json()
    case_type = data.get("case_type", "missing")  # missing, unidentified, unclaimed
    state = data.get("state")  # Optional state filter
    limit = data.get("limit", 20)  # Small default for testing

    try:
        client = NamUsClient()
        results = client.search_cases(case_type, state=state, limit=limit)

        # Fetch full details for first few cases (for display)
        cases = []
        for item in results.get("results", [])[:limit]:
            case_id = item.get("namus2Number")
            if case_id:
                try:
                    full_case = client.get_case(case_type, case_id)
                    # Transform to our format
                    if case_type == "missing":
                        transformed = client.transform_missing_person(full_case)
                    else:
                        transformed = client.transform_unidentified_person(full_case)
                    cases.append(transformed)
                except Exception as e:
                    # Skip cases that fail to fetch
                    print(f"Failed to fetch NamUs case {case_id}: {e}")
                    continue

        client.close()
        return jsonify({
            "status": "ok",
            "cases": cases,
            "total": results.get("count", 0),
            "returned": len(cases)
        })

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.route("/api/import-case", methods=["POST"])
def import_case():
    """Import a case from external source into current investigation."""
    db = current_app.get_db()
    data = request.get_json()

    if not data or not data.get("case_id"):
        return jsonify({"status": "error", "error": "case_id required"}), 400

    source_type = data.get("source", "fbi")
    case_id = data.get("case_id")

    try:
        if source_type == "namus":
            # Import from NamUs
            case_type = data.get("case_type", "missing")  # missing or unidentified
            namus_id = data.get("namus_id")

            if not namus_id:
                return jsonify({"status": "error", "error": "namus_id required"}), 400

            client = NamUsClient()
            namus_data = client.get_case(case_type, namus_id)

            # Transform to DeepTrace format
            if case_type == "missing":
                transformed = client.transform_missing_person(namus_data)
            else:
                transformed = client.transform_unidentified_person(namus_data)

            client.close()

            now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

            with db.transaction() as cur:
                # Create source
                cur.execute(
                    "INSERT INTO sources (url, source_type, raw_text, notes, "
                    "source_reliability, information_accuracy, reliability_score, ingested_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        transformed["namus_url"],
                        f"NamUs {transformed['case_type']}",
                        json.dumps(namus_data, indent=2),
                        f"Imported from NamUs: {transformed['title']}",
                        "A",  # Official government database
                        "1",  # Confirmed
                        1.0,  # Max reliability
                        now
                    )
                )
                source_id = cur.lastrowid

                # Create entity
                if case_type == "missing":
                    entity_name = transformed["subject_name"]
                    entity_desc = transformed.get("physical_description", "")
                else:
                    entity_name = f"Unidentified {transformed['sex']} - {transformed['case_id']}"
                    entity_desc = f"{transformed['sex']}, estimated age {transformed['estimated_age']}"

                cur.execute(
                    "INSERT INTO entities (name, entity_type, description, source_id) "
                    "VALUES (?, ?, ?, ?)",
                    (entity_name, "person", entity_desc, source_id)
                )
                entity_id = cur.lastrowid

                # Create timeline event
                event_date = transformed.get("last_seen_date") or transformed.get("date_found")
                if event_date:
                    event_desc = (
                        f"Last seen at {transformed['last_seen_location']}"
                        if case_type == "missing"
                        else f"Remains found at {transformed['location_found']}"
                    )
                    cur.execute(
                        "INSERT INTO events (timestamp_start, description, source_id, layer) "
                        "VALUES (?, ?, ?, ?)",
                        (event_date, event_desc, source_id, "general")
                    )

            return jsonify({
                "status": "ok",
                "source_id": source_id,
                "entity_id": entity_id,
                "message": f"Imported: {transformed['title']}"
            })

        elif source_type == "fbi":
            # Fetch full case details from FBI
            response = requests.get(f"{FBI_WANTED_API}/{case_id}", timeout=10)
            response.raise_for_status()
            case_data = response.json()

            # Create source entry
            now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

            with db.transaction() as cur:
                # Insert as source
                cur.execute(
                    "INSERT INTO sources (url, source_type, raw_text, notes, "
                    "source_reliability, information_accuracy, reliability_score, ingested_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        case_data.get("url", ""),
                        "official",  # FBI is official source
                        json.dumps(case_data, indent=2),
                        f"Imported from FBI Most Wanted: {case_data.get('title', 'Unknown')}",
                        "A",  # Completely reliable
                        "1",  # Confirmed
                        1.0,  # Max reliability
                        now
                    )
                )
                source_id = cur.lastrowid

                # Extract entities (subjects)
                entity_ids = []
                for subject in case_data.get("subjects", [])[:10]:
                    cur.execute(
                        "INSERT INTO entities (name, entity_type, description, source_id) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            subject,
                            "person",
                            f"FBI Most Wanted subject from case: {case_data.get('title', '')}",
                            source_id
                        )
                    )
                    entity_ids.append(cur.lastrowid)

                # Create suspect pool if not exists
                if case_data.get("subjects"):
                    cur.execute(
                        "INSERT INTO suspect_pools (category, description, basis) "
                        "VALUES (?, ?, ?)",
                        (
                            f"FBI: {case_data.get('title', 'Unknown')[:50]}",
                            case_data.get("warning_message", case_data.get("description", ""))[:500],
                            "FBI Most Wanted listing"
                        )
                    )
                    suspect_id = cur.lastrowid

                    # Link entities to suspect pool
                    for ent_id in entity_ids:
                        cur.execute(
                            "INSERT INTO suspect_pool_members (pool_id, entity_id) "
                            "VALUES (?, ?)",
                            (suspect_id, ent_id)
                        )

            return jsonify({
                "status": "ok",
                "source_id": source_id,
                "entities_created": len(entity_ids),
                "message": f"Imported: {case_data.get('title', 'Unknown')}"
            })

        else:
            return jsonify({"status": "error", "error": "Unknown source type"}), 400

    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "error": f"Failed to fetch case: {e}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "error": f"Import failed: {e}"}), 500
    finally:
        db.close()

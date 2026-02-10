"""NamUs API client for DeepTrace.

This module provides a clean interface to the National Missing and Unidentified
Persons System (NamUs) API for searching and retrieving missing person cases.
"""

import requests
from typing import List, Dict, Optional, Literal

# API Configuration
NAMUS_API = "https://www.namus.gov/api"
USER_AGENT = "DeepTrace Cold Case Investigation Platform"
DEFAULT_TIMEOUT = 30
REQUEST_BATCH_SIZE = 50  # Conservative batch size for API calls

CaseType = Literal["missing", "unidentified", "unclaimed"]

# Case type configurations
CASE_TYPES = {
    "missing": {
        "api_type": "MissingPersons",
        "state_field": "stateOfLastContact",
        "display_name": "Missing Person",
    },
    "unidentified": {
        "api_type": "UnidentifiedPersons",
        "state_field": "stateOfRecovery",
        "display_name": "Unidentified Person",
    },
    "unclaimed": {
        "api_type": "UnclaimedPersons",
        "state_field": "stateFound",
        "display_name": "Unclaimed Person",
    },
}


class NamUsClient:
    """Client for interacting with the NamUs API."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """Initialize NamUs client.

        Args:
            timeout: Request timeout in seconds (default: 30)
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def get_states(self) -> List[Dict]:
        """Fetch list of US states from NamUs.

        Returns:
            List of state dictionaries with 'name' and 'displayName' fields
        """
        url = f"{NAMUS_API}/CaseSets/NamUs/States"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def search_cases(
        self,
        case_type: CaseType,
        state: Optional[str] = None,
        limit: int = 50,
    ) -> Dict:
        """Search NamUs for cases.

        Args:
            case_type: One of "missing", "unidentified", "unclaimed"
            state: State name (e.g., "California") or None for all states
            limit: Maximum results to return (max 10000)

        Returns:
            Dictionary with 'count' (total) and 'results' (list of case summaries)

        Raises:
            ValueError: If case_type is invalid
            requests.HTTPError: If API request fails
        """
        if case_type not in CASE_TYPES:
            raise ValueError(f"Invalid case_type: {case_type}")

        type_config = CASE_TYPES[case_type]
        url = f"{NAMUS_API}/CaseSets/NamUs/{type_config['api_type']}/Search"

        # Build search payload
        payload = {"take": min(limit, 10000), "projections": ["namus2Number"]}

        # Add state filter if provided
        if state:
            payload["predicates"] = [
                {
                    "field": type_config["state_field"],
                    "operator": "IsIn",
                    "values": [state],
                }
            ]

        response = self.session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_case(self, case_type: CaseType, case_id: int) -> Dict:
        """Fetch full case details from NamUs.

        Args:
            case_type: One of "missing", "unidentified", "unclaimed"
            case_id: NamUs case number (e.g., 3250 for MP3250)

        Returns:
            Full case data dictionary

        Raises:
            ValueError: If case_type is invalid
            requests.HTTPError: If API request fails
        """
        if case_type not in CASE_TYPES:
            raise ValueError(f"Invalid case_type: {case_type}")

        type_config = CASE_TYPES[case_type]
        url = f"{NAMUS_API}/CaseSets/NamUs/{type_config['api_type']}/Cases/{case_id}"

        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_case_thumbnail_url(self, case_type: CaseType, case_id: int) -> str:
        """Get URL for case thumbnail image.

        Args:
            case_type: One of "missing", "unidentified", "unclaimed"
            case_id: NamUs case number

        Returns:
            Full URL to thumbnail image
        """
        if case_type not in CASE_TYPES:
            raise ValueError(f"Invalid case_type: {case_type}")

        type_config = CASE_TYPES[case_type]
        return f"{NAMUS_API}/CaseSets/NamUs/{type_config['api_type']}/Cases/{case_id}/Images/Default/Thumbnail"

    def transform_missing_person(self, namus_data: Dict) -> Dict:
        """Transform NamUs missing person data to DeepTrace format.

        Args:
            namus_data: Raw NamUs API response for a missing person case

        Returns:
            Transformed dictionary ready for DeepTrace import
        """
        subject = namus_data.get("subjectIdentification", {})
        description = namus_data.get("subjectDescription", {})
        circumstances = namus_data.get("circumstances", {})
        sighting = namus_data.get("sighting", {})

        # Build full name
        name_parts = [
            subject.get("firstName", ""),
            subject.get("middleName", ""),
            subject.get("lastName", ""),
        ]
        name = " ".join(p for p in name_parts if p).strip() or "Unknown Subject"

        # Build physical description
        physical = []
        if description.get("sex"):
            physical.append(f"Sex: {description['sex']['name']}")
        if description.get("heightFrom"):
            physical.append(f"Height: {description['heightFrom']} inches")
        if description.get("weightFrom"):
            weight_to = description.get("weightTo", "?")
            physical.append(f"Weight: {description['weightFrom']}-{weight_to} lbs")
        if description.get("ethnicities"):
            ethnicities = ", ".join(e["name"] for e in description["ethnicities"])
            physical.append(f"Ethnicity: {ethnicities}")

        # Build location
        location = "Unknown"
        if sighting and sighting.get("address"):
            addr = sighting["address"]
            city = addr.get("city", "Unknown")
            state = addr.get("state", {}).get("displayName", "Unknown")
            location = f"{city}, {state}"

        # Get investigating agencies
        agencies = namus_data.get("investigatingAgencies", [])
        agency_info = []
        for agency in agencies[:3]:  # Limit to top 3
            case_num = agency.get("caseNumber", "N/A")
            agency_info.append(f"{agency['name']} (Case #{case_num})")

        return {
            "case_id": namus_data["idFormatted"],  # e.g., "MP3250"
            "namus_id": namus_data["id"],
            "title": f"{name} - NamUs {namus_data['idFormatted']}",
            "case_type": "Missing Person",
            "subject_name": name,
            "physical_description": "; ".join(physical),
            "last_seen_date": sighting.get("date") if sighting else None,
            "last_seen_location": location,
            "circumstances": circumstances.get("circumstancesOfDisappearance", ""),
            "investigating_agencies": "; ".join(agency_info),
            "namus_url": f"https://www.namus.gov/MissingPersons/Case#/{namus_data['id']}",
            "thumbnail_url": self.get_case_thumbnail_url("missing", namus_data["id"]),
            "raw_data": namus_data,
        }

    def transform_unidentified_person(self, namus_data: Dict) -> Dict:
        """Transform NamUs unidentified person data to DeepTrace format.

        Args:
            namus_data: Raw NamUs API response for an unidentified person case

        Returns:
            Transformed dictionary ready for DeepTrace import
        """
        description = namus_data.get("subjectDescription", {})
        circumstances = namus_data.get("circumstances", {})

        # Build descriptive title
        sex = description.get("sex", {}).get("name", "Unknown")
        age_from = description.get("estimatedAgeFrom", "Unknown")
        age_to = description.get("estimatedAgeTo", "Unknown")
        age_str = f"{age_from}-{age_to}" if age_from != "Unknown" else "Unknown age"

        title = f"Unidentified {sex} ({age_str}) - NamUs {namus_data['idFormatted']}"

        # Build recovery location
        location = "Unknown"
        if circumstances and circumstances.get("address"):
            addr = circumstances["address"]
            city = addr.get("city", "Unknown")
            state = addr.get("state", {}).get("displayName", "Unknown")
            location = f"{city}, {state}"

        return {
            "case_id": namus_data["idFormatted"],  # e.g., "UP906"
            "namus_id": namus_data["id"],
            "title": title,
            "case_type": "Unidentified Person",
            "sex": sex,
            "estimated_age": age_str,
            "date_found": circumstances.get("dateFound"),
            "location_found": location,
            "condition": circumstances.get("circumstancesOfRecovery", ""),
            "namus_url": f"https://www.namus.gov/UnidentifiedPersons/Case#/{namus_data['id']}",
            "thumbnail_url": self.get_case_thumbnail_url(
                "unidentified", namus_data["id"]
            ),
            "raw_data": namus_data,
        }

    def close(self):
        """Close the HTTP session."""
        self.session.close()

"""Tests for NLP entity extraction."""

import pytest

try:
    import spacy
    HAS_SPACY = True
except (ImportError, Exception):
    HAS_SPACY = False

pytestmark = pytest.mark.skipif(not HAS_SPACY, reason="spaCy not installed")


from deeptrace.nlp import extract_entities


class TestEntityExtraction:
    def test_extracts_person_names(self):
        text = "Detective Michael Chen is investigating Sarah Johnson's disappearance."
        entities = extract_entities(text)
        person_names = [e["text"] for e in entities if e["type"] == "PERSON"]
        assert any("Chen" in name for name in person_names)
        assert any("Johnson" in name for name in person_names)

    def test_extracts_locations(self):
        text = "She was last seen in Portland, Oregon near Main Street."
        entities = extract_entities(text)
        location_types = {"GPE", "LOC", "FAC"}
        locations = [e["text"] for e in entities if e["type"] in location_types]
        assert any("Portland" in loc for loc in locations)

    def test_extracts_dates(self):
        text = "Nancy was last seen on January 31, 2026 at 9:45 PM."
        entities = extract_entities(text)
        dates = [e["text"] for e in entities if e["type"] in {"DATE", "TIME"}]
        assert len(dates) > 0

    def test_extracts_organizations(self):
        text = "The FBI and Pima County Sheriff's Department are investigating."
        entities = extract_entities(text)
        orgs = [e["text"] for e in entities if e["type"] == "ORG"]
        assert any("FBI" in org for org in orgs)

    def test_returns_structured_data(self):
        text = "John Smith was seen in Tucson."
        entities = extract_entities(text)
        assert len(entities) > 0
        entity = entities[0]
        assert "text" in entity
        assert "type" in entity
        assert "start" in entity
        assert "end" in entity

    def test_handles_empty_text(self):
        entities = extract_entities("")
        assert entities == []

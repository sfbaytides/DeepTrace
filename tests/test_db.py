"""Tests for the database layer."""


import pytest

from deeptrace.db import CaseDatabase


@pytest.fixture
def db(tmp_path):
    db = CaseDatabase(tmp_path / "test.db")
    db.open()
    db.initialize_schema()
    yield db
    db.close()


class TestCaseDatabase:
    def test_creates_database_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = CaseDatabase(db_path)
        db.open()
        db.initialize_schema()
        db.close()
        assert db_path.exists()

    def test_creates_all_tables(self, db):
        tables = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [row["name"] for row in tables]
        assert "sources" in table_names
        assert "entities" in table_names
        assert "events" in table_names
        assert "hypotheses" in table_names
        assert "suspect_pools" in table_names
        assert "evidence_items" in table_names
        assert "statements" in table_names
        assert "anomalies" in table_names
        assert "victim_profile" in table_names
        assert "relationships" in table_names
        # Methodology integration tables
        assert "hypothesis_evidence_scores" in table_names
        assert "indicators" in table_names
        assert "case_review_items" in table_names

    def test_context_manager(self, tmp_path):
        db_path = tmp_path / "test.db"
        with CaseDatabase(db_path) as db:
            db.initialize_schema()
            tables = db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            assert len(tables) > 0

    def test_insert_and_retrieve_source(self, db):
        with db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO sources (raw_text, source_type) VALUES (?, ?)",
                ("Article text here", "news"),
            )
        sources = db.fetchall("SELECT * FROM sources")
        assert len(sources) == 1
        assert sources[0]["raw_text"] == "Article text here"
        assert sources[0]["source_type"] == "news"

    def test_insert_and_retrieve_event(self, db):
        with db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO events (timestamp_start, description, confidence) VALUES (?, ?, ?)",
                ("2024-01-15T14:30:00", "Victim last seen", "high"),
            )
        events = db.fetchall("SELECT * FROM events")
        assert len(events) == 1
        assert events[0]["description"] == "Victim last seen"
        assert events[0]["confidence"] == "high"

    def test_insert_and_retrieve_hypothesis(self, db):
        with db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO hypotheses (description, tier) VALUES (?, ?)",
                ("Perpetrator knew the victim", "most-probable"),
            )
        hypotheses = db.fetchall("SELECT * FROM hypotheses")
        assert len(hypotheses) == 1
        assert hypotheses[0]["tier"] == "most-probable"

    def test_source_reliability_fields(self, db):
        """Test Admiralty/NATO source reliability fields."""
        with db.transaction() as cursor:
            cursor.execute(
                """INSERT INTO sources
                   (raw_text, source_type, source_reliability,
                    information_accuracy, access_assessment,
                    bias_assessment)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    "Sheriff statement", "official", "A", "2",
                    "Direct involvement",
                    "Law enforcement perspective",
                ),
            )
        sources = db.fetchall("SELECT * FROM sources")
        assert sources[0]["source_reliability"] == "A"
        assert sources[0]["information_accuracy"] == "2"

    def test_hypothesis_evidence_scores(self, db):
        """Test ACH consistency matrix table."""
        with db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO hypotheses (description, tier) VALUES (?, ?)",
                ("Test hypothesis", "plausible"),
            )
            cursor.execute(
                "INSERT INTO evidence_items (name, evidence_type, status) VALUES (?, ?, ?)",
                ("DNA sample", "physical", "processed"),
            )
            cursor.execute(
                """INSERT INTO hypothesis_evidence_scores
                   (hypothesis_id, evidence_id, consistency,
                    diagnostic_weight)
                   VALUES (?, ?, ?, ?)""",
                (1, 1, "C", "H"),
            )
        scores = db.fetchall("SELECT * FROM hypothesis_evidence_scores")
        assert len(scores) == 1
        assert scores[0]["consistency"] == "C"
        assert scores[0]["diagnostic_weight"] == "H"

    def test_indicators(self, db):
        """Test signpost/indicator table."""
        with db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO hypotheses (description, tier) VALUES (?, ?)",
                ("Test hypothesis", "plausible"),
            )
            cursor.execute(
                """INSERT INTO indicators (hypothesis_id, description, status)
                   VALUES (?, ?, ?)""",
                (1, "DNA match in CODIS", "pending"),
            )
        indicators = db.fetchall("SELECT * FROM indicators")
        assert len(indicators) == 1
        assert indicators[0]["status"] == "pending"

    def test_case_review_items(self, db):
        """Test cold case completeness checklist table."""
        with db.transaction() as cursor:
            cursor.execute(
                """INSERT INTO case_review_items (category, item_name, status)
                   VALUES (?, ?, ?)""",
                ("original_report", "First responder reports", "located"),
            )
        items = db.fetchall("SELECT * FROM case_review_items")
        assert len(items) == 1
        assert items[0]["status"] == "located"

    def test_evidence_forensic_gap_fields(self, db):
        """Test forensic technology gap analysis fields on evidence_items."""
        with db.transaction() as cursor:
            cursor.execute(
                """INSERT INTO evidence_items
                   (name, evidence_type, status, original_testing,
                    contemporary_testing_available,
                    resubmission_status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    "Blood sample", "physical", "known",
                    "ABO typing only", "STR DNA profiling",
                    "recommended",
                ),
            )
        items = db.fetchall("SELECT * FROM evidence_items")
        assert items[0]["original_testing"] == "ABO typing only"
        assert items[0]["contemporary_testing_available"] == "STR DNA profiling"
        assert items[0]["resubmission_status"] == "recommended"

    def test_transaction_rollback_on_error(self, db):
        with db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO sources (raw_text, source_type) VALUES (?, ?)",
                ("Good data", "news"),
            )
        try:
            with db.transaction() as cursor:
                cursor.execute(
                    "INSERT INTO sources (raw_text, source_type) VALUES (?, ?)",
                    ("Bad data", "news"),
                )
                raise ValueError("Simulated error")
        except ValueError:
            pass
        sources = db.fetchall("SELECT * FROM sources")
        assert len(sources) == 1
        assert sources[0]["raw_text"] == "Good data"

    def test_parameterized_queries_prevent_injection(self, db):
        malicious = "'; DROP TABLE events; --"
        with db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO events (description, confidence) VALUES (?, ?)",
                (malicious, "low"),
            )
        events = db.fetchall("SELECT * FROM events")
        assert len(events) == 1
        assert events[0]["description"] == malicious

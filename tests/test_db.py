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

    def test_attachments_v4_columns(self, db):
        """Verify v4 attachments table has file_path, sha256, source_url."""
        row = db.fetchone(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='attachments'"
        )
        schema = row["sql"]
        assert "file_path" in schema
        assert "sha256" in schema
        assert "source_url" in schema
        assert "data BLOB" not in schema

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


def test_migrate_v3_to_v4_extracts_blobs(tmp_path):
    """v3 databases with BLOB data should migrate to disk files."""
    import hashlib

    from deeptrace.db import CaseDatabase, migrate_v3_to_v4

    db_path = tmp_path / "case.db"
    db = CaseDatabase(db_path)
    db.open()

    # Create v3 schema manually (with data BLOB column)
    db.conn.executescript("""
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version (version) VALUES (3);
        CREATE TABLE attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            data BLOB NOT NULL,
            thumbnail BLOB,
            description TEXT,
            ai_analysis TEXT,
            ai_analyzed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    db.conn.execute(
        "INSERT INTO attachments (filename, mime_type, file_size, data, thumbnail) "
        "VALUES (?, ?, ?, ?, ?)",
        ("photo.jpg", "image/jpeg", 4, b"\xff\xd8\xff\xe0", b"\x89PNG"),
    )
    db.conn.commit()

    # Run migration
    attachments_dir = tmp_path / "attachments"
    migrate_v3_to_v4(db, attachments_dir)

    # File should exist on disk
    row = db.fetchone("SELECT file_path, sha256, thumbnail_path FROM attachments WHERE id = 1")
    assert row is not None
    assert (tmp_path / row["file_path"]).exists()
    assert (tmp_path / row["file_path"]).read_bytes() == b"\xff\xd8\xff\xe0"

    # SHA-256 should be correct
    expected_hash = hashlib.sha256(b"\xff\xd8\xff\xe0").hexdigest()
    assert row["sha256"] == expected_hash

    # Thumbnail should exist on disk
    assert row["thumbnail_path"] is not None
    assert (tmp_path / row["thumbnail_path"]).exists()

    # Schema version should be 4
    ver = db.fetchone("SELECT version FROM schema_version")
    assert ver["version"] == 4

    # data BLOB column should be gone
    cols = [r["name"] for r in db.fetchall("PRAGMA table_info(attachments)")]
    assert "data" not in cols
    assert "file_path" in cols
    assert "sha256" in cols

    db.close()


def test_open_v3_database_triggers_migration(tmp_path):
    """Opening a v3 case should auto-migrate to v4."""
    import sqlite3

    from deeptrace.db import CaseDatabase

    case_dir = tmp_path / "old-case"
    case_dir.mkdir()
    db_path = case_dir / "case.db"

    # Create a minimal v3 database
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version (version) VALUES (3);
        CREATE TABLE attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            data BLOB NOT NULL,
            thumbnail BLOB,
            description TEXT,
            ai_analysis TEXT,
            ai_analyzed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.execute(
        "INSERT INTO attachments (filename, mime_type, file_size, data) "
        "VALUES (?, ?, ?, ?)",
        ("test.jpg", "image/jpeg", 5, b"hello"),
    )
    conn.commit()
    conn.close()

    # Open with CaseDatabase — should auto-migrate via maybe_migrate
    db = CaseDatabase(db_path)
    db.open()
    db.maybe_migrate(case_dir)

    ver = db.fetchone("SELECT version FROM schema_version")
    assert ver["version"] == 4

    row = db.fetchone("SELECT file_path, sha256 FROM attachments WHERE id = 1")
    assert row["file_path"] is not None
    assert row["sha256"] is not None
    assert (case_dir / "attachments" / "1_test.jpg").exists()

    db.close()
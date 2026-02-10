"""Tests for attachments schema and files dashboard routes."""

import sqlite3

import pytest

from deeptrace.db import CaseDatabase

try:
    import flask  # noqa: F401

    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


@pytest.fixture()
def db(tmp_path):
    """Create a fresh case database."""
    path = tmp_path / "test_case.db"
    d = CaseDatabase(path)
    d.open()
    d.initialize_schema()
    yield d
    d.close()


class TestAttachmentsSchema:
    """Verify the attachments and attachment_links tables are created."""

    def test_attachments_table_exists(self, db):
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='attachments'"
        )
        assert row is not None

    def test_attachment_links_table_exists(self, db):
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='attachment_links'"
        )
        assert row is not None

    def test_insert_attachment(self, db):
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO attachments (filename, mime_type, file_size, file_path, sha256) "
                "VALUES (?, ?, ?, ?, ?)",
                ("photo.jpg", "image/jpeg", 1024,
                 "attachments/1_photo.jpg", "abc123"),
            )
        row = db.fetchone("SELECT * FROM attachments WHERE id = 1")
        assert row is not None
        assert row["filename"] == "photo.jpg"
        assert row["mime_type"] == "image/jpeg"
        assert row["file_size"] == 1024
        assert row["file_path"] == "attachments/1_photo.jpg"
        assert row["sha256"] == "abc123"

    def test_insert_attachment_with_optional_fields(self, db):
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO attachments "
                "(filename, mime_type, file_size, file_path, sha256, "
                "description, thumbnail_path, source_url) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("doc.pdf", "application/pdf", 2048,
                 "attachments/1_doc.pdf", "def456",
                 "A report", "attachments/thumbs/1_doc.png",
                 "https://example.com/doc.pdf"),
            )
        row = db.fetchone("SELECT * FROM attachments WHERE id = 1")
        assert row["description"] == "A report"
        assert row["thumbnail_path"] == "attachments/thumbs/1_doc.png"
        assert row["source_url"] == "https://example.com/doc.pdf"
        assert row["ai_analysis"] is None
        assert row["ai_analyzed_at"] is None

    def test_attachment_link_insert(self, db):
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO attachments (filename, mime_type, file_size, file_path, sha256) "
                "VALUES (?, ?, ?, ?, ?)",
                ("photo.jpg", "image/jpeg", 1024,
                 "attachments/1_photo.jpg", "abc123"),
            )
            cur.execute(
                "INSERT INTO evidence_items (name, evidence_type, status) "
                "VALUES (?, ?, ?)",
                ("knife", "physical", "known"),
            )
            cur.execute(
                "INSERT INTO attachment_links (attachment_id, entity_type, entity_id) "
                "VALUES (?, ?, ?)",
                (1, "evidence", 1),
            )
        row = db.fetchone("SELECT * FROM attachment_links WHERE id = 1")
        assert row["attachment_id"] == 1
        assert row["entity_type"] == "evidence"
        assert row["entity_id"] == 1

    def test_attachment_link_check_constraint(self, db):
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO attachments (filename, mime_type, file_size, file_path, sha256) "
                "VALUES (?, ?, ?, ?, ?)",
                ("photo.jpg", "image/jpeg", 1024,
                 "attachments/1_photo.jpg", "abc123"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            with db.transaction() as cur:
                cur.execute(
                    "INSERT INTO attachment_links (attachment_id, entity_type, entity_id) "
                    "VALUES (?, ?, ?)",
                    (1, "invalid_type", 1),
                )

    def test_attachment_link_unique_constraint(self, db):
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO attachments (filename, mime_type, file_size, file_path, sha256) "
                "VALUES (?, ?, ?, ?, ?)",
                ("photo.jpg", "image/jpeg", 1024,
                 "attachments/1_photo.jpg", "abc123"),
            )
            cur.execute(
                "INSERT INTO evidence_items (name, evidence_type, status) "
                "VALUES (?, ?, ?)",
                ("knife", "physical", "known"),
            )
            cur.execute(
                "INSERT INTO attachment_links (attachment_id, entity_type, entity_id) "
                "VALUES (?, ?, ?)",
                (1, "evidence", 1),
            )
        # INSERT OR IGNORE should not raise
        with db.transaction() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO attachment_links "
                "(attachment_id, entity_type, entity_id) VALUES (?, ?, ?)",
                (1, "evidence", 1),
            )
        count = db.fetchone("SELECT COUNT(*) as c FROM attachment_links")["c"]
        assert count == 1

    def test_cascade_delete_attachment(self, db):
        """Deleting an attachment should cascade-delete its links."""
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO attachments (filename, mime_type, file_size, file_path, sha256) "
                "VALUES (?, ?, ?, ?, ?)",
                ("photo.jpg", "image/jpeg", 1024,
                 "attachments/1_photo.jpg", "abc123"),
            )
            cur.execute(
                "INSERT INTO evidence_items (name, evidence_type, status) "
                "VALUES (?, ?, ?)",
                ("knife", "physical", "known"),
            )
            cur.execute(
                "INSERT INTO attachment_links (attachment_id, entity_type, entity_id) "
                "VALUES (?, ?, ?)",
                (1, "evidence", 1),
            )
        # Verify link exists
        assert db.fetchone("SELECT COUNT(*) as c FROM attachment_links")["c"] == 1
        # Delete attachment
        with db.transaction() as cur:
            cur.execute("DELETE FROM attachments WHERE id = 1")
        # Link should be cascade-deleted
        assert db.fetchone("SELECT COUNT(*) as c FROM attachment_links")["c"] == 0

    def test_indexes_created(self, db):
        """Verify the attachment-related indexes exist."""
        indexes = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='index' AND "
            "name LIKE '%attachment%'"
        )
        names = {row["name"] for row in indexes}
        assert "idx_attachments_mime" in names
        assert "idx_attachment_link_unique" in names
        assert "idx_attachment_links_entity" in names


@pytest.mark.skipif(not HAS_FLASK, reason="Flask not installed (optional dashboard dependency)")
class TestFilesRoute:
    """Test the dashboard files blueprint (requires Flask test client)."""

    @pytest.fixture()
    def app(self, tmp_path):
        """Create a Flask test app with a case database."""
        import deeptrace.state as _state

        _state.CASES_DIR = tmp_path
        case_dir = tmp_path / "test-case"
        case_dir.mkdir()
        (case_dir / "attachments").mkdir()
        (case_dir / "attachments" / "thumbs").mkdir()
        db = CaseDatabase(case_dir / "case.db")
        db.open()
        db.initialize_schema()
        db.close()

        from deeptrace.dashboard import create_app

        app = create_app("test-case")
        app.config["TESTING"] = True
        return app

    @pytest.fixture()
    def client(self, app):
        return app.test_client()

    def test_files_index_empty(self, client):
        resp = client.get("/files/", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert b"No files uploaded yet" in resp.data

    def test_upload_and_list(self, client):
        from io import BytesIO

        data = {
            "file": (BytesIO(b"fake image data"), "test.png"),
            "description": "Test file",
        }
        resp = client.post(
            "/files/",
            data=data,
            content_type="multipart/form-data",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert b"test.png" in resp.data

    def test_upload_no_file(self, client):
        resp = client.post("/files/", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_detail(self, client):
        from io import BytesIO

        client.post(
            "/files/",
            data={"file": (BytesIO(b"data"), "test.txt")},
            content_type="multipart/form-data",
        )
        resp = client.get("/files/1")
        assert resp.status_code == 200
        assert b"test.txt" in resp.data

    def test_download(self, client):
        from io import BytesIO

        client.post(
            "/files/",
            data={"file": (BytesIO(b"hello world"), "test.txt")},
            content_type="multipart/form-data",
        )
        resp = client.get("/files/1/download")
        assert resp.status_code == 200
        assert resp.data == b"hello world"

    def test_thumbnail_placeholder(self, client):
        from io import BytesIO

        client.post(
            "/files/",
            data={"file": (BytesIO(b"%PDF-1.4"), "doc.pdf")},
            content_type="multipart/form-data",
        )
        resp = client.get("/files/1/thumbnail")
        assert resp.status_code == 200
        assert b"<svg" in resp.data

    def test_delete(self, client):
        from io import BytesIO

        client.post(
            "/files/",
            data={"file": (BytesIO(b"data"), "test.txt")},
            content_type="multipart/form-data",
        )
        resp = client.delete("/files/1")
        assert resp.status_code == 200
        resp = client.get("/files/1")
        assert resp.status_code == 404

    def test_link_and_unlink(self, client, app):
        from io import BytesIO

        import deeptrace.state as _state

        # Upload a file
        client.post(
            "/files/",
            data={"file": (BytesIO(b"data"), "test.txt")},
            content_type="multipart/form-data",
        )
        # Create an evidence item to link to
        case_dir = _state.CASES_DIR / "test-case"
        db = CaseDatabase(case_dir / "case.db")
        db.open()
        try:
            with db.transaction() as cur:
                cur.execute(
                    "INSERT INTO evidence_items (name, evidence_type, status) "
                    "VALUES (?, ?, ?)",
                    ("knife", "physical", "known"),
                )
        finally:
            db.close()

        # Link
        resp = client.post(
            "/files/1/link",
            data={"entity_type": "evidence", "entity_id": "1"},
        )
        assert resp.status_code == 200
        assert b"evidence" in resp.data

        # Unlink
        resp = client.delete("/files/1/link/1")
        assert resp.status_code == 200

    def test_type_filter(self, client):
        from io import BytesIO

        client.post(
            "/files/",
            data={"file": (BytesIO(b"img"), "pic.jpg")},
            content_type="multipart/form-data",
        )
        resp = client.get(
            "/files/?type=image", headers={"HX-Request": "true"}
        )
        assert resp.status_code == 200

    def test_upload_writes_to_disk(self, client, app):
        """Upload should write file to attachments dir, not BLOB."""
        import hashlib
        from io import BytesIO

        import deeptrace.state as _state

        content = b"fake image data for disk test"
        data = {
            "file": (BytesIO(content), "disk_test.png"),
            "description": "Disk storage test",
        }
        resp = client.post(
            "/files/",
            data=data,
            content_type="multipart/form-data",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200

        case_dir = _state.CASES_DIR / "test-case"
        db = CaseDatabase(case_dir / "case.db")
        db.open()
        try:
            row = db.fetchone("SELECT file_path, sha256 FROM attachments WHERE id = 1")
            assert row is not None
            assert row["file_path"].startswith("attachments/")
            assert row["sha256"] == hashlib.sha256(content).hexdigest()
        finally:
            db.close()

    def test_download_from_disk(self, client):
        """Download should serve file from disk."""
        from io import BytesIO

        content = b"hello world from disk"
        client.post(
            "/files/",
            data={"file": (BytesIO(content), "test.txt")},
            content_type="multipart/form-data",
        )
        resp = client.get("/files/1/download")
        assert resp.status_code == 200
        assert resp.data == content

    def test_delete_removes_disk_file(self, client, app):
        """Deleting an attachment should remove the file from disk."""
        from io import BytesIO

        import deeptrace.state as _state

        content = b"delete me"
        client.post(
            "/files/",
            data={"file": (BytesIO(content), "deletable.txt")},
            content_type="multipart/form-data",
        )

        case_dir = _state.CASES_DIR / "test-case"
        attach_dir = case_dir / "attachments"
        # Verify file exists
        files_before = list(attach_dir.glob("1_*"))
        assert len(files_before) > 0

        resp = client.delete("/files/1")
        assert resp.status_code == 200

        files_after = list(attach_dir.glob("1_*"))
        assert len(files_after) == 0

    def test_verify_integrity_passes(self, client):
        """Verify route should confirm file integrity."""
        from io import BytesIO

        client.post(
            "/files/",
            data={"file": (BytesIO(b"integrity check"), "verify.txt")},
            content_type="multipart/form-data",
        )
        resp = client.post("/files/1/verify")
        assert resp.status_code == 200
        assert b"intact" in resp.data.lower()

    def test_forensic_system_prompt_uncensored(self):
        """Verify the forensic system prompt prohibits censorship."""
        from deeptrace.dashboard.routes.files import FORENSIC_SYSTEM_PROMPT
        assert "NEVER censor" in FORENSIC_SYSTEM_PROMPT
        assert "CSAM" in FORENSIC_SYSTEM_PROMPT

    def test_analyze_uses_carl_ai(self, client, app, monkeypatch):
        """AI analysis should use Carl (Ollama) not Anthropic."""
        from io import BytesIO

        import deeptrace.dashboard.routes.files as files_mod

        client.post(
            "/files/",
            data={"file": (BytesIO(b"crime scene photo data"), "scene.jpg")},
            content_type="multipart/form-data",
        )

        # Mock the requests module used by Carl AI
        class MockRequests:
            class exceptions:
                Timeout = Exception
                RequestException = Exception

            @staticmethod
            def post(*a, **kw):
                class MockResponse:
                    status_code = 200
                    def json(self):
                        return {
                            "response": "Analysis: blood spatter pattern "
                            "consistent with blunt force trauma",
                            "model": "qwen2.5:3b-instruct",
                        }
                    def raise_for_status(self):
                        pass
                return MockResponse()

        monkeypatch.setattr(files_mod, "http_requests", MockRequests)

        resp = client.post("/files/1/analyze")
        assert resp.status_code == 200

        import deeptrace.state as _state
        case_dir = _state.CASES_DIR / "test-case"
        db = CaseDatabase(case_dir / "case.db")
        db.open()
        try:
            row = db.fetchone("SELECT ai_analysis FROM attachments WHERE id = 1")
            assert "blood spatter" in row["ai_analysis"]
        finally:
            db.close()

    def test_verify_integrity_fails_on_tamper(self, client, app):
        """Verify should detect tampered files."""
        from io import BytesIO

        import deeptrace.state as _state

        client.post(
            "/files/",
            data={"file": (BytesIO(b"original"), "tamper.txt")},
            content_type="multipart/form-data",
        )

        # Tamper with file on disk
        case_dir = _state.CASES_DIR / "test-case"
        tampered = list((case_dir / "attachments").glob("1_*"))[0]
        tampered.write_bytes(b"tampered content")

        resp = client.post("/files/1/verify")
        assert resp.status_code == 200
        assert b"mismatch" in resp.data.lower()

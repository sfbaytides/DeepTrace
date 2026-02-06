"""Tests for evidence tracker commands."""

import pytest

from deeptrace.db import CaseDatabase
from deeptrace.main import app


@pytest.fixture
def case_with_db(tmp_cases_dir, monkeypatch):
    monkeypatch.setattr("deeptrace.state.CASES_DIR", tmp_cases_dir)
    case_dir = tmp_cases_dir / "test-case"
    case_dir.mkdir(parents=True)
    db = CaseDatabase(case_dir / "case.db")
    db.open()
    db.initialize_schema()
    db.close()
    return "test-case"


VALID_STATUSES = ["known", "processed", "pending", "inconclusive", "missing"]


class TestEvidenceAdd:
    def test_add_evidence(self, runner, case_with_db):
        result = runner.invoke(
            app,
            [
                "evidence", "add",
                "Security camera footage",
                "--case", case_with_db,
                "--type", "digital",
            ],
        )
        assert result.exit_code == 0
        assert "Added evidence" in result.output

    def test_add_with_status(self, runner, case_with_db, tmp_cases_dir):
        runner.invoke(
            app,
            [
                "evidence", "add",
                "DNA sample",
                "--case", case_with_db,
                "--type", "physical",
                "--status", "pending",
            ],
        )
        db = CaseDatabase(tmp_cases_dir / case_with_db / "case.db")
        db.open()
        items = db.fetchall("SELECT * FROM evidence_items")
        db.close()
        assert items[0]["status"] == "pending"

    @pytest.mark.parametrize("status", VALID_STATUSES)
    def test_all_statuses_accepted(self, runner, case_with_db, status):
        result = runner.invoke(
            app,
            [
                "evidence", "add", f"Item {status}",
                "--case", case_with_db,
                "--type", "physical",
                "--status", status,
            ],
        )
        assert result.exit_code == 0


class TestEvidenceShow:
    def test_show_empty(self, runner, case_with_db):
        result = runner.invoke(app, ["evidence", "show", "--case", case_with_db])
        assert result.exit_code == 0
        assert "No evidence" in result.output

    def test_show_evidence_list(self, runner, case_with_db):
        runner.invoke(
            app,
            ["evidence", "add", "Camera footage", "--case", case_with_db, "--type", "digital"],
        )
        runner.invoke(
            app,
            [
                "evidence", "add", "DNA sample",
                "--case", case_with_db,
                "--type", "physical",
                "--status", "pending",
            ],
        )
        result = runner.invoke(app, ["evidence", "show", "--case", case_with_db])
        assert "Camera footage" in result.output
        assert "DNA sample" in result.output


class TestEvidenceUpdate:
    def test_update_status(self, runner, case_with_db, tmp_cases_dir):
        runner.invoke(
            app,
            ["evidence", "add", "DNA sample", "--case", case_with_db, "--type", "physical"],
        )
        result = runner.invoke(
            app,
            ["evidence", "update", "1", "--case", case_with_db, "--status", "processed"],
        )
        assert result.exit_code == 0
        db = CaseDatabase(tmp_cases_dir / case_with_db / "case.db")
        db.open()
        item = db.fetchone("SELECT * FROM evidence_items WHERE id = 1")
        db.close()
        assert item["status"] == "processed"

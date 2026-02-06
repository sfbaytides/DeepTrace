"""Tests for suspect pool commands."""

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


class TestSuspectPoolAdd:
    def test_add_pool(self, runner, case_with_db):
        result = runner.invoke(
            app,
            [
                "suspects", "add",
                "--case", case_with_db,
                "--category", "Intimate knowledge of home",
                "--description", "Someone who knew the layout, camera locations, and entry points",
            ],
        )
        assert result.exit_code == 0
        assert "Added suspect pool" in result.output

    def test_stored_in_db(self, runner, case_with_db, tmp_cases_dir):
        runner.invoke(
            app,
            [
                "suspects", "add",
                "--case", case_with_db,
                "--category", "Physical capability",
                "--description", "Someone able to carry or transport victim",
            ],
        )
        db = CaseDatabase(tmp_cases_dir / case_with_db / "case.db")
        db.open()
        pools = db.fetchall("SELECT * FROM suspect_pools")
        db.close()
        assert len(pools) == 1
        assert pools[0]["category"] == "Physical capability"


class TestSuspectPoolShow:
    def test_show_empty(self, runner, case_with_db):
        result = runner.invoke(app, ["suspects", "show", "--case", case_with_db])
        assert result.exit_code == 0
        assert "No suspect pools" in result.output

    def test_show_pools(self, runner, case_with_db):
        runner.invoke(
            app,
            [
                "suspects", "add", "--case", case_with_db,
                "--category", "Pool A",
                "--description", "Desc A",
            ],
        )
        runner.invoke(
            app,
            [
                "suspects", "add", "--case", case_with_db,
                "--category", "Pool B",
                "--description", "Desc B",
            ],
        )
        result = runner.invoke(app, ["suspects", "show", "--case", case_with_db])
        assert "Pool A" in result.output
        assert "Pool B" in result.output

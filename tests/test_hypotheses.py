"""Tests for hypothesis tracker commands."""

import pytest
from deeptrace.main import app
from deeptrace.db import CaseDatabase


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


TIERS = ["most-probable", "plausible", "less-likely", "unlikely"]


class TestHypothesesAdd:
    def test_add_hypothesis(self, runner, case_with_db):
        result = runner.invoke(
            app,
            ["hypotheses", "add", "Perpetrator knew the victim", "--case", case_with_db],
        )
        assert result.exit_code == 0
        assert "Added hypothesis" in result.output

    def test_add_with_tier(self, runner, case_with_db, tmp_cases_dir):
        runner.invoke(
            app,
            [
                "hypotheses", "add",
                "Targeted attack",
                "--case", case_with_db,
                "--tier", "most-probable",
            ],
        )
        db = CaseDatabase(tmp_cases_dir / case_with_db / "case.db")
        db.open()
        h = db.fetchall("SELECT * FROM hypotheses")
        db.close()
        assert h[0]["tier"] == "most-probable"

    @pytest.mark.parametrize("tier", TIERS)
    def test_all_tiers_accepted(self, runner, case_with_db, tier):
        result = runner.invoke(
            app,
            ["hypotheses", "add", f"Test {tier}", "--case", case_with_db, "--tier", tier],
        )
        assert result.exit_code == 0


class TestHypothesesShow:
    def test_show_empty(self, runner, case_with_db):
        result = runner.invoke(app, ["hypotheses", "show", "--case", case_with_db])
        assert result.exit_code == 0
        assert "No hypotheses" in result.output

    def test_show_grouped_by_tier(self, runner, case_with_db):
        runner.invoke(
            app,
            ["hypotheses", "add", "Theory A", "--case", case_with_db, "--tier", "most-probable"],
        )
        runner.invoke(
            app,
            ["hypotheses", "add", "Theory B", "--case", case_with_db, "--tier", "unlikely"],
        )
        result = runner.invoke(app, ["hypotheses", "show", "--case", case_with_db])
        assert "Theory A" in result.output
        assert "Theory B" in result.output


class TestHypothesesUpdate:
    def test_update_tier(self, runner, case_with_db, tmp_cases_dir):
        runner.invoke(
            app,
            ["hypotheses", "add", "Theory A", "--case", case_with_db, "--tier", "plausible"],
        )
        result = runner.invoke(
            app,
            ["hypotheses", "update", "1", "--case", case_with_db, "--tier", "most-probable"],
        )
        assert result.exit_code == 0
        db = CaseDatabase(tmp_cases_dir / case_with_db / "case.db")
        db.open()
        h = db.fetchone("SELECT * FROM hypotheses WHERE id = 1")
        db.close()
        assert h["tier"] == "most-probable"

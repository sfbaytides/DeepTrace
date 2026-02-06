"""Tests for source ingestion commands."""

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


class TestAddSource:
    def test_add_source_with_text(self, runner, case_with_db, tmp_cases_dir):
        result = runner.invoke(
            app,
            [
                "add-source", "--case", case_with_db,
                "--type", "news",
                "--text", "Article content here",
            ],
        )
        assert result.exit_code == 0
        assert "Added source" in result.output

        db = CaseDatabase(tmp_cases_dir / case_with_db / "case.db")
        db.open()
        sources = db.fetchall("SELECT * FROM sources")
        db.close()
        assert len(sources) == 1
        assert sources[0]["raw_text"] == "Article content here"
        assert sources[0]["source_type"] == "news"

    def test_add_source_with_url(self, runner, case_with_db, tmp_cases_dir):
        result = runner.invoke(
            app,
            [
                "add-source",
                "--case", case_with_db,
                "--type", "news",
                "--text", "Content from the article",
                "--url", "https://example.com/article",
            ],
        )
        assert result.exit_code == 0
        db = CaseDatabase(tmp_cases_dir / case_with_db / "case.db")
        db.open()
        sources = db.fetchall("SELECT * FROM sources")
        db.close()
        assert sources[0]["url"] == "https://example.com/article"

    def test_add_source_requires_case(self, runner, tmp_cases_dir, monkeypatch):
        monkeypatch.setattr("deeptrace.state.CASES_DIR", tmp_cases_dir)
        result = runner.invoke(
            app,
            ["add-source", "--case", "nonexistent", "--type", "news", "--text", "text"],
        )
        assert result.exit_code != 0

    def test_add_source_with_reliability(self, runner, case_with_db, tmp_cases_dir):
        result = runner.invoke(
            app,
            [
                "add-source",
                "--case", case_with_db,
                "--type", "official",
                "--text", "Sheriff statement",
                "--reliability", "0.9",
            ],
        )
        assert result.exit_code == 0
        db = CaseDatabase(tmp_cases_dir / case_with_db / "case.db")
        db.open()
        sources = db.fetchall("SELECT * FROM sources")
        db.close()
        assert sources[0]["reliability_score"] == 0.9

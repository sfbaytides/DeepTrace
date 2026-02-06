"""Tests for case management commands."""

import pytest
from deeptrace.main import app


class TestNewCase:
    def test_creates_case_directory(self, runner, tmp_cases_dir, monkeypatch):
        monkeypatch.setattr("deeptrace.state.CASES_DIR", tmp_cases_dir)
        result = runner.invoke(app, ["new", "Nancy Guthrie Disappearance"])
        assert result.exit_code == 0
        assert (tmp_cases_dir / "nancy-guthrie-disappearance" / "case.db").exists()

    def test_prints_confirmation(self, runner, tmp_cases_dir, monkeypatch):
        monkeypatch.setattr("deeptrace.state.CASES_DIR", tmp_cases_dir)
        result = runner.invoke(app, ["new", "Test Case"])
        assert result.exit_code == 0
        assert "Created case" in result.output

    def test_rejects_duplicate_name(self, runner, tmp_cases_dir, monkeypatch):
        monkeypatch.setattr("deeptrace.state.CASES_DIR", tmp_cases_dir)
        runner.invoke(app, ["new", "Test Case"])
        result = runner.invoke(app, ["new", "Test Case"])
        assert result.exit_code != 0
        assert "already exists" in result.output


class TestListCases:
    def test_shows_no_cases(self, runner, tmp_cases_dir, monkeypatch):
        monkeypatch.setattr("deeptrace.state.CASES_DIR", tmp_cases_dir)
        result = runner.invoke(app, ["cases"])
        assert result.exit_code == 0
        assert "No cases" in result.output

    def test_lists_existing_cases(self, runner, tmp_cases_dir, monkeypatch):
        monkeypatch.setattr("deeptrace.state.CASES_DIR", tmp_cases_dir)
        runner.invoke(app, ["new", "Case One"])
        runner.invoke(app, ["new", "Case Two"])
        result = runner.invoke(app, ["cases"])
        assert result.exit_code == 0
        assert "case-one" in result.output
        assert "case-two" in result.output


class TestOpenCase:
    def test_opens_existing_case(self, runner, tmp_cases_dir, monkeypatch):
        monkeypatch.setattr("deeptrace.state.CASES_DIR", tmp_cases_dir)
        runner.invoke(app, ["new", "Test Case"])
        result = runner.invoke(app, ["open", "test-case"])
        assert result.exit_code == 0
        assert "Opened case" in result.output

    def test_rejects_nonexistent_case(self, runner, tmp_cases_dir, monkeypatch):
        monkeypatch.setattr("deeptrace.state.CASES_DIR", tmp_cases_dir)
        result = runner.invoke(app, ["open", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

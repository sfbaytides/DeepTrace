"""Tests for timeline commands."""

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


class TestTimelineAdd:
    def test_add_event(self, runner, case_with_db, tmp_cases_dir):
        result = runner.invoke(
            app,
            [
                "timeline", "add",
                "Victim last seen at home",
                "--case", case_with_db,
                "--date", "2024-01-31T21:45:00",
                "--confidence", "high",
            ],
        )
        assert result.exit_code == 0
        assert "Added event" in result.output

    def test_add_event_stored_in_db(self, runner, case_with_db, tmp_cases_dir):
        runner.invoke(
            app,
            [
                "timeline", "add",
                "Victim last seen",
                "--case", case_with_db,
                "--date", "2024-01-31T21:45:00",
            ],
        )
        db = CaseDatabase(tmp_cases_dir / case_with_db / "case.db")
        db.open()
        events = db.fetchall("SELECT * FROM events ORDER BY timestamp_start")
        db.close()
        assert len(events) == 1
        assert events[0]["description"] == "Victim last seen"


class TestTimelineShow:
    def test_show_empty_timeline(self, runner, case_with_db):
        result = runner.invoke(app, ["timeline", "show", "--case", case_with_db])
        assert result.exit_code == 0
        assert "No events" in result.output

    def test_show_timeline_with_events(self, runner, case_with_db):
        runner.invoke(
            app,
            [
                "timeline", "add", "Event one",
                "--case", case_with_db,
                "--date", "2024-01-31T21:00:00",
            ],
        )
        runner.invoke(
            app,
            [
                "timeline", "add", "Event two",
                "--case", case_with_db,
                "--date", "2024-02-01T02:00:00",
            ],
        )
        result = runner.invoke(app, ["timeline", "show", "--case", case_with_db])
        assert result.exit_code == 0
        assert "Event one" in result.output
        assert "Event two" in result.output


class TestTimelineGaps:
    def test_gaps_with_no_events(self, runner, case_with_db):
        result = runner.invoke(app, ["timeline", "gaps", "--case", case_with_db])
        assert result.exit_code == 0

    def test_identifies_gap(self, runner, case_with_db):
        runner.invoke(
            app,
            [
                "timeline", "add", "Event one",
                "--case", case_with_db,
                "--date", "2024-01-31T21:00:00",
            ],
        )
        runner.invoke(
            app,
            [
                "timeline", "add", "Event two",
                "--case", case_with_db,
                "--date", "2024-02-01T14:00:00",
            ],
        )
        result = runner.invoke(app, ["timeline", "gaps", "--case", case_with_db])
        assert result.exit_code == 0
        # Should identify the ~17 hour gap
        assert "gap" in result.output.lower()

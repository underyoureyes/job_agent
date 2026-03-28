"""
tests/unit/test_tracker.py
==========================
Unit tests for tracker.py — ApplicationTracker SQLite wrapper.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from tracker import ApplicationTracker, STATUS_FLOW, STATUS_COLOURS


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path) -> ApplicationTracker:
    return ApplicationTracker(tmp_path / "test.db")


def _job(url: str = "https://example.com/job/1", title: str = "Policy Analyst") -> dict:
    return {
        "title": title,
        "employer": "Cabinet Office",
        "location": "London",
        "salary": "£35,000",
        "url": url,
        "description": "Great policy role.",
        "source": "reed",
        "date_closes": "2026-04-30",
        "match_score": None,
        "match_reason": None,
    }


# ── Schema / init ──────────────────────────────────────────────────────────────

class TestInit:

    def test_creates_db_file(self, tmp_path):
        db_path = tmp_path / "new.db"
        ApplicationTracker(db_path)
        assert db_path.exists()

    def test_jobs_table_exists(self, db):
        with db._connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [r[0] for r in tables]
        assert "jobs" in table_names
        assert "events" in table_names


# ── add_job / get_job / job_exists ────────────────────────────────────────────

class TestAddAndGet:

    def test_add_job_returns_id(self, db):
        job_id = db.add_job(_job())
        assert isinstance(job_id, int)
        assert job_id > 0

    def test_get_job_returns_dict(self, db):
        job_id = db.add_job(_job())
        result = db.get_job(job_id)
        assert result is not None
        assert result["title"] == "Policy Analyst"
        assert result["employer"] == "Cabinet Office"

    def test_get_job_unknown_id_returns_none(self, db):
        assert db.get_job(9999) is None

    def test_job_exists_true(self, db):
        db.add_job(_job(url="https://example.com/job/42"))
        assert db.job_exists("https://example.com/job/42") is True

    def test_job_exists_false(self, db):
        assert db.job_exists("https://example.com/job/999") is False

    def test_add_job_status_is_discovered(self, db):
        job_id = db.add_job(_job())
        assert db.get_job(job_id)["status"] == "discovered"

    def test_add_job_logs_discovered_event(self, db):
        job_id = db.add_job(_job())
        events = db.get_events(job_id)
        assert any(e["event"] == "discovered" for e in events)

    def test_add_job_with_optional_fields(self, db):
        job = _job()
        job["match_score"] = 75
        job["match_reason"] = "Strong match"
        job_id = db.add_job(job)
        result = db.get_job(job_id)
        assert result["match_score"] == 75


# ── update_status ─────────────────────────────────────────────────────────────

class TestUpdateStatus:

    def test_update_status_changes_status(self, db):
        job_id = db.add_job(_job())
        db.update_status(job_id, "scored")
        assert db.get_job(job_id)["status"] == "scored"

    def test_update_status_logs_event(self, db):
        job_id = db.add_job(_job())
        db.update_status(job_id, "tailored", "CV and cover letter done")
        events = db.get_events(job_id)
        assert any("tailored" in e["event"] for e in events)

    def test_multiple_status_changes(self, db):
        job_id = db.add_job(_job())
        for status in ["score_me", "scored", "tailoring", "tailored"]:
            db.update_status(job_id, status)
        assert db.get_job(job_id)["status"] == "tailored"
        assert len(db.get_events(job_id)) >= 5  # discovered + 4 changes


# ── update_documents ──────────────────────────────────────────────────────────

class TestUpdateDocuments:

    def test_update_documents_sets_paths(self, db):
        job_id = db.add_job(_job())
        db.update_documents(job_id, "/path/to/cv.docx", "/path/to/letter.docx")
        result = db.get_job(job_id)
        assert result["tailored_cv_path"] == "/path/to/cv.docx"
        assert result["cover_letter_path"] == "/path/to/letter.docx"

    def test_update_documents_sets_status_tailored(self, db):
        job_id = db.add_job(_job())
        db.update_documents(job_id, "/cv.docx", "/letter.docx")
        assert db.get_job(job_id)["status"] == "tailored"

    def test_update_documents_logs_event(self, db):
        job_id = db.add_job(_job())
        db.update_documents(job_id, "/cv.docx", "/letter.docx")
        events = db.get_events(job_id)
        assert any("tailored" in e["event"] for e in events)


# ── add_note ──────────────────────────────────────────────────────────────────

class TestAddNote:

    def test_add_note_saves_note(self, db):
        job_id = db.add_job(_job())
        db.add_note(job_id, "Follow up on Monday")
        result = db.get_job(job_id)
        assert result["notes"] == "Follow up on Monday"

    def test_add_note_logs_event(self, db):
        job_id = db.add_job(_job())
        db.add_note(job_id, "Interesting role")
        events = db.get_events(job_id)
        assert any(e["event"] == "note" for e in events)

    def test_add_note_event_contains_text(self, db):
        job_id = db.add_job(_job())
        db.add_note(job_id, "Great salary")
        events = db.get_events(job_id)
        note_events = [e for e in events if e["event"] == "note"]
        assert any("Great salary" in e["detail"] for e in note_events)


# ── Query methods ─────────────────────────────────────────────────────────────

class TestQueryMethods:

    def test_get_jobs_by_status(self, db):
        j1 = db.add_job(_job(url="https://a.com/1"))
        j2 = db.add_job(_job(url="https://a.com/2"))
        db.update_status(j1, "scored")
        results = db.get_jobs_by_status("scored")
        assert len(results) == 1
        assert results[0]["id"] == j1

    def test_get_all_jobs_empty(self, db):
        assert db.get_all_jobs() == []

    def test_get_all_jobs_returns_all(self, db):
        for i in range(5):
            db.add_job(_job(url=f"https://example.com/job/{i}"))
        assert len(db.get_all_jobs()) == 5

    def test_get_pending_review_returns_tailored(self, db):
        job_id = db.add_job(_job())
        db.update_status(job_id, "tailored")
        results = db.get_pending_review()
        assert len(results) == 1

    def test_get_pending_review_returns_pending_review(self, db):
        job_id = db.add_job(_job())
        db.update_status(job_id, "pending_review")
        results = db.get_pending_review()
        assert len(results) == 1

    def test_get_pending_review_excludes_approved(self, db):
        job_id = db.add_job(_job())
        db.update_status(job_id, "approved")
        assert db.get_pending_review() == []

    def test_get_discovered_jobs(self, db):
        j1 = db.add_job(_job(url="https://a.com/1"))
        j2 = db.add_job(_job(url="https://a.com/2"))
        db.update_status(j2, "scored")
        results = db.get_discovered_jobs()
        assert len(results) == 1
        assert results[0]["id"] == j1

    def test_get_scored_jobs(self, db):
        job_id = db.add_job(_job())
        db.update_status(job_id, "scored")
        results = db.get_scored_jobs()
        assert len(results) == 1

    def test_get_scored_jobs_ordered_by_score(self, db):
        j1 = db.add_job(_job(url="https://a.com/1", title="Low Score Job"))
        j2 = db.add_job(_job(url="https://a.com/2", title="High Score Job"))
        db.update_status(j1, "scored")
        db.update_status(j2, "scored")
        with db._connect() as conn:
            conn.execute("UPDATE jobs SET match_score=30 WHERE id=?", (j1,))
            conn.execute("UPDATE jobs SET match_score=90 WHERE id=?", (j2,))
        results = db.get_scored_jobs()
        assert results[0]["match_score"] == 90

    def test_get_jobs_for_screening_returns_discovered_and_scored(self, db):
        j1 = db.add_job(_job(url="https://a.com/1"))  # discovered
        j2 = db.add_job(_job(url="https://a.com/2"))  # scored with high score
        db.update_status(j2, "scored")
        with db._connect() as conn:
            conn.execute("UPDATE jobs SET match_score=80 WHERE id=?", (j2,))
        results = db.get_jobs_for_screening()
        ids = [r["id"] for r in results]
        assert j1 in ids
        assert j2 in ids

    def test_get_jobs_for_screening_excludes_low_scores(self, db):
        job_id = db.add_job(_job())
        db.update_status(job_id, "scored")
        with db._connect() as conn:
            conn.execute("UPDATE jobs SET match_score=20 WHERE id=?", (job_id,))
        results = db.get_jobs_for_screening()
        ids = [r["id"] for r in results]
        assert job_id not in ids

    def test_get_events_returns_list(self, db):
        job_id = db.add_job(_job())
        events = db.get_events(job_id)
        assert isinstance(events, list)
        assert len(events) >= 1

    def test_get_events_sorted_by_timestamp(self, db):
        job_id = db.add_job(_job())
        db.update_status(job_id, "score_me")
        db.update_status(job_id, "scored")
        events = db.get_events(job_id)
        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps)


# ── print_dashboard ────────────────────────────────────────────────────────────

class TestPrintDashboard:

    def test_print_dashboard_no_jobs(self, db, capsys):
        db.print_dashboard()
        # Should not raise; output is to rich console (not captured by capsys)

    def test_print_dashboard_with_jobs(self, db):
        for i in range(3):
            job_id = db.add_job(_job(url=f"https://example.com/{i}"))
        db.update_status(job_id, "scored")
        # Should not raise
        db.print_dashboard()

    def test_print_dashboard_many_jobs(self, db):
        for i in range(25):
            db.add_job(_job(url=f"https://example.com/{i}"))
        # Should not raise (tests the "> 20" branch)
        db.print_dashboard()


# ── STATUS constants ──────────────────────────────────────────────────────────

class TestStatusConstants:

    def test_status_flow_is_list(self):
        assert isinstance(STATUS_FLOW, list)
        assert len(STATUS_FLOW) > 0

    def test_status_colours_covers_flow(self):
        for status in STATUS_FLOW:
            assert status in STATUS_COLOURS

    def test_discovered_in_flow(self):
        assert "discovered" in STATUS_FLOW

    def test_submitted_in_flow(self):
        assert "submitted" in STATUS_FLOW

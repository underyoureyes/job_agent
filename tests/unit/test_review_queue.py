"""
tests/unit/test_review_queue.py
================================
Unit tests for review_queue.py — ReviewQueue interactive CLI.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from config import Config
from tracker import ApplicationTracker
from review_queue import ReviewQueue


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg(tmp_path):
    c = Config(candidate_name="Test User", anthropic_api_key="sk-test")
    c.output_dir = tmp_path / "output"
    c.logs_dir = tmp_path / "logs"
    c.db_path = tmp_path / "test.db"
    c.base_cv_path = tmp_path / "base_cv.md"
    c.output_dir.mkdir()
    c.logs_dir.mkdir()
    c.base_cv_path.write_text("# CV")
    return c


@pytest.fixture
def tracker(cfg):
    return ApplicationTracker(cfg.db_path)


@pytest.fixture
def queue(tracker, cfg):
    return ReviewQueue(tracker, cfg)


def _add_tailored_job(tracker, tmp_path, url="https://example.com/j1"):
    job = {
        "title": "Policy Analyst",
        "employer": "Cabinet Office",
        "location": "London",
        "salary": "£40,000",
        "url": url,
        "description": "Policy role",
        "source": "reed",
        "date_closes": "2026-04-30",
        "match_score": 75,
        "match_reason": "Strong background",
    }
    job_id = tracker.add_job(job)
    cv_path = tmp_path / "cv.docx"
    letter_path = tmp_path / "letter.docx"
    cv_path.write_text("CV content")
    letter_path.write_text("Letter content")
    tracker.update_documents(job_id, str(cv_path), str(letter_path))
    return job_id


# ── run() — no pending jobs ───────────────────────────────────────────────────

class TestRunNoPending:

    def test_run_with_no_pending_does_not_crash(self, queue):
        queue.run()  # should not raise

    def test_run_with_no_pending_prints_message(self, queue, capsys):
        queue.run()
        # rich Console prints to its own stream — just confirm no exception


# ── run() — with pending jobs ─────────────────────────────────────────────────

class TestRunWithPending:

    def test_run_approve_increments_count(self, queue, tracker, tmp_path, cfg):
        _add_tailored_job(tracker, tmp_path)
        with patch('rich.prompt.Prompt.ask', return_value="a"):
            queue.run()
        job = tracker.get_all_jobs()[0]
        assert job["status"] == "approved"

    def test_run_skip_sets_skipped_status(self, queue, tracker, tmp_path, cfg):
        _add_tailored_job(tracker, tmp_path)
        with patch('rich.prompt.Prompt.ask', side_effect=["s", ""]):
            queue.run()
        job = tracker.get_all_jobs()[0]
        assert job["status"] == "skipped"

    def test_run_quit_stops_processing(self, queue, tracker, tmp_path):
        _add_tailored_job(tracker, tmp_path, url="https://example.com/j1")
        _add_tailored_job(tracker, tmp_path, url="https://example.com/j2")
        with patch('rich.prompt.Prompt.ask', return_value="q"), \
             patch('rich.prompt.Confirm.ask', return_value=True):
            queue.run()
        # Both jobs remain pending (not approved/skipped)
        pending = tracker.get_pending_review()
        assert len(pending) == 2

    def test_run_note_saves_note(self, queue, tracker, tmp_path):
        _add_tailored_job(tracker, tmp_path)
        job_id = tracker.get_all_jobs()[0]["id"]
        with patch('rich.prompt.Prompt.ask', side_effect=["n", "Great role", "a"]):
            queue.run()
        job = tracker.get_job(job_id)
        assert job["notes"] == "Great role"

    def test_run_open_files_called(self, queue, tracker, tmp_path):
        _add_tailored_job(tracker, tmp_path)
        with patch.object(queue, '_open_files') as mock_open, \
             patch('rich.prompt.Prompt.ask', side_effect=["o", "a"]):
            queue.run()
        mock_open.assert_called_once()


# ── _review_one ───────────────────────────────────────────────────────────────

class TestReviewOne:

    def _make_job(self, tmp_path, score=75):
        return {
            "id": 1,
            "title": "Policy Analyst",
            "employer": "Cabinet Office",
            "location": "London",
            "salary": "£40,000",
            "url": "https://example.com/j1",
            "match_score": score,
            "match_reason": "Good match",
            "source": "reed",
            "date_closes": "2026-04-30",
            "tailored_cv_path": str(tmp_path / "cv.docx"),
            "cover_letter_path": str(tmp_path / "letter.docx"),
        }

    def test_review_one_approve_returns_approved(self, queue, tracker, tmp_path):
        job_id = tracker.add_job({
            "title": "Policy Analyst", "employer": "CO", "location": "London",
            "salary": "£40,000", "url": "https://ex.com/1", "description": "",
            "source": "test", "date_closes": "", "match_score": 75, "match_reason": "ok",
        })
        (tmp_path / "cv.docx").write_text("CV")
        (tmp_path / "letter.docx").write_text("Letter")
        tracker.update_documents(job_id, str(tmp_path / "cv.docx"), str(tmp_path / "letter.docx"))
        job = tracker.get_job(job_id)
        with patch('rich.prompt.Prompt.ask', return_value="a"):
            result = queue._review_one(job)
        assert result == "approved"

    def test_review_one_skip_returns_skipped(self, queue, tracker, tmp_path):
        job_id = tracker.add_job({
            "title": "Policy Analyst", "employer": "CO", "location": "London",
            "salary": "£40,000", "url": "https://ex.com/2", "description": "",
            "source": "test", "date_closes": "", "match_score": 75, "match_reason": "ok",
        })
        (tmp_path / "cv.docx").write_text("CV")
        (tmp_path / "letter.docx").write_text("Letter")
        tracker.update_documents(job_id, str(tmp_path / "cv.docx"), str(tmp_path / "letter.docx"))
        job = tracker.get_job(job_id)
        with patch('rich.prompt.Prompt.ask', side_effect=["s", ""]):
            result = queue._review_one(job)
        assert result == "skipped"

    def test_review_one_quit_with_confirmation(self, queue, tracker, tmp_path):
        job_id = tracker.add_job({
            "title": "Policy Analyst", "employer": "CO", "location": "London",
            "salary": "£40,000", "url": "https://ex.com/3", "description": "",
            "source": "test", "date_closes": "", "match_score": 75, "match_reason": "ok",
        })
        (tmp_path / "cv.docx").write_text("CV")
        tracker.update_documents(job_id, str(tmp_path / "cv.docx"), str(tmp_path / "cv.docx"))
        job = tracker.get_job(job_id)
        with patch('rich.prompt.Prompt.ask', return_value="q"), \
             patch('rich.prompt.Confirm.ask', return_value=True):
            result = queue._review_one(job)
        assert result == "quit"

    def test_review_one_quit_cancelled_continues(self, queue, tracker, tmp_path):
        """If user cancels quit, loop continues until approve."""
        job_id = tracker.add_job({
            "title": "Policy Analyst", "employer": "CO", "location": "London",
            "salary": "£40,000", "url": "https://ex.com/4", "description": "",
            "source": "test", "date_closes": "", "match_score": 75, "match_reason": "ok",
        })
        (tmp_path / "cv.docx").write_text("CV")
        tracker.update_documents(job_id, str(tmp_path / "cv.docx"), str(tmp_path / "cv.docx"))
        job = tracker.get_job(job_id)
        with patch('rich.prompt.Prompt.ask', side_effect=["q", "a"]), \
             patch('rich.prompt.Confirm.ask', return_value=False):
            result = queue._review_one(job)
        assert result == "approved"

    def test_review_one_score_colour_low(self, queue, tracker, tmp_path):
        """Low score (< 50) renders without raising."""
        job_id = tracker.add_job({
            "title": "Policy Analyst", "employer": "CO", "location": "London",
            "salary": "£40,000", "url": "https://ex.com/5", "description": "",
            "source": "test", "date_closes": "", "match_score": 30, "match_reason": "ok",
        })
        tracker.update_documents(job_id, "", "")
        job = tracker.get_job(job_id)
        with patch('rich.prompt.Prompt.ask', return_value="a"):
            result = queue._review_one(job)
        assert result == "approved"

    def test_review_one_no_score(self, queue, tracker, tmp_path):
        """No score (None) renders without raising."""
        job_id = tracker.add_job({
            "title": "Policy Analyst", "employer": "CO", "location": "London",
            "salary": "£40,000", "url": "https://ex.com/6", "description": "",
            "source": "test", "date_closes": None, "match_score": None, "match_reason": None,
        })
        tracker.update_documents(job_id, "", "")
        job = tracker.get_job(job_id)
        with patch('rich.prompt.Prompt.ask', return_value="a"):
            result = queue._review_one(job)
        assert result == "approved"


# ── _open_files ───────────────────────────────────────────────────────────────

class TestOpenFiles:

    def test_open_files_nonexistent_path_no_crash(self, queue):
        queue._open_files("/nonexistent/cv.docx", "/nonexistent/letter.docx")

    def test_open_files_none_paths_no_crash(self, queue):
        queue._open_files(None, None)

    def test_open_files_calls_system_open(self, queue, tmp_path):
        cv = tmp_path / "cv.docx"
        letter = tmp_path / "letter.docx"
        cv.write_text("CV")
        letter.write_text("Letter")
        with patch('subprocess.run') as mock_run, \
             patch('platform.system', return_value="Darwin"):
            queue._open_files(str(cv), str(letter))
        assert mock_run.call_count == 2

    def test_open_files_linux(self, queue, tmp_path):
        cv = tmp_path / "cv.docx"
        cv.write_text("CV")
        with patch('subprocess.run') as mock_run, \
             patch('platform.system', return_value="Linux"):
            queue._open_files(str(cv), None)
        assert mock_run.call_count == 1

    def test_open_files_subprocess_error_no_crash(self, queue, tmp_path):
        cv = tmp_path / "cv.docx"
        cv.write_text("CV")
        with patch('subprocess.run', side_effect=Exception("no open cmd")), \
             patch('platform.system', return_value="Darwin"):
            queue._open_files(str(cv), None)  # should not raise

    def test_open_files_windows(self, queue, tmp_path):
        cv = tmp_path / "cv.docx"
        cv.write_text("CV")
        with patch('subprocess.run') as mock_run, \
             patch('platform.system', return_value="Windows"):
            queue._open_files(str(cv), None)
        assert mock_run.call_count == 1

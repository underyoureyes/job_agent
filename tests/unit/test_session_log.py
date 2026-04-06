"""
tests/unit/test_session_log.py
===============================
Unit tests for session_log.py — SessionLog activity tracker and email sender.
"""

import pytest
from unittest.mock import patch, MagicMock
from session_log import SessionLog


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def log():
    return SessionLog()


def _scored_job(title="Policy Analyst", employer="Cabinet Office",
                score=75, status="scored"):
    return {"title": title, "employer": employer,
            "match_score": score, "status": status}


def _tailored_job(title="Policy Analyst", employer="Cabinet Office"):
    return {"title": title, "employer": employer}


def _applied_job(title="Policy Analyst", employer="Cabinet Office"):
    return {"title": title, "employer": employer}


def _smtp_config(notify="user@example.com", smtp_host="smtp.gmail.com",
                 smtp_user="user@gmail.com", smtp_password="secret",
                 smtp_from="user@gmail.com", smtp_port=587):
    cfg = MagicMock()
    cfg.notify_email = notify
    cfg.smtp_from = smtp_from
    cfg.smtp_host = smtp_host
    cfg.smtp_port = smtp_port
    cfg.smtp_user = smtp_user
    cfg.smtp_password = smtp_password
    return cfg


# ── Initialisation ─────────────────────────────────────────────────────────────

class TestInit:

    def test_scored_list_empty(self, log):
        assert log.scored == []

    def test_tailored_list_empty(self, log):
        assert log.tailored == []

    def test_applied_list_empty(self, log):
        assert log.applied == []

    def test_start_time_set(self, log):
        from datetime import datetime
        assert isinstance(log.start_time, datetime)


# ── record_scored ──────────────────────────────────────────────────────────────

class TestRecordScored:

    def test_records_single_job(self, log):
        log.record_scored([_scored_job()])
        assert len(log.scored) == 1

    def test_records_title_and_employer(self, log):
        log.record_scored([_scored_job(title="Analyst", employer="HMRC")])
        assert log.scored[0]["title"] == "Analyst"
        assert log.scored[0]["employer"] == "HMRC"

    def test_records_score(self, log):
        log.record_scored([_scored_job(score=80)])
        assert log.scored[0]["score"] == 80

    def test_passed_true_when_scored(self, log):
        log.record_scored([_scored_job(status="scored")])
        assert log.scored[0]["passed"] is True

    def test_passed_false_when_filtered(self, log):
        log.record_scored([_scored_job(status="filtered")])
        assert log.scored[0]["passed"] is False

    def test_records_multiple_jobs(self, log):
        log.record_scored([_scored_job(), _scored_job(title="Other", employer="DWP")])
        assert len(log.scored) == 2

    def test_empty_batch_no_error(self, log):
        log.record_scored([])
        assert log.scored == []


# ── record_tailored ────────────────────────────────────────────────────────────

class TestRecordTailored:

    def test_records_single_job(self, log):
        log.record_tailored([_tailored_job()])
        assert len(log.tailored) == 1

    def test_records_title_and_employer(self, log):
        log.record_tailored([_tailored_job(title="Researcher", employer="ONS")])
        assert log.tailored[0]["title"] == "Researcher"
        assert log.tailored[0]["employer"] == "ONS"

    def test_records_multiple(self, log):
        log.record_tailored([_tailored_job(), _tailored_job(title="Other")])
        assert len(log.tailored) == 2


# ── record_apply ───────────────────────────────────────────────────────────────

class TestRecordApply:

    def test_records_apply_attempt(self, log):
        log.record_apply(_applied_job(), "reed", True)
        assert len(log.applied) == 1

    def test_records_platform(self, log):
        log.record_apply(_applied_job(), "linkedin", False)
        assert log.applied[0]["platform"] == "linkedin"

    def test_records_success(self, log):
        log.record_apply(_applied_job(), "reed", True)
        assert log.applied[0]["success"] is True

    def test_records_failure(self, log):
        log.record_apply(_applied_job(), "reed", False)
        assert log.applied[0]["success"] is False


# ── has_activity ───────────────────────────────────────────────────────────────

class TestHasActivity:

    def test_false_when_empty(self, log):
        assert log.has_activity() is False

    def test_true_after_scoring(self, log):
        log.record_scored([_scored_job()])
        assert log.has_activity() is True

    def test_true_after_tailoring(self, log):
        log.record_tailored([_tailored_job()])
        assert log.has_activity() is True

    def test_true_after_applying(self, log):
        log.record_apply(_applied_job(), "reed", True)
        assert log.has_activity() is True


# ── estimated_cost ─────────────────────────────────────────────────────────────

class TestEstimatedCost:

    def test_zero_when_no_activity(self, log):
        assert log.estimated_cost() == 0.0

    def test_cost_per_scored_job(self, log):
        log.record_scored([_scored_job()] * 5)
        assert log.estimated_cost() == pytest.approx(0.05)

    def test_cost_per_tailored_job(self, log):
        log.record_tailored([_tailored_job()] * 2)
        assert log.estimated_cost() == pytest.approx(0.12)

    def test_combined_cost(self, log):
        log.record_scored([_scored_job()] * 3)
        log.record_tailored([_tailored_job()] * 1)
        assert log.estimated_cost() == pytest.approx(0.09)


# ── send_summary ───────────────────────────────────────────────────────────────

class TestSendSummary:

    def test_returns_false_when_no_smtp_config(self, log):
        cfg = MagicMock()
        cfg.notify_email = ""
        cfg.smtp_host = ""
        cfg.smtp_user = ""
        cfg.smtp_password = ""
        cfg.smtp_from = ""
        cfg.smtp_port = 587
        assert log.send_summary(cfg) is False

    def test_returns_false_when_notify_email_missing(self, log):
        cfg = _smtp_config(notify="")
        assert log.send_summary(cfg) is False

    def test_returns_false_when_smtp_host_missing(self, log):
        cfg = _smtp_config(smtp_host="")
        assert log.send_summary(cfg) is False

    def test_returns_true_on_successful_send(self, log):
        log.record_scored([_scored_job()])
        cfg = _smtp_config()
        mock_server = MagicMock()
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with patch('smtplib.SMTP', return_value=mock_smtp):
            result = log.send_summary(cfg)
        assert result is True

    def test_returns_false_on_smtp_error(self, log):
        cfg = _smtp_config()
        with patch('smtplib.SMTP', side_effect=Exception("connection refused")):
            result = log.send_summary(cfg)
        assert result is False

    def test_uses_smtp_from_as_from_addr(self, log):
        cfg = _smtp_config(smtp_from="from@domain.com")
        mock_server = MagicMock()
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with patch('smtplib.SMTP', return_value=mock_smtp):
            log.send_summary(cfg)
        mock_server.sendmail.assert_called_once()
        from_arg = mock_server.sendmail.call_args[0][0]
        assert from_arg == "from@domain.com"

    def test_falls_back_to_smtp_user_when_no_from(self, log):
        cfg = _smtp_config(smtp_from="", smtp_user="user@gmail.com")
        mock_server = MagicMock()
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with patch('smtplib.SMTP', return_value=mock_smtp):
            log.send_summary(cfg)
        from_arg = mock_server.sendmail.call_args[0][0]
        assert from_arg == "user@gmail.com"


# ── _build_plain ───────────────────────────────────────────────────────────────

class TestBuildPlain:

    def test_contains_header(self, log):
        plain = log._build_plain()
        assert "Job Agent Session Summary" in plain

    def test_contains_scored_section_when_scored(self, log):
        log.record_scored([_scored_job()])
        plain = log._build_plain()
        assert "JOBS SCORED" in plain

    def test_contains_tailored_section_when_tailored(self, log):
        log.record_tailored([_tailored_job()])
        plain = log._build_plain()
        assert "CVs / COVER LETTERS TAILORED" in plain

    def test_contains_applied_section_when_applied(self, log):
        log.record_apply(_applied_job(), "reed", True)
        plain = log._build_plain()
        assert "AUTO-APPLY ATTEMPTS" in plain

    def test_filtered_job_marked(self, log):
        log.record_scored([_scored_job(status="filtered")])
        plain = log._build_plain()
        assert "filtered" in plain

    def test_successful_apply_marked(self, log):
        log.record_apply(_applied_job(), "reed", True)
        plain = log._build_plain()
        assert "submitted" in plain

    def test_failed_apply_marked(self, log):
        log.record_apply(_applied_job(), "reed", False)
        plain = log._build_plain()
        assert "not submitted" in plain

    def test_no_sections_when_empty(self, log):
        plain = log._build_plain()
        assert "JOBS SCORED" not in plain
        assert "CVs / COVER LETTERS TAILORED" not in plain


# ── _build_html ────────────────────────────────────────────────────────────────

class TestBuildHtml:

    def test_returns_html_string(self, log):
        html = log._build_html()
        assert "<html>" in html

    def test_contains_session_header(self, log):
        html = log._build_html()
        assert "Job Agent" in html

    def test_contains_scored_rows_when_scored(self, log):
        log.record_scored([_scored_job(title="Policy Analyst")])
        html = log._build_html()
        assert "Policy Analyst" in html

    def test_contains_tailored_rows_when_tailored(self, log):
        log.record_tailored([_tailored_job(title="Researcher")])
        html = log._build_html()
        assert "Researcher" in html

    def test_contains_apply_rows_when_applied(self, log):
        log.record_apply(_applied_job(title="Data Analyst"), "linkedin", True)
        html = log._build_html()
        assert "Data Analyst" in html

    def test_cost_in_html(self, log):
        log.record_tailored([_tailored_job()])
        html = log._build_html()
        assert "£" in html

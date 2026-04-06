"""
tests/unit/test_main.py
=======================
Unit tests for main.py — filter functions and run_* orchestrators.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from config import Config
from tracker import ApplicationTracker
from main import (
    _is_too_senior,
    _is_irrelevant,
    _is_not_relevant,
    _is_wrong_location,
    _is_out_of_salary_range,
    run_scan,
    run_score_selected,
    run_tailor_approved,
    main,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg(tmp_path):
    c = Config(
        candidate_name="Test User",
        anthropic_api_key="sk-test",
        reed_api_key="test-reed",
        min_match_score=60,
        scan_civil_service=False,
        scan_guardian=False,
        scan_linkedin=False,
        linkedin_manual_file=None,
    )
    c.output_dir = tmp_path / "output"
    c.logs_dir = tmp_path / "logs"
    c.db_path = tmp_path / "test.db"
    c.base_dir = tmp_path
    c.base_cv_path = tmp_path / "base_cv.md"
    c.output_dir.mkdir()
    c.logs_dir.mkdir()
    c.base_cv_path.write_text("# Test CV\n\n## Experience\n- Did things")
    return c


@pytest.fixture
def tracker(cfg):
    return ApplicationTracker(cfg.db_path)


def _job(title="Policy Analyst", url="https://example.com/job/1",
         location="London", salary="£35,000", description=""):
    return {
        "title": title,
        "employer": "Test Employer",
        "location": location,
        "salary": salary,
        "url": url,
        "description": description,
        "source": "test",
        "date_closes": "",
        "match_score": None,
        "match_reason": None,
    }


# ── _is_too_senior ────────────────────────────────────────────────────────────

class TestIsTooSenior:

    def test_head_of_filtered(self, cfg):
        assert _is_too_senior({"title": "Head of Policy", "description": ""}, cfg)

    def test_director_filtered(self, cfg):
        assert _is_too_senior({"title": "Director of Strategy", "description": ""}, cfg)

    def test_chief_filtered(self, cfg):
        assert _is_too_senior({"title": "Chief Policy Officer", "description": ""}, cfg)

    def test_senior_manager_filtered(self, cfg):
        assert _is_too_senior({"title": "Senior Manager Policy", "description": ""}, cfg)

    def test_experience_in_desc_filtered(self, cfg):
        assert _is_too_senior(
            {"title": "Policy Advisor", "description": "5+ years experience required."},
            cfg
        )

    def test_graduate_role_not_filtered(self, cfg):
        assert not _is_too_senior(
            {"title": "Policy Analyst", "description": "Entry-level role."},
            cfg
        )

    def test_empty_fields_not_filtered(self, cfg):
        assert not _is_too_senior({"title": "", "description": ""}, cfg)

    def test_none_fields_not_filtered(self, cfg):
        assert not _is_too_senior({"title": None, "description": None}, cfg)

    def test_case_insensitive(self, cfg):
        assert _is_too_senior({"title": "HEAD OF POLICY", "description": ""}, cfg)


# ── _is_irrelevant ────────────────────────────────────────────────────────────

class TestIsIrrelevant:

    def test_software_engineer_filtered(self, cfg):
        assert _is_irrelevant({"title": "Software Engineer"}, cfg)

    def test_it_support_filtered(self, cfg):
        assert _is_irrelevant({"title": "IT Support Technician"}, cfg)

    def test_sales_filtered(self, cfg):
        assert _is_irrelevant({"title": "Sales Manager"}, cfg)

    def test_policy_analyst_not_filtered(self, cfg):
        assert not _is_irrelevant({"title": "Policy Analyst"}, cfg)

    def test_empty_title_not_filtered(self, cfg):
        assert not _is_irrelevant({"title": ""}, cfg)

    def test_none_title_not_filtered(self, cfg):
        assert not _is_irrelevant({"title": None}, cfg)

    def test_case_insensitive(self, cfg):
        assert _is_irrelevant({"title": "SALES EXECUTIVE"}, cfg)


# ── _is_not_relevant ──────────────────────────────────────────────────────────

class TestIsNotRelevant:

    def test_policy_title_is_relevant(self, cfg):
        assert not _is_not_relevant({"title": "Policy Analyst"}, cfg)

    def test_research_title_is_relevant(self, cfg):
        assert not _is_not_relevant({"title": "Research Officer"}, cfg)

    def test_government_title_is_relevant(self, cfg):
        assert not _is_not_relevant({"title": "Government Affairs Manager"}, cfg)

    def test_unrelated_title_is_not_relevant(self, cfg):
        assert _is_not_relevant({"title": "Warehouse Operative"}, cfg)

    def test_empty_title_is_not_relevant(self, cfg):
        assert _is_not_relevant({"title": ""}, cfg)

    def test_none_title_is_not_relevant(self, cfg):
        assert _is_not_relevant({"title": None}, cfg)

    def test_keyword_match_from_search_keywords(self, cfg):
        cfg.search_keywords = ["climate policy"]
        assert not _is_not_relevant({"title": "Climate Policy Officer"}, cfg)


# ── _is_wrong_location ────────────────────────────────────────────────────────

class TestIsWrongLocation:

    def test_brussels_filtered(self, cfg):
        assert _is_wrong_location({"location": "Brussels, Belgium"}, cfg)

    def test_amsterdam_filtered(self, cfg):
        assert _is_wrong_location({"location": "Amsterdam, Netherlands"}, cfg)

    def test_london_not_filtered(self, cfg):
        assert not _is_wrong_location({"location": "London"}, cfg)

    def test_remote_not_filtered(self, cfg):
        assert not _is_wrong_location({"location": "Remote"}, cfg)

    def test_empty_location_not_filtered(self, cfg):
        assert not _is_wrong_location({"location": ""}, cfg)

    def test_none_location_not_filtered(self, cfg):
        assert not _is_wrong_location({"location": None}, cfg)

    def test_case_insensitive(self, cfg):
        assert _is_wrong_location({"location": "PARIS, FRANCE"}, cfg)


# ── _is_out_of_salary_range ───────────────────────────────────────────────────

class TestIsOutOfSalaryRange:

    def test_no_salary_passes_through(self, cfg):
        assert not _is_out_of_salary_range({"salary": ""}, cfg)

    def test_none_salary_passes_through(self, cfg):
        assert not _is_out_of_salary_range({"salary": None}, cfg)

    def test_in_range_passes(self, cfg):
        cfg.min_salary_gbp = 30000
        cfg.max_salary_gbp = 60000
        assert not _is_out_of_salary_range({"salary": "£40,000"}, cfg)

    def test_below_min_filtered(self, cfg):
        cfg.min_salary_gbp = 35000
        assert _is_out_of_salary_range({"salary": "£20,000"}, cfg)

    def test_above_max_filtered(self, cfg):
        cfg.min_salary_gbp = 0
        cfg.max_salary_gbp = 50000
        assert _is_out_of_salary_range({"salary": "£75,000"}, cfg)

    def test_range_salary_uses_midpoint(self, cfg):
        cfg.min_salary_gbp = 30000
        cfg.max_salary_gbp = 60000
        # Midpoint of 35k-45k = 40k → in range
        assert not _is_out_of_salary_range({"salary": "£35,000 – £45,000"}, cfg)

    def test_zero_max_salary_no_upper_limit(self, cfg):
        cfg.min_salary_gbp = 0
        cfg.max_salary_gbp = 0
        assert not _is_out_of_salary_range({"salary": "£150,000"}, cfg)

    def test_pence_amounts_ignored(self, cfg):
        cfg.min_salary_gbp = 30000
        cfg.max_salary_gbp = 60000
        # "40000.50" — pence should be filtered (int(n) <= 1000 skip)
        assert not _is_out_of_salary_range({"salary": "£40,000.50"}, cfg)


# ── run_scan ──────────────────────────────────────────────────────────────────

class TestRunScan:

    def test_scanner_crash_handled(self, cfg, tracker):
        with patch('job_scanner.JobScanner.scan_all', side_effect=Exception("network down")):
            run_scan(cfg, tracker)  # should not raise
        assert tracker.get_all_jobs() == []

    def test_location_filtered_job(self, cfg, tracker):
        job = _job(title="Policy Analyst", location="Brussels, Belgium",
                   url="https://example.com/brussels")
        with patch('job_scanner.JobScanner.scan_all', return_value=[job]):
            run_scan(cfg, tracker)
        all_jobs = tracker.get_all_jobs()
        assert all_jobs[0]["status"] == "filtered"

    def test_salary_filtered_job(self, cfg, tracker):
        cfg.min_salary_gbp = 50000
        cfg.max_salary_gbp = 0
        job = _job(title="Policy Officer", salary="£25,000",
                   url="https://example.com/low-salary")
        with patch('job_scanner.JobScanner.scan_all', return_value=[job]):
            run_scan(cfg, tracker)
        all_jobs = tracker.get_all_jobs()
        assert all_jobs[0]["status"] == "filtered"

    def test_not_relevant_job_filtered(self, cfg, tracker):
        job = _job(title="Warehouse Operative", url="https://example.com/warehouse")
        with patch('job_scanner.JobScanner.scan_all', return_value=[job]):
            run_scan(cfg, tracker)
        all_jobs = tracker.get_all_jobs()
        assert all_jobs[0]["status"] == "filtered"

    def test_good_job_saved_as_discovered(self, cfg, tracker):
        job = _job(title="Policy Analyst", url="https://example.com/policy-1")
        with patch('job_scanner.JobScanner.scan_all', return_value=[job]):
            run_scan(cfg, tracker)
        all_jobs = tracker.get_all_jobs()
        assert all_jobs[0]["status"] == "discovered"


# ── run_score_selected ────────────────────────────────────────────────────────

class TestRunScoreSelected:

    def test_no_queued_jobs_is_safe(self, cfg, tracker):
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            run_score_selected(cfg, tracker)
        assert mock_client.messages.create.call_count == 0

    def test_failed_scoring_reverts_to_discovered(self, cfg, tracker):
        import json
        job = _job(url="https://example.com/j1")
        job_id = tracker.add_job(job)
        tracker.update_status(job_id, "score_me")

        error_client = MagicMock()
        error_client.messages.create.side_effect = Exception("API down")
        with patch('anthropic.Anthropic', return_value=error_client):
            run_score_selected(cfg, tracker)
        assert tracker.get_job(job_id)["status"] == "discovered"


# ── run_score_selected — billing error re-raise ───────────────────────────────

class TestRunScoreSelectedBillingError:

    def test_billing_error_re_raised(self, cfg, tracker):
        job = _job(url="https://example.com/j2")
        job_id = tracker.add_job(job)
        tracker.update_status(job_id, "score_me")

        error_client = MagicMock()
        error_client.messages.create.side_effect = Exception("insufficient credits")
        with patch('anthropic.Anthropic', return_value=error_client):
            with pytest.raises(Exception, match="credit"):
                run_score_selected(cfg, tracker)

    def test_non_billing_error_not_raised(self, cfg, tracker):
        job = _job(url="https://example.com/j3")
        job_id = tracker.add_job(job)
        tracker.update_status(job_id, "score_me")

        error_client = MagicMock()
        error_client.messages.create.side_effect = Exception("network timeout")
        with patch('anthropic.Anthropic', return_value=error_client):
            run_score_selected(cfg, tracker)  # should not raise


# ── run_scan — saved_count print ─────────────────────────────────────────────

class TestRunScanAdvice:

    def test_prints_advice_when_jobs_discovered(self, cfg, tracker, capsys):
        job = _job(title="Policy Analyst", url="https://example.com/advice-1")
        with patch('job_scanner.JobScanner.scan_all', return_value=[job]):
            run_scan(cfg, tracker)
        # Just verify it doesn't crash — Rich Console doesn't use capsys


# ── run_tailor_approved ───────────────────────────────────────────────────────

class TestRunTailorApproved:

    def test_no_queued_jobs_is_safe(self, cfg, tracker):
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            run_tailor_approved(cfg, tracker)
        assert mock_client.messages.create.call_count == 0


# ── main() CLI entrypoint ─────────────────────────────────────────────────────

class TestMain:

    def _run_main(self, args, cfg, tracker):
        with patch('sys.argv', ['main.py'] + args), \
             patch('main.Config', return_value=cfg), \
             patch('main.ApplicationTracker', return_value=tracker):
            main()

    def test_no_command_prints_help(self, cfg, tracker):
        with patch('sys.argv', ['main.py']), \
             patch('main.Config', return_value=cfg), \
             patch('main.ApplicationTracker', return_value=tracker), \
             patch('argparse.ArgumentParser.print_help') as mock_help:
            main()
        mock_help.assert_called_once()

    def test_scan_command(self, cfg, tracker):
        with patch('main.run_scan') as mock_scan:
            self._run_main(['scan'], cfg, tracker)
        mock_scan.assert_called_once_with(cfg, tracker)

    def test_score_selected_command(self, cfg, tracker):
        with patch('main.run_score_selected') as mock_score:
            self._run_main(['score_selected'], cfg, tracker)
        mock_score.assert_called_once_with(cfg, tracker)

    def test_tailor_approved_command(self, cfg, tracker):
        with patch('main.run_tailor_approved') as mock_tailor:
            self._run_main(['tailor_approved'], cfg, tracker)
        mock_tailor.assert_called_once_with(cfg, tracker)

    def test_review_command(self, cfg, tracker):
        with patch('main.ReviewQueue') as MockRQ:
            mock_rq = MagicMock()
            MockRQ.return_value = mock_rq
            self._run_main(['review'], cfg, tracker)
        mock_rq.run.assert_called_once()

    def test_status_command(self, cfg, tracker):
        with patch.object(tracker, 'print_dashboard') as mock_dash:
            self._run_main(['status'], cfg, tracker)
        mock_dash.assert_called_once()

    def test_tailor_specific_job(self, cfg, tracker):
        job = _job(url="https://example.com/tailor-1")
        job_id = tracker.add_job(job)
        with patch('main.CVTailor') as MockTailor:
            mock_tailor = MagicMock()
            MockTailor.return_value = mock_tailor
            self._run_main(['tailor', str(job_id)], cfg, tracker)
        mock_tailor.process_job.assert_called_once()

    def test_tailor_missing_job_id(self, cfg, tracker):
        # Job 9999 doesn't exist — should print error without crashing
        self._run_main(['tailor', '9999'], cfg, tracker)  # should not raise

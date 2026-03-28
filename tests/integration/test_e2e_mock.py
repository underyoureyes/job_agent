"""
tests/test_e2e_mock.py
======================
End-to-end pipeline tests using mocked Claude API responses.
No real API calls are made — zero cost to run.

v10 flow:
  Phase 1 — scan:           scan_all() → free filters → status = discovered
  Phase 2 — score:          run_score_selected() → score_only() → status = scored / filtered
  Phase 3 — tailor:         run_tailor_approved() → process_job() → status = tailored
  Phase 4 — review:         approve/skip → status = approved / skipped

Run from the job_agent directory:
    python -m pytest tests/ -v
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

#sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from tracker import ApplicationTracker
from cv_tailor import CVTailor
from main import run_scan, run_score_selected, run_tailor_approved, _is_too_senior


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_config(tmp_path):
    """Fully configured test Config using a temp directory."""
    cfg = Config(
        candidate_name="Finlay Castledine",
        candidate_email="finlay@test.com",
        candidate_phone="+44 7000 000000",
        candidate_linkedin="https://linkedin.com/in/finlay",
        anthropic_api_key="sk-ant-test-key",
        reed_api_key="test-reed-key",
        search_keywords=["public policy analyst"],
        search_location="London",
        min_match_score=55,
        max_tailored_per_scan=0,
        scan_civil_service=False,
        scan_guardian=False,
        scan_linkedin=False,
        linkedin_manual_file=None,
    )
    cfg.base_dir     = tmp_path
    cfg.output_dir   = tmp_path / "output"
    cfg.logs_dir     = tmp_path / "logs"
    cfg.db_path      = tmp_path / "test.db"
    cfg.base_cv_path = tmp_path / "base_cv.md"
    cfg.output_dir.mkdir()
    cfg.logs_dir.mkdir()
    cfg.base_cv_path.write_text(
        "# Finlay Castledine\n\n"
        "## Education\nMSc Public Policy, King's College London (2024-2025)\n\n"
        "## Experience\n### Policy Intern — HM Treasury (2023)\n"
        "- Analysed fiscal policy options for the 2023 Autumn Statement\n"
        "- Produced briefing notes for senior officials\n\n"
        "## Skills\nPolicy analysis, stakeholder engagement, quantitative research",
        encoding="utf-8"
    )
    return cfg


@pytest.fixture
def tracker(tmp_config):
    return ApplicationTracker(tmp_config.db_path)


@pytest.fixture
def policy_job():
    return {
        "title": "Policy Analyst",
        "employer": "Cabinet Office",
        "location": "London",
        "salary": "£35,000 – £45,000",
        "url": "https://example.gov.uk/jobs/policy-analyst-1",
        "description": "Analyse policy options across central government. "
                       "Produce high-quality briefings and policy papers. "
                       "Work with ministers and senior officials.",
        "source": "reed",
        "date_closes": "2026-04-30",
        "match_score": None,
        "match_reason": None,
    }


@pytest.fixture
def senior_job():
    return {
        "title": "Head of Policy",
        "employer": "Home Office",
        "location": "London",
        "salary": "£75,000 – £90,000",
        "url": "https://example.gov.uk/jobs/head-of-policy-1",
        "description": "Lead a team of 12 policy professionals. "
                       "Minimum 7 years experience in senior policy roles required.",
        "source": "reed",
        "date_closes": "2026-04-30",
        "match_score": None,
        "match_reason": None,
    }


@pytest.fixture
def it_job():
    return {
        "title": "IT Support Technician",
        "employer": "Some Tech Co",
        "location": "London",
        "salary": "£25,000",
        "url": "https://example.com/jobs/it-support-1",
        "description": "Fix computers, manage helpdesk tickets, install software.",
        "source": "reed",
        "date_closes": "",
        "match_score": None,
        "match_reason": None,
    }


# ── Mock Claude response builders ─────────────────────────────────────────────

def make_score_response(score: int, reason: str = "Good policy background"):
    return MagicMock(content=[MagicMock(text=json.dumps({
        "score": score,
        "reason": reason,
        "key_requirements": ["Policy analysis", "Written communication"],
        "candidate_strengths": ["MSc Public Policy", "Treasury internship"],
        "gaps": ["Limited senior experience"],
        "ats_keywords": ["policy analysis", "stakeholder engagement"],
    }))])


def make_cv_response():
    return MagicMock(content=[MagicMock(text=(
        "# Finlay Castledine\n\n"
        "**Email:** finlay@test.com\n\n"
        "## Education\n\n"
        "**MSc Public Policy** — King's College London *(2024–2025)*\n\n"
        "## Work Experience\n\n"
        "### Policy Intern — HM Treasury *(2023)*\n"
        "- Delivered fiscal policy analysis for the 2023 Autumn Statement\n"
    ))])


def make_letter_response():
    return MagicMock(content=[MagicMock(text=(
        "Dear Hiring Manager,\n\n"
        "I am writing to express my interest in the Policy Analyst role.\n\n"
        "Yours sincerely,\nFinlay Castledine"
    ))])


def make_mock_client(score: int = 72, reason: str = "Strong policy background"):
    """Mock that handles score → cv → letter call sequence."""
    client = MagicMock()
    client.messages.create.side_effect = (
        [make_score_response(score, reason), make_cv_response(), make_letter_response()] * 10
    )
    return client


def make_low_score_client(score: int = 20):
    """Mock that always returns a low score."""
    client = MagicMock()
    client.messages.create.return_value = make_score_response(score, "Not relevant")
    return client


# ── Helper: simulate UI selecting jobs to score ───────────────────────────────

def queue_discovered_for_scoring(tracker):
    """Simulate Finlay ticking all discovered jobs in the Screen Jobs UI."""
    for job in tracker.get_discovered_jobs():
        tracker.update_status(job["id"], "score_me", "Selected in test")


def queue_scored_for_tailoring(tracker):
    """Simulate Finlay ticking all scored jobs for tailoring."""
    for job in tracker.get_scored_jobs():
        tracker.update_status(job["id"], "tailoring", "Selected in test")


# ── Phase 1: Seniority filter tests ──────────────────────────────────────────

class TestSeniorityFilter:

    @pytest.fixture
    def tmp_config(self, tmp_path):
        cfg = Config()
        cfg.base_dir = tmp_path
        cfg.db_path  = tmp_path / "test.db"
        return cfg

    def test_head_of_filtered(self, tmp_config):
        assert _is_too_senior({"title": "Head of Policy", "description": ""}, tmp_config)

    def test_director_in_title_filtered(self, tmp_config):
        assert _is_too_senior({"title": "Director of Strategy", "description": ""}, tmp_config)

    def test_chief_in_title_filtered(self, tmp_config):
        assert _is_too_senior({"title": "Chief Policy Officer", "description": ""}, tmp_config)

    def test_senior_manager_filtered(self, tmp_config):
        assert _is_too_senior({"title": "Senior Manager - Policy", "description": ""}, tmp_config)

    def test_experience_in_description_filtered(self, tmp_config):
        assert _is_too_senior(
            {"title": "Policy Advisor", "description": "Minimum 7 years experience required."},
            tmp_config
        )

    def test_five_plus_years_filtered(self, tmp_config):
        assert _is_too_senior(
            {"title": "Policy Analyst", "description": "5+ years in public sector required."},
            tmp_config
        )

    def test_graduate_role_not_filtered(self, tmp_config):
        job = {"title": "Policy Analyst", "description": "Entry-level policy role. No experience required."}
        assert _is_too_senior(job, tmp_config) is False

    def test_analyst_not_filtered(self, tmp_config):
        job = {"title": "Policy Researcher", "description": "Graduate scheme open to recent graduates."}
        assert _is_too_senior(job, tmp_config) is False

    def test_empty_title_and_description(self, tmp_config):
        assert _is_too_senior({"title": "", "description": ""}, tmp_config) is False

    def test_none_fields_handled(self, tmp_config):
        assert _is_too_senior({"title": None, "description": None}, tmp_config) is False


# ── Phase 1: Scan tests (v10 — scan is FREE, no scoring) ─────────────────────

class TestPhase1Scan:

    def test_scan_saves_as_discovered(self, tmp_config, tracker, policy_job):
        """v10: scan saves jobs as 'discovered' — no scoring happens."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]), \
             patch('anthropic.Anthropic', return_value=make_mock_client()):
            run_scan(tmp_config, tracker)

        all_jobs = tracker.get_all_jobs()
        assert len(all_jobs) == 1
        assert all_jobs[0]["status"] == "discovered"
        assert all_jobs[0]["match_score"] is None  # not scored yet

    def test_scan_does_not_call_api(self, tmp_config, tracker, policy_job):
        """v10: scan must make ZERO API calls — completely free."""
        mock_client = make_mock_client()
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]), \
             patch('anthropic.Anthropic', return_value=mock_client):
            run_scan(tmp_config, tracker)

        assert mock_client.messages.create.call_count == 0

    def test_scan_does_not_tailor(self, tmp_config, tracker, policy_job):
        """Scan must NOT create any CV or cover letter files."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]), \
             patch('anthropic.Anthropic', return_value=make_mock_client()):
            run_scan(tmp_config, tracker)

        output_files = list(tmp_config.output_dir.rglob("*.*"))
        assert output_files == [], f"Unexpected files created during scan: {output_files}"

    def test_scan_auto_filters_senior_jobs(self, tmp_config, tracker, senior_job):
        """Senior jobs should be filtered without any API call."""
        mock_client = make_mock_client()
        with patch('job_scanner.JobScanner.scan_all', return_value=[senior_job]), \
             patch('anthropic.Anthropic', return_value=mock_client):
            run_scan(tmp_config, tracker)

        all_jobs = tracker.get_all_jobs()
        assert all_jobs[0]["status"] == "filtered"
        assert mock_client.messages.create.call_count == 0

    def test_scan_auto_filters_irrelevant_jobs(self, tmp_config, tracker, it_job):
        """Irrelevant title jobs should be filtered without any API call."""
        mock_client = make_mock_client()
        with patch('job_scanner.JobScanner.scan_all', return_value=[it_job]), \
             patch('anthropic.Anthropic', return_value=mock_client):
            run_scan(tmp_config, tracker)

        all_jobs = tracker.get_all_jobs()
        assert all_jobs[0]["status"] == "filtered"
        assert mock_client.messages.create.call_count == 0

    def test_scan_deduplicates_on_rerun(self, tmp_config, tracker, policy_job):
        """Running scan twice with the same jobs should not create duplicates."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]):
            run_scan(tmp_config, tracker)
            run_scan(tmp_config, tracker)

        assert len(tracker.get_all_jobs()) == 1

    def test_scan_second_run_skips_existing(self, tmp_config, tracker, policy_job):
        """On second scan, existing jobs should be skipped."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]):
            run_scan(tmp_config, tracker)
            count_after_first = len(tracker.get_all_jobs())
            run_scan(tmp_config, tracker)
            count_after_second = len(tracker.get_all_jobs())

        assert count_after_first == count_after_second == 1

    def test_scan_handles_mixed_jobs(self, tmp_config, tracker, policy_job, senior_job, it_job):
        """Mix of jobs: only policy job passes filters as discovered."""
        with patch('job_scanner.JobScanner.scan_all',
                   return_value=[policy_job, senior_job, it_job]):
            run_scan(tmp_config, tracker)

        all_jobs = tracker.get_all_jobs()
        assert len(all_jobs) == 3
        discovered = [j for j in all_jobs if j["status"] == "discovered"]
        filtered   = [j for j in all_jobs if j["status"] == "filtered"]
        assert len(discovered) == 1
        assert len(filtered) == 2

    def test_scan_handles_scanner_crash_gracefully(self, tmp_config, tracker):
        """If the scanner crashes entirely, run_scan should not raise."""
        with patch('job_scanner.JobScanner.scan_all', side_effect=Exception("Network down")):
            try:
                run_scan(tmp_config, tracker)
            except Exception as e:
                pytest.fail(f"run_scan raised unexpectedly: {e}")

    def test_discovered_jobs_appear_in_screening_queue(self, tmp_config, tracker, policy_job):
        """After scan, discovered jobs should appear in get_discovered_jobs()."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]):
            run_scan(tmp_config, tracker)

        discovered = tracker.get_discovered_jobs()
        assert len(discovered) == 1
        assert discovered[0]["title"] == "Policy Analyst"


# ── Phase 2: Score selected tests ────────────────────────────────────────────

class TestPhase2Score:

    def test_score_sets_status_to_scored(self, tmp_config, tracker, policy_job):
        """After scoring, job status should be 'scored' with a match score."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]):
            run_scan(tmp_config, tracker)
        queue_discovered_for_scoring(tracker)

        with patch('anthropic.Anthropic', return_value=make_mock_client(score=72)):
            run_score_selected(tmp_config, tracker)

        all_jobs = tracker.get_all_jobs()
        assert all_jobs[0]["status"] == "scored"
        assert all_jobs[0]["match_score"] == 72

    def test_score_calls_api_once_per_job(self, tmp_config, tracker, policy_job):
        """Scoring should make exactly 1 API call per job."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]):
            run_scan(tmp_config, tracker)
        queue_discovered_for_scoring(tracker)

        mock_client = make_mock_client(score=72)
        with patch('anthropic.Anthropic', return_value=mock_client):
            run_score_selected(tmp_config, tracker)

        assert mock_client.messages.create.call_count == 1

    def test_score_saves_match_reason(self, tmp_config, tracker, policy_job):
        """Match reason should be saved to the tracker after scoring."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]):
            run_scan(tmp_config, tracker)
        queue_discovered_for_scoring(tracker)

        with patch('anthropic.Anthropic',
                   return_value=make_mock_client(score=72, reason="Strong policy background")):
            run_score_selected(tmp_config, tracker)

        job = tracker.get_all_jobs()[0]
        assert job["match_reason"] is not None
        assert "policy" in job["match_reason"].lower()

    def test_score_filters_low_scoring_jobs(self, tmp_config, tracker, policy_job):
        """Jobs scoring below min_match_score should be filtered."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]):
            run_scan(tmp_config, tracker)
        queue_discovered_for_scoring(tracker)

        with patch('anthropic.Anthropic', return_value=make_low_score_client(score=15)):
            run_score_selected(tmp_config, tracker)

        all_jobs = tracker.get_all_jobs()
        assert all_jobs[0]["status"] == "filtered"

    def test_scored_jobs_appear_in_queue(self, tmp_config, tracker, policy_job):
        """After scoring, jobs should appear in get_scored_jobs()."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]):
            run_scan(tmp_config, tracker)
        queue_discovered_for_scoring(tracker)

        with patch('anthropic.Anthropic', return_value=make_mock_client(score=72)):
            run_score_selected(tmp_config, tracker)

        scored = tracker.get_scored_jobs()
        assert len(scored) == 1
        assert scored[0]["title"] == "Policy Analyst"

    def test_score_no_jobs_queued_is_safe(self, tmp_config, tracker):
        """Calling run_score_selected with nothing queued should not crash."""
        try:
            with patch('anthropic.Anthropic', return_value=make_mock_client()):
                run_score_selected(tmp_config, tracker)
        except Exception as e:
            pytest.fail(f"run_score_selected raised unexpectedly: {e}")


# ── Phase 3: Tailor tests ─────────────────────────────────────────────────────

class TestPhase3Tailor:

    @pytest.fixture(autouse=True)
    def mock_pdf_conversion(self):
        """Block all PDF conversion — no Word prompts during tests."""
        with patch('doc_generator.DocGenerator._try_weasyprint', return_value=False), \
             patch('doc_generator.DocGenerator._try_applescript_word', return_value=False), \
             patch('doc_generator.DocGenerator._try_libreoffice', return_value=False), \
             patch('doc_generator.DocGenerator._try_docx2pdf', return_value=False):
            yield

    def _scan_score_queue(self, tmp_config, tracker, jobs, score=72):
        """Helper: scan → score → queue for tailoring."""
        with patch('job_scanner.JobScanner.scan_all', return_value=jobs):
            run_scan(tmp_config, tracker)
        queue_discovered_for_scoring(tracker)
        with patch('anthropic.Anthropic', return_value=make_mock_client(score=score)):
            run_score_selected(tmp_config, tracker)
        queue_scored_for_tailoring(tracker)

    def test_tailor_creates_cv_and_letter_files(self, tmp_config, tracker, policy_job):
        """After tailoring, CV and cover letter files should exist."""
        self._scan_score_queue(tmp_config, tracker, [policy_job])

        with patch('anthropic.Anthropic', return_value=make_mock_client()):
            run_tailor_approved(tmp_config, tracker)

        job = tracker.get_all_jobs()[0]
        assert job["status"] == "tailored"
        assert job["tailored_cv_path"] is not None
        assert job["cover_letter_path"] is not None

    def test_tailor_makes_three_api_calls_per_job(self, tmp_config, tracker, policy_job):
        """Tailoring should make exactly 3 API calls: score + cv + letter."""
        self._scan_score_queue(tmp_config, tracker, [policy_job])

        mock_client = make_mock_client()
        with patch('anthropic.Anthropic', return_value=mock_client):
            run_tailor_approved(tmp_config, tracker)

        assert mock_client.messages.create.call_count == 3

    def test_tailor_only_processes_queued_jobs(self, tmp_config, tracker, policy_job, it_job):
        """Only jobs with status='tailoring' should be processed."""
        with patch('job_scanner.JobScanner.scan_all',
                   return_value=[policy_job, it_job]):
            run_scan(tmp_config, tracker)
        queue_discovered_for_scoring(tracker)
        with patch('anthropic.Anthropic', return_value=make_mock_client(score=72)):
            run_score_selected(tmp_config, tracker)

        # Only queue the policy job (it_job was filtered)
        scored = tracker.get_scored_jobs()
        if scored:
            tracker.update_status(scored[0]["id"], "tailoring", "Selected")

        mock_client = make_mock_client()
        with patch('anthropic.Anthropic', return_value=mock_client):
            run_tailor_approved(tmp_config, tracker)

        tailored = [j for j in tracker.get_all_jobs() if j["status"] == "tailored"]
        assert len(tailored) == 1

    def test_tailor_output_files_in_correct_dir(self, tmp_config, tracker, policy_job):
        """Output files should be inside tmp_config.output_dir."""
        self._scan_score_queue(tmp_config, tracker, [policy_job])

        with patch('anthropic.Anthropic', return_value=make_mock_client()):
            run_tailor_approved(tmp_config, tracker)

        output_files = list(tmp_config.output_dir.rglob("*.*"))
        assert len(output_files) >= 2

    def test_tailor_cv_contains_candidate_name(self, tmp_config, tracker, policy_job):
        """The generated CV markdown should contain the candidate's name."""
        self._scan_score_queue(tmp_config, tracker, [policy_job])

        with patch('anthropic.Anthropic', return_value=make_mock_client()):
            run_tailor_approved(tmp_config, tracker)

        md_files = list(tmp_config.output_dir.rglob("cv_*.md"))
        assert md_files, "No CV markdown file found"
        content = md_files[0].read_text()
        assert "Finlay" in content

    def test_tailor_no_jobs_queued_is_safe(self, tmp_config, tracker):
        """Calling run_tailor_approved with nothing queued should not crash."""
        try:
            with patch('anthropic.Anthropic', return_value=make_mock_client()):
                run_tailor_approved(tmp_config, tracker)
        except Exception as e:
            pytest.fail(f"run_tailor_approved raised unexpectedly: {e}")

    def test_tailor_api_error_raises_with_friendly_message(self, tmp_config, tracker, policy_job):
        """An API error during tailoring should raise with a plain-English message."""
        import anthropic as anthropic_lib
        self._scan_score_queue(tmp_config, tracker, [policy_job])

        error_client = MagicMock()
        error_client.messages.create.side_effect = anthropic_lib.APIError(
            message="billing: insufficient credits", request=MagicMock(), body={}
        )
        with patch('anthropic.Anthropic', return_value=error_client):
            with pytest.raises(Exception) as exc_info:
                run_tailor_approved(tmp_config, tracker)
        assert "credit" in str(exc_info.value).lower() or "anthropic" in str(exc_info.value).lower()

    def test_tailor_malformed_json_score_handled(self, tmp_config, tracker, policy_job):
        """Malformed JSON in score response should not crash tailoring."""
        self._scan_score_queue(tmp_config, tracker, [policy_job])

        bad_client = MagicMock()
        bad_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="not json")]
        )
        try:
            with patch('anthropic.Anthropic', return_value=bad_client):
                run_tailor_approved(tmp_config, tracker)
        except Exception as e:
            pytest.fail(f"run_tailor_approved raised unexpectedly: {e}")


# ── Phase 4: Review / status flow tests ──────────────────────────────────────

class TestPhase4ReviewAndStatus:

    @pytest.fixture(autouse=True)
    def mock_pdf_conversion(self):
        with patch('doc_generator.DocGenerator._try_weasyprint', return_value=False), \
             patch('doc_generator.DocGenerator._try_applescript_word', return_value=False), \
             patch('doc_generator.DocGenerator._try_libreoffice', return_value=False), \
             patch('doc_generator.DocGenerator._try_docx2pdf', return_value=False):
            yield

    def _full_pipeline(self, tmp_config, tracker, job):
        """Run full scan → score → tailor pipeline."""
        with patch('job_scanner.JobScanner.scan_all', return_value=[job]):
            run_scan(tmp_config, tracker)
        queue_discovered_for_scoring(tracker)
        with patch('anthropic.Anthropic', return_value=make_mock_client(score=72)):
            run_score_selected(tmp_config, tracker)
        queue_scored_for_tailoring(tracker)
        with patch('anthropic.Anthropic', return_value=make_mock_client()):
            run_tailor_approved(tmp_config, tracker)

    def test_tailored_jobs_in_review_queue(self, tmp_config, tracker, policy_job):
        """After tailoring, jobs should appear in get_pending_review()."""
        self._full_pipeline(tmp_config, tracker, policy_job)
        assert len(tracker.get_pending_review()) == 1

    def test_approve_moves_out_of_review_queue(self, tmp_config, tracker, policy_job):
        """Approving a job should remove it from the pending review queue."""
        self._full_pipeline(tmp_config, tracker, policy_job)
        job_id = tracker.get_all_jobs()[0]["id"]
        tracker.update_status(job_id, "approved")
        assert len(tracker.get_pending_review()) == 0

    def test_skip_moves_out_of_review_queue(self, tmp_config, tracker, policy_job):
        """Skipping a job should remove it from the pending review queue."""
        self._full_pipeline(tmp_config, tracker, policy_job)
        job_id = tracker.get_all_jobs()[0]["id"]
        tracker.update_status(job_id, "skipped")
        assert len(tracker.get_pending_review()) == 0

    def test_full_status_progression(self, tmp_config, tracker, policy_job):
        """Job flows: discovered → score_me → scored → tailoring → tailored → approved → submitted."""
        # After scan
        with patch('job_scanner.JobScanner.scan_all', return_value=[policy_job]):
            run_scan(tmp_config, tracker)
        assert tracker.get_all_jobs()[0]["status"] == "discovered"

        # After UI selection for scoring
        queue_discovered_for_scoring(tracker)
        assert tracker.get_all_jobs()[0]["status"] == "score_me"

        # After scoring
        with patch('anthropic.Anthropic', return_value=make_mock_client(score=72)):
            run_score_selected(tmp_config, tracker)
        assert tracker.get_all_jobs()[0]["status"] == "scored"

        # After UI selection for tailoring
        queue_scored_for_tailoring(tracker)
        assert tracker.get_all_jobs()[0]["status"] == "tailoring"

        # After tailoring
        with patch('anthropic.Anthropic', return_value=make_mock_client()):
            run_tailor_approved(tmp_config, tracker)
        assert tracker.get_all_jobs()[0]["status"] == "tailored"

        # After approval and submission
        job_id = tracker.get_all_jobs()[0]["id"]
        tracker.update_status(job_id, "approved")
        assert tracker.get_job(job_id)["status"] == "approved"
        tracker.update_status(job_id, "submitted")
        assert tracker.get_job(job_id)["status"] == "submitted"

    def test_all_events_logged(self, tmp_config, tracker, policy_job):
        """Every status change should produce a tracker event."""
        self._full_pipeline(tmp_config, tracker, policy_job)
        job_id = tracker.get_all_jobs()[0]["id"]
        events = tracker.get_events(job_id)
        event_names = [e["event"] for e in events]
        assert "discovered" in event_names
        assert "status → scored" in event_names
        assert any("tailor" in e.lower() for e in event_names)

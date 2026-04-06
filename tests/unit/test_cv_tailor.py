"""
tests/unit/test_cv_tailor.py
=============================
Unit tests for cv_tailor.py — CVTailor AI scoring and tailoring logic.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from config import Config
from tracker import ApplicationTracker
from cv_tailor import CVTailor


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg(tmp_path):
    c = Config(
        candidate_name="Alice Test",
        anthropic_api_key="sk-ant-test",
        min_match_score=60,
    )
    c.output_dir = tmp_path / "output"
    c.logs_dir = tmp_path / "logs"
    c.db_path = tmp_path / "test.db"
    c.base_dir = tmp_path
    c.base_cv_path = tmp_path / "base_cv.md"
    c.output_dir.mkdir()
    c.logs_dir.mkdir()
    c.base_cv_path.write_text(
        "# Alice Test\n\n"
        "## Education\nMSc Public Policy\n\n"
        "## Experience\n- Policy work at HM Treasury"
    )
    return c


@pytest.fixture
def tracker(cfg):
    return ApplicationTracker(cfg.db_path)


def _job(job_id: int = 1, url: str = "https://example.com/j1",
         title: str = "Policy Analyst", description: str = "Policy role") -> dict:
    return {
        "id": job_id,
        "title": title,
        "employer": "Cabinet Office",
        "location": "London",
        "salary": "£40,000",
        "url": url,
        "description": description,
        "source": "test",
        "date_closes": "2026-04-30",
        "match_score": None,
        "match_reason": None,
    }


def _make_score_response(score: int = 75):
    return MagicMock(content=[MagicMock(text=json.dumps({
        "score": score,
        "reason": "Good policy background",
        "key_requirements": ["Policy analysis"],
        "candidate_strengths": ["MSc Public Policy"],
        "gaps": [],
    }))])


def _make_cv_response():
    return MagicMock(content=[MagicMock(text="# Alice Test\n\n## Experience\n- Policy work")])


def _make_letter_response():
    return MagicMock(content=[MagicMock(text="Dear Hiring Manager,\n\nSincerely,\nAlice Test")])


# ── Initialisation ────────────────────────────────────────────────────────────

class TestCVTailorInit:

    def test_init_loads_base_cv(self, cfg):
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
        assert "Alice Test" in tailor.base_cv

    def test_init_missing_base_cv_warns(self, cfg):
        cfg.base_cv_path = cfg.base_dir / "nonexistent.md"
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
        assert tailor.base_cv == ""

    def test_init_loads_style_from_json(self, cfg):
        from document_processor import StyleFingerprint
        style = StyleFingerprint(body_font="Arial")
        (cfg.base_dir / "cv_style.json").write_text(style.to_json())
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
        assert tailor.cv_style.body_font == "Arial"

    def test_init_handles_corrupt_style_json(self, cfg):
        (cfg.base_dir / "cv_style.json").write_text("{invalid json}")
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
        # Should fall back to default style without raising
        from document_processor import StyleFingerprint
        assert isinstance(tailor.cv_style, StyleFingerprint)

    def test_init_missing_style_file_uses_default(self, cfg):
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
        from document_processor import StyleFingerprint
        assert isinstance(tailor.cv_style, StyleFingerprint)


# ── score_only ────────────────────────────────────────────────────────────────

class TestScoreOnly:

    def test_score_only_returns_tuple(self, cfg, tracker):
        job = _job()
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_score_response(72)
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            score, reason = tailor.score_only(job, tracker)

        assert score == 72
        assert isinstance(reason, str)

    def test_score_only_updates_tracker(self, cfg, tracker):
        job = _job()
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_score_response(80)
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            tailor.score_only(job, tracker)

        result = tracker.get_job(job_id)
        assert result["match_score"] == 80
        assert result["status"] == "scored"

    def test_score_only_fetches_description_if_missing(self, cfg, tracker):
        job = _job(description="")
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_score_response(65)
        with patch('anthropic.Anthropic', return_value=mock_client), \
             patch('job_scanner.JobScanner.fetch_job_description', return_value="Policy description"):
            tailor = CVTailor(cfg)
            score, reason = tailor.score_only(job, tracker)
        assert score == 65

    def test_score_only_malformed_json_fallback(self, cfg, tracker):
        job = _job()
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="not json at all")]
        )
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            score, reason = tailor.score_only(job, tracker)
        # Fallback: score=50
        assert score == 50


# ── process_job ───────────────────────────────────────────────────────────────

class TestProcessJob:

    def test_process_job_missing_base_cv_returns_false(self, cfg, tracker):
        cfg.base_cv_path = cfg.base_dir / "missing.md"
        job = _job()
        job_id = tracker.add_job(job)
        job["id"] = job_id
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            tailor.base_cv = ""
            result = tailor.process_job(job, tracker)
        assert result is False

    def test_process_job_low_score_returns_false(self, cfg, tracker):
        job = _job()
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_score_response(20)
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            result = tailor.process_job(job, tracker)
        assert result is False
        assert tracker.get_job(job_id)["status"] == "skipped"

    def test_process_job_success_returns_true(self, cfg, tracker):
        job = _job()
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_score_response(75),
            _make_cv_response(),
            _make_letter_response(),
        ]
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            result = tailor.process_job(job, tracker)
        assert result is True

    def test_process_job_sets_tailored_status(self, cfg, tracker):
        job = _job()
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_score_response(75),
            _make_cv_response(),
            _make_letter_response(),
        ]
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            tailor.process_job(job, tracker)
        assert tracker.get_job(job_id)["status"] == "tailored"

    def test_process_job_fetches_missing_description(self, cfg, tracker):
        job = _job(description="")
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_score_response(75),
            _make_cv_response(),
            _make_letter_response(),
        ]
        with patch('anthropic.Anthropic', return_value=mock_client), \
             patch('job_scanner.JobScanner.fetch_job_description', return_value="Fetched description"):
            tailor = CVTailor(cfg)
            result = tailor.process_job(job, tracker)
        assert result is True

    def test_process_job_api_error_raises(self, cfg, tracker):
        import anthropic as anthropic_lib
        job = _job()
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic_lib.APIError(
            message="Rate limit", request=MagicMock(), body={}
        )
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            with pytest.raises(RuntimeError):
                tailor.process_job(job, tracker)

    def test_process_job_generic_exception_raises(self, cfg, tracker):
        job = _job()
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Unexpected error")
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            with pytest.raises(Exception):
                tailor.process_job(job, tracker)

    def test_process_job_docx_failure_falls_back_to_md(self, cfg, tracker):
        job = _job()
        job_id = tracker.add_job(job)
        job["id"] = job_id

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_score_response(75),
            _make_cv_response(),
            _make_letter_response(),
        ]
        with patch('anthropic.Anthropic', return_value=mock_client), \
             patch('doc_generator.DocGenerator.generate_cv', side_effect=Exception("docx fail")):
            tailor = CVTailor(cfg)
            result = tailor.process_job(job, tracker)
        # Falls back to markdown — should still succeed
        assert result is True
        job_result = tracker.get_job(job_id)
        assert job_result["tailored_cv_path"].endswith(".md")


# ── _score_match ──────────────────────────────────────────────────────────────

class TestScoreMatch:

    def test_score_match_returns_dict(self, cfg):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_score_response(70)
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            result = tailor._score_match("Policy Analyst job description")
        assert "score" in result
        assert result["score"] == 70

    def test_score_match_handles_markdown_fences(self, cfg):
        raw_json = json.dumps({"score": 65, "reason": "Good"})
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=f"```json\n{raw_json}\n```")]
        )
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            result = tailor._score_match("job text")
        assert result["score"] == 65

    def test_score_match_fallback_on_bad_json(self, cfg):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="totally not json")]
        )
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
            result = tailor._score_match("job text")
        assert result["score"] == 50


# ── _slug ─────────────────────────────────────────────────────────────────────

class TestSlug:

    def test_slug_lowercases(self):
        assert CVTailor._slug("Policy Analyst") == "policy_analyst"

    def test_slug_replaces_spaces(self):
        slug = CVTailor._slug("head of policy")
        assert " " not in slug

    def test_slug_strips_special_chars(self):
        slug = CVTailor._slug("Policy & Research — Cabinet Office")
        assert "&" not in slug
        assert "—" not in slug

    def test_slug_max_length(self):
        assert len(CVTailor._slug("a" * 100)) <= 40

    def test_slug_empty_string(self):
        result = CVTailor._slug("")
        assert isinstance(result, str)


# ── _build_cv_header ──────────────────────────────────────────────────────────

class TestBuildCvHeader:

    def test_header_contains_title(self, cfg):
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
        score_data = {"reason": "Good match", "score": 75}
        header = tailor._build_cv_header("Policy Analyst", "Cabinet Office", 75, score_data)
        assert "Policy Analyst" in header
        assert "Cabinet Office" in header

    def test_header_contains_score(self, cfg):
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
        score_data = {"reason": "Strong background"}
        header = tailor._build_cv_header("Role", "Employer", 80, score_data)
        assert "80%" in header

    def test_header_contains_review_warning(self, cfg):
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            tailor = CVTailor(cfg)
        score_data = {}
        header = tailor._build_cv_header("Role", "Employer", 70, score_data)
        assert "REVIEW BEFORE SENDING" in header

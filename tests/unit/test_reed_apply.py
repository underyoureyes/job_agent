"""
tests/unit/test_reed_apply.py
==============================
Unit tests for reed_apply.py — Reed.co.uk auto-apply logic.
Playwright is mocked throughout; no browser is launched.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from config import Config
from reed_apply import (
    ReedApplyError,
    ReedExternalApplyError,
    ReedApplicant,
    _extract_text_from_docx,
    _save_debug_screenshot,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg():
    c = Config(
        candidate_name="Alice Smith",
        candidate_email="alice@example.com",
        candidate_phone="+44 7000 000000",
    )
    c.reed_email = "alice@example.com"
    c.reed_password = "secret"
    return c


def _job(tmp_path):
    cv = tmp_path / "cv.docx"
    cv.write_bytes(b"fake")
    letter = tmp_path / "letter.docx"
    letter.write_bytes(b"fake")
    return {
        "id": 1,
        "title": "Policy Analyst",
        "employer": "Cabinet Office",
        "url": "https://www.reed.co.uk/jobs/policy-analyst/12345",
        "tailored_cv_path": str(cv),
        "cover_letter_path": str(letter),
    }


def _mock_sync_playwright(page):
    """Return a (mock_module, mock_cm) pair for mocking sync_playwright."""
    mock_p = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = page

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_p)
    mock_cm.__exit__ = MagicMock(return_value=False)

    mock_module = MagicMock()
    mock_module.sync_playwright = MagicMock(return_value=mock_cm)
    return mock_module, mock_cm


# ── _extract_text_from_docx ────────────────────────────────────────────────────

class TestExtractTextFromDocx:

    def test_returns_text_from_docx(self, tmp_path):
        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text="First paragraph"),
            MagicMock(text="Second paragraph"),
        ]
        mock_docx = MagicMock()
        mock_docx.Document = MagicMock(return_value=mock_doc)
        with patch.dict(sys.modules, {'docx': mock_docx}):
            result = _extract_text_from_docx(str(tmp_path / "letter.docx"))
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_returns_empty_string_on_exception(self, tmp_path):
        mock_docx = MagicMock()
        mock_docx.Document = MagicMock(side_effect=Exception("bad file"))
        with patch.dict(sys.modules, {'docx': mock_docx}):
            result = _extract_text_from_docx(str(tmp_path / "missing.docx"))
        assert result == ""


# ── Exception classes ──────────────────────────────────────────────────────────

class TestExceptions:

    def test_reed_apply_error_is_exception(self):
        e = ReedApplyError("test")
        assert isinstance(e, Exception)

    def test_reed_external_apply_error_is_reed_apply_error(self):
        e = ReedExternalApplyError("external")
        assert isinstance(e, ReedApplyError)

    def test_reed_external_apply_error_message(self):
        e = ReedExternalApplyError("http://external.com")
        assert "http://external.com" in str(e)


# ── ReedApplicant init ─────────────────────────────────────────────────────────

class TestReedApplicantInit:

    def test_stores_config(self, cfg):
        applicant = ReedApplicant(cfg)
        assert applicant.config is cfg

    def test_default_not_headless(self, cfg):
        applicant = ReedApplicant(cfg)
        assert applicant.headless is False

    def test_headless_flag(self, cfg):
        applicant = ReedApplicant(cfg, headless=True)
        assert applicant.headless is True


# ── apply() — playwright not installed ────────────────────────────────────────

class TestApplyNoPlaywright:

    def test_raises_when_playwright_not_installed(self, cfg, tmp_path):
        job = _job(tmp_path)
        applicant = ReedApplicant(cfg)
        with patch.dict(sys.modules, {'playwright': None, 'playwright.sync_api': None}):
            with pytest.raises((ReedApplyError, Exception)):
                applicant.apply(job)


# ── apply() — error paths that follow playwright import ───────────────────────

class TestApplyErrorPaths:

    def test_raises_for_non_reed_url(self, cfg, tmp_path):
        job = _job(tmp_path)
        job["url"] = "https://www.linkedin.com/jobs/123"
        applicant = ReedApplicant(cfg)
        mock_module, _ = _mock_sync_playwright(MagicMock())
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}):
            with pytest.raises(ReedApplyError, match="Not a Reed URL"):
                applicant.apply(job)

    def test_raises_when_cv_missing(self, cfg, tmp_path):
        job = _job(tmp_path)
        job["tailored_cv_path"] = str(tmp_path / "nonexistent.docx")
        applicant = ReedApplicant(cfg)
        mock_module, _ = _mock_sync_playwright(MagicMock())
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}):
            with pytest.raises(ReedApplyError, match="not found"):
                applicant.apply(job)

    def test_raises_when_cv_path_none(self, cfg, tmp_path):
        job = _job(tmp_path)
        job["tailored_cv_path"] = None
        applicant = ReedApplicant(cfg)
        mock_module, _ = _mock_sync_playwright(MagicMock())
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}):
            with pytest.raises(ReedApplyError):
                applicant.apply(job)


# ── apply() — flow with mocked playwright ─────────────────────────────────────

class TestApplyFlow:

    def test_returns_false_when_run_returns_false(self, cfg, tmp_path):
        job = _job(tmp_path)
        applicant = ReedApplicant(cfg)
        page = MagicMock()
        mock_module, _ = _mock_sync_playwright(page)
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}), \
             patch.object(applicant, '_run', return_value=False), \
             patch('time.sleep'):
            result = applicant.apply(job)
        assert result is False

    def test_returns_true_when_run_succeeds(self, cfg, tmp_path):
        job = _job(tmp_path)
        applicant = ReedApplicant(cfg)
        page = MagicMock()
        mock_module, _ = _mock_sync_playwright(page)
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}), \
             patch.object(applicant, '_run', return_value=True), \
             patch('time.sleep'):
            result = applicant.apply(job)
        assert result is True

    def test_returns_false_on_exception_in_run(self, cfg, tmp_path):
        job = _job(tmp_path)
        applicant = ReedApplicant(cfg)
        page = MagicMock()
        mock_module, _ = _mock_sync_playwright(page)
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}), \
             patch.object(applicant, '_run', side_effect=Exception("page crashed")), \
             patch('time.sleep'):
            result = applicant.apply(job)
        assert result is False

    def test_reads_cover_letter_when_path_exists(self, cfg, tmp_path):
        job = _job(tmp_path)
        applicant = ReedApplicant(cfg)
        page = MagicMock()
        mock_module, _ = _mock_sync_playwright(page)
        mock_docx = MagicMock()
        mock_doc = MagicMock()
        mock_doc.paragraphs = [MagicMock(text="Cover letter content")]
        mock_docx.Document = MagicMock(return_value=mock_doc)
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module, 'docx': mock_docx}), \
             patch.object(applicant, '_run', return_value=True), \
             patch('time.sleep'):
            result = applicant.apply(job)
        assert result is True


# ── _is_login_page ─────────────────────────────────────────────────────────────

class TestIsLoginPage:

    def test_login_url_returns_true(self, cfg):
        page = MagicMock()
        page.url = "https://www.reed.co.uk/login?redirect=/apply"
        assert ReedApplicant(cfg)._is_login_page(page) is True

    def test_signin_url_returns_true(self, cfg):
        page = MagicMock()
        page.url = "https://www.reed.co.uk/signin"
        assert ReedApplicant(cfg)._is_login_page(page) is True

    def test_normal_url_returns_false(self, cfg):
        page = MagicMock()
        page.url = "https://www.reed.co.uk/jobs/apply/12345"
        assert ReedApplicant(cfg)._is_login_page(page) is False


# ── _find_element ──────────────────────────────────────────────────────────────

class TestFindElement:

    def test_returns_element_when_selector_matches(self, cfg):
        applicant = ReedApplicant(cfg)
        page = MagicMock()
        mock_el = MagicMock()
        page.wait_for_selector.return_value = mock_el
        result = applicant._find_element(page, "submit", timeout=1000)
        assert result is mock_el

    def test_returns_none_when_all_selectors_fail(self, cfg):
        applicant = ReedApplicant(cfg)
        page = MagicMock()
        page.wait_for_selector.side_effect = Exception("not found")
        result = applicant._find_element(page, "submit", timeout=100)
        assert result is None

    def test_tries_next_selector_on_failure(self, cfg):
        applicant = ReedApplicant(cfg)
        page = MagicMock()
        mock_el = MagicMock()
        page.wait_for_selector.side_effect = [Exception("fail"), mock_el]
        result = applicant._find_element(page, "submit", timeout=100)
        assert result is mock_el


# ── _try_fill ──────────────────────────────────────────────────────────────────

class TestTryFill:

    def test_fills_when_element_found(self, cfg):
        applicant = ReedApplicant(cfg)
        page = MagicMock()
        mock_el = MagicMock()
        with patch.object(applicant, '_find_element', return_value=mock_el):
            applicant._try_fill(page, "email", "alice@example.com")
        mock_el.fill.assert_called_once_with("alice@example.com")

    def test_no_fill_when_value_empty(self, cfg):
        applicant = ReedApplicant(cfg)
        page = MagicMock()
        mock_el = MagicMock()
        with patch.object(applicant, '_find_element', return_value=mock_el):
            applicant._try_fill(page, "email", "")
        mock_el.fill.assert_not_called()

    def test_no_fill_when_element_not_found(self, cfg):
        applicant = ReedApplicant(cfg)
        page = MagicMock()
        with patch.object(applicant, '_find_element', return_value=None):
            applicant._try_fill(page, "email", "alice@example.com")  # should not raise


# ── _first_name / _last_name ───────────────────────────────────────────────────

class TestNameHelpers:

    def test_first_name_single_word(self, cfg):
        cfg.candidate_name = "Alice"
        assert ReedApplicant(cfg)._first_name() == "Alice"

    def test_first_name_full_name(self, cfg):
        cfg.candidate_name = "Alice Smith"
        assert ReedApplicant(cfg)._first_name() == "Alice"

    def test_last_name_full_name(self, cfg):
        cfg.candidate_name = "Alice Smith"
        assert ReedApplicant(cfg)._last_name() == "Smith"

    def test_last_name_multiple_parts(self, cfg):
        cfg.candidate_name = "Alice Jane Smith"
        assert ReedApplicant(cfg)._last_name() == "Jane Smith"

    def test_first_name_empty_config(self, cfg):
        cfg.candidate_name = ""
        assert ReedApplicant(cfg)._first_name() == ""

    def test_last_name_single_word(self, cfg):
        cfg.candidate_name = "Alice"
        assert ReedApplicant(cfg)._last_name() == ""


# ── _save_debug_screenshot ─────────────────────────────────────────────────────

class TestSaveDebugScreenshot:

    def test_calls_page_screenshot(self):
        page = MagicMock()
        _save_debug_screenshot(page, "test_label")
        page.screenshot.assert_called_once()

    def test_no_raise_on_screenshot_exception(self):
        page = MagicMock()
        page.screenshot.side_effect = Exception("screenshot failed")
        _save_debug_screenshot(page, "label")  # should not raise

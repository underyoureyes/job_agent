"""
tests/unit/test_linkedin_apply.py
===================================
Unit tests for linkedin_apply.py — LinkedIn Easy Apply logic.
Playwright is mocked throughout; no browser is launched.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from config import Config
from linkedin_apply import (
    LinkedInApplyError,
    LinkedInApplicant,
    _extract_text_from_docx,
    _screenshot,
    LINKEDIN_LOGIN_URL,
    LINKEDIN_FEED_URL,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg():
    c = Config(
        candidate_name="Alice Smith",
        candidate_email="alice@example.com",
        candidate_phone="+44 7000 000000",
    )
    c.linkedin_apply_email = "alice@example.com"
    c.linkedin_apply_password = "secret"
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
        "url": "https://www.linkedin.com/jobs/view/12345",
        "tailored_cv_path": str(cv),
        "cover_letter_path": str(letter),
    }


def _mock_sync_playwright(page):
    """Return a mock playwright module where sync_playwright() yields page."""
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
    return mock_module


# ── _extract_text_from_docx ────────────────────────────────────────────────────

class TestExtractTextFromDocx:

    def test_returns_text_from_docx(self, tmp_path):
        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text="Para one"),
            MagicMock(text="Para two"),
        ]
        mock_docx = MagicMock()
        mock_docx.Document = MagicMock(return_value=mock_doc)
        with patch.dict(sys.modules, {'docx': mock_docx}):
            result = _extract_text_from_docx(str(tmp_path / "letter.docx"))
        assert "Para one" in result

    def test_returns_empty_on_exception(self, tmp_path):
        mock_docx = MagicMock()
        mock_docx.Document = MagicMock(side_effect=Exception("bad"))
        with patch.dict(sys.modules, {'docx': mock_docx}):
            result = _extract_text_from_docx(str(tmp_path / "x.docx"))
        assert result == ""


# ── _screenshot ────────────────────────────────────────────────────────────────

class TestScreenshot:

    def test_calls_page_screenshot(self):
        page = MagicMock()
        _screenshot(page, "label")
        page.screenshot.assert_called_once()

    def test_no_raise_on_exception(self):
        page = MagicMock()
        page.screenshot.side_effect = Exception("fail")
        _screenshot(page, "label")  # should not raise


# ── LinkedInApplicant init ─────────────────────────────────────────────────────

class TestLinkedInApplicantInit:

    def test_stores_config(self, cfg):
        a = LinkedInApplicant(cfg)
        assert a.config is cfg

    def test_reads_email_from_config(self, cfg):
        a = LinkedInApplicant(cfg)
        assert a._email == "alice@example.com"

    def test_reads_password_from_config(self, cfg):
        a = LinkedInApplicant(cfg)
        assert a._password == "secret"

    def test_default_not_headless(self, cfg):
        a = LinkedInApplicant(cfg)
        assert a.headless is False

    def test_headless_flag(self, cfg):
        a = LinkedInApplicant(cfg, headless=True)
        assert a.headless is True

    def test_missing_credentials_empty_strings(self):
        cfg = Config(candidate_name="Alice")
        a = LinkedInApplicant(cfg)
        assert a._email == ""
        assert a._password == ""


# ── apply() — playwright not installed ────────────────────────────────────────

class TestApplyNoPlaywright:

    def test_raises_when_playwright_not_installed(self, cfg, tmp_path):
        job = _job(tmp_path)
        a = LinkedInApplicant(cfg)
        with patch.dict(sys.modules, {'playwright': None, 'playwright.sync_api': None}):
            with pytest.raises((LinkedInApplyError, Exception)):
                a.apply(job)


# ── apply() — error paths after playwright import ─────────────────────────────

class TestApplyErrorPaths:

    def test_raises_when_credentials_missing(self, cfg, tmp_path):
        job = _job(tmp_path)
        a = LinkedInApplicant(cfg)
        a._email = ""
        a._password = ""
        mock_module = _mock_sync_playwright(MagicMock())
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}):
            with pytest.raises(LinkedInApplyError, match="credentials"):
                a.apply(job)

    def test_raises_for_non_linkedin_url(self, cfg, tmp_path):
        job = _job(tmp_path)
        job["url"] = "https://www.reed.co.uk/jobs/123"
        a = LinkedInApplicant(cfg)
        mock_module = _mock_sync_playwright(MagicMock())
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}):
            with pytest.raises(LinkedInApplyError, match="Not a LinkedIn URL"):
                a.apply(job)

    def test_raises_when_cv_missing(self, cfg, tmp_path):
        job = _job(tmp_path)
        job["tailored_cv_path"] = str(tmp_path / "missing.docx")
        a = LinkedInApplicant(cfg)
        mock_module = _mock_sync_playwright(MagicMock())
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}):
            with pytest.raises(LinkedInApplyError, match="not found"):
                a.apply(job)

    def test_raises_when_cv_path_none(self, cfg, tmp_path):
        job = _job(tmp_path)
        job["tailored_cv_path"] = None
        a = LinkedInApplicant(cfg)
        mock_module = _mock_sync_playwright(MagicMock())
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}):
            with pytest.raises(LinkedInApplyError):
                a.apply(job)


# ── apply() — flow with mocked playwright ─────────────────────────────────────

class TestApplyFlow:

    def test_returns_false_when_run_returns_false(self, cfg, tmp_path):
        job = _job(tmp_path)
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        mock_module = _mock_sync_playwright(page)
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}), \
             patch.object(a, '_run', return_value=False), \
             patch('time.sleep'):
            result = a.apply(job)
        assert result is False

    def test_returns_true_when_run_returns_true(self, cfg, tmp_path):
        job = _job(tmp_path)
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        mock_module = _mock_sync_playwright(page)
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}), \
             patch.object(a, '_run', return_value=True), \
             patch('time.sleep'):
            result = a.apply(job)
        assert result is True

    def test_returns_false_on_exception(self, cfg, tmp_path):
        job = _job(tmp_path)
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        mock_module = _mock_sync_playwright(page)
        with patch.dict(sys.modules, {'playwright.sync_api': mock_module}), \
             patch.object(a, '_run', side_effect=RuntimeError("crash")), \
             patch('time.sleep'):
            result = a.apply(job)
        assert result is False


# ── _first_name / _last_name ───────────────────────────────────────────────────

class TestNameHelpers:

    def test_first_name(self, cfg):
        cfg.candidate_name = "Alice Smith"
        assert LinkedInApplicant(cfg)._first_name() == "Alice"

    def test_last_name(self, cfg):
        cfg.candidate_name = "Alice Smith"
        assert LinkedInApplicant(cfg)._last_name() == "Smith"

    def test_last_name_multiple_parts(self, cfg):
        cfg.candidate_name = "Alice Jane Smith"
        assert LinkedInApplicant(cfg)._last_name() == "Jane Smith"

    def test_first_name_empty(self, cfg):
        cfg.candidate_name = ""
        assert LinkedInApplicant(cfg)._first_name() == ""

    def test_last_name_single_word(self, cfg):
        cfg.candidate_name = "Alice"
        assert LinkedInApplicant(cfg)._last_name() == ""


# ── _find_one ──────────────────────────────────────────────────────────────────

class TestFindOne:

    def test_returns_element_on_match(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        el = MagicMock()
        page.wait_for_selector.return_value = el
        result = a._find_one(page, ['button[type="submit"]'], timeout=500)
        assert result is el

    def test_returns_none_when_no_match(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        page.wait_for_selector.side_effect = Exception("not found")
        result = a._find_one(page, ['button[type="submit"]'], timeout=100)
        assert result is None

    def test_tries_all_selectors(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        el = MagicMock()
        page.wait_for_selector.side_effect = [Exception("miss"), el]
        result = a._find_one(page, ["#first", "#second"], timeout=100)
        assert result is el


# ── _fill_if_empty ─────────────────────────────────────────────────────────────

class TestFillIfEmpty:

    def test_fills_when_field_empty(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        el = MagicMock()
        el.input_value.return_value = ""
        page.wait_for_selector.return_value = el
        a._fill_if_empty(page, 'input[type="text"]', "Alice")
        el.fill.assert_called_once_with("Alice")

    def test_does_not_fill_when_already_filled(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        el = MagicMock()
        el.input_value.return_value = "already there"
        page.wait_for_selector.return_value = el
        a._fill_if_empty(page, 'input[type="text"]', "Alice")
        el.fill.assert_not_called()

    def test_does_not_fill_when_value_empty(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        a._fill_if_empty(page, 'input', "")
        page.wait_for_selector.assert_not_called()

    def test_no_raise_when_selector_fails(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        page.wait_for_selector.side_effect = Exception("timeout")
        a._fill_if_empty(page, 'input', "Alice")  # should not raise


# ── _has_unanswered_required ───────────────────────────────────────────────────

class TestHasUnansweredRequired:

    def test_returns_false_when_no_required_fields(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        page.query_selector_all.return_value = []
        assert a._has_unanswered_required(page) is False

    def test_returns_true_when_unanswered_field_present(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        field = MagicMock()
        field.get_attribute.return_value = "customQuestion"
        field.input_value.return_value = ""
        page.query_selector_all.return_value = [field]
        assert a._has_unanswered_required(page) is True

    def test_returns_false_when_all_fields_answered(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        field = MagicMock()
        field.get_attribute.return_value = "customQuestion"
        field.input_value.return_value = "some answer"
        page.query_selector_all.return_value = [field]
        assert a._has_unanswered_required(page) is False

    def test_returns_false_on_exception(self, cfg):
        a = LinkedInApplicant(cfg)
        page = MagicMock()
        page.query_selector_all.side_effect = Exception("page crash")
        assert a._has_unanswered_required(page) is False


# ── constants ──────────────────────────────────────────────────────────────────

class TestConstants:

    def test_login_url_is_linkedin(self):
        assert "linkedin.com" in LINKEDIN_LOGIN_URL

    def test_feed_url_is_linkedin(self):
        assert "linkedin.com" in LINKEDIN_FEED_URL

"""
tests/unit/test_document_processor.py
======================================
Unit tests for document_processor.py — StyleFingerprint and DocumentProcessor.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from document_processor import StyleFingerprint, DocumentProcessor


# ── StyleFingerprint ──────────────────────────────────────────────────────────

class TestStyleFingerprint:

    def test_default_body_font(self):
        sf = StyleFingerprint()
        assert sf.body_font == "Calibri"

    def test_default_heading_font(self):
        sf = StyleFingerprint()
        assert sf.heading_font == "Calibri"

    def test_default_sizes(self):
        sf = StyleFingerprint()
        assert sf.body_size_pt == 11.0
        assert sf.heading1_size_pt == 16.0
        assert sf.heading2_size_pt == 13.0

    def test_default_margins(self):
        sf = StyleFingerprint()
        assert sf.margin_top_cm == 2.54
        assert sf.margin_bottom_cm == 2.54
        assert sf.margin_left_cm == 2.54
        assert sf.margin_right_cm == 2.54

    def test_default_spacing(self):
        sf = StyleFingerprint()
        assert sf.paragraph_space_after_pt == 6.0

    def test_default_section_headings_empty_list(self):
        sf = StyleFingerprint()
        assert sf.section_headings == []

    def test_default_has_no_horizontal_rule(self):
        sf = StyleFingerprint()
        assert sf.has_horizontal_rule is False

    def test_default_heading_colour_none(self):
        sf = StyleFingerprint()
        assert sf.heading_colour is None

    def test_default_sign_off(self):
        sf = StyleFingerprint()
        assert sf.sign_off == "Yours sincerely"

    def test_default_uses_date_line(self):
        sf = StyleFingerprint()
        assert sf.uses_date_line is True

    def test_default_uses_salutation(self):
        sf = StyleFingerprint()
        assert sf.uses_salutation is True

    def test_custom_values(self):
        sf = StyleFingerprint(
            body_font="Arial",
            heading_font="Times New Roman",
            body_size_pt=10.0,
            heading1_size_pt=18.0,
            heading_colour="2E74B5",
        )
        assert sf.body_font == "Arial"
        assert sf.heading_font == "Times New Roman"
        assert sf.body_size_pt == 10.0
        assert sf.heading1_size_pt == 18.0
        assert sf.heading_colour == "2E74B5"


# ── StyleFingerprint serialisation ────────────────────────────────────────────

class TestStyleFingerprintSerialisation:

    def test_to_json_returns_string(self):
        sf = StyleFingerprint()
        result = sf.to_json()
        assert isinstance(result, str)

    def test_to_json_is_valid_json(self):
        sf = StyleFingerprint()
        data = json.loads(sf.to_json())
        assert "body_font" in data
        assert "heading_font" in data

    def test_from_json_round_trips(self):
        sf = StyleFingerprint(
            body_font="Arial",
            heading_colour="FF0000",
            margin_top_cm=1.5,
        )
        restored = StyleFingerprint.from_json(sf.to_json())
        assert restored.body_font == "Arial"
        assert restored.heading_colour == "FF0000"
        assert restored.margin_top_cm == 1.5

    def test_from_json_handles_defaults(self):
        sf = StyleFingerprint()
        restored = StyleFingerprint.from_json(sf.to_json())
        assert restored.body_font == sf.body_font
        assert restored.heading1_size_pt == sf.heading1_size_pt

    def test_from_json_section_headings_list(self):
        sf = StyleFingerprint(section_headings=["EDUCATION", "EXPERIENCE"])
        restored = StyleFingerprint.from_json(sf.to_json())
        assert restored.section_headings == ["EDUCATION", "EXPERIENCE"]


# ── DocumentProcessor static methods ──────────────────────────────────────────

class TestDocumentProcessorStatics:

    def test_detect_sign_off_yours_sincerely(self):
        text = "Thank you.\n\nYours sincerely,\nAlice"
        assert DocumentProcessor._detect_sign_off(text) == "Yours sincerely"

    def test_detect_sign_off_kind_regards(self):
        text = "Looking forward to hearing from you.\n\nKind regards,\nBob"
        assert DocumentProcessor._detect_sign_off(text) == "Kind regards"

    def test_detect_sign_off_best_regards(self):
        text = "I look forward to discussing further.\n\nBest regards,\nCarol"
        assert DocumentProcessor._detect_sign_off(text) == "Best regards"

    def test_detect_sign_off_yours_faithfully(self):
        text = "Yours faithfully,\nDave"
        assert DocumentProcessor._detect_sign_off(text) == "Yours faithfully"

    def test_detect_sign_off_sincerely(self):
        text = "Sincerely,\nEve"
        assert DocumentProcessor._detect_sign_off(text) == "Sincerely"

    def test_detect_sign_off_default_fallback(self):
        text = "Just a letter without a standard sign-off."
        assert DocumentProcessor._detect_sign_off(text) == "Yours sincerely"

    def test_detect_sign_off_case_insensitive(self):
        text = "YOURS SINCERELY, Frank"
        assert DocumentProcessor._detect_sign_off(text) == "Yours sincerely"

    def test_detect_salutation_dear_hiring(self):
        assert DocumentProcessor._detect_salutation("Dear Hiring Manager,") is True

    def test_detect_salutation_dear_sir(self):
        assert DocumentProcessor._detect_salutation("Dear Sir or Madam,") is True

    def test_detect_salutation_to_whom(self):
        assert DocumentProcessor._detect_salutation("To Whom It May Concern,") is True

    def test_detect_salutation_none(self):
        assert DocumentProcessor._detect_salutation("Hello there, I am applying.") is False

    def test_detect_salutation_case_insensitive(self):
        assert DocumentProcessor._detect_salutation("DEAR HIRING MANAGER") is True

    def test_most_common_returns_most_frequent(self):
        result = DocumentProcessor._most_common(["Arial", "Calibri", "Arial", "Arial"])
        assert result == "Arial"

    def test_most_common_empty_returns_none(self):
        assert DocumentProcessor._most_common([]) is None

    def test_most_common_single_item(self):
        assert DocumentProcessor._most_common(["Times"]) == "Times"

    def test_median_odd_list(self):
        assert DocumentProcessor._median([1, 3, 5]) == 3

    def test_median_even_list(self):
        assert DocumentProcessor._median([2, 4]) == 3.0

    def test_median_single_item(self):
        assert DocumentProcessor._median([7]) == 7

    def test_median_empty_returns_none(self):
        assert DocumentProcessor._median([]) is None

    def test_median_unsorted_input(self):
        assert DocumentProcessor._median([10, 2, 6]) == 6


# ── DocumentProcessor with mocked docx ────────────────────────────────────────

class TestDocumentProcessorExtract:

    def _make_mock_doc(self, paragraphs=None, sections=None):
        """Build a minimal mock Document object."""
        mock_doc = MagicMock()

        # Paragraphs
        mock_paragraphs = []
        for text, style_name in (paragraphs or [("Policy experience", "Normal")]):
            para = MagicMock()
            para.text = text
            para.style.name = style_name
            para.style.font.name = "Calibri"
            para.style.font.size = None
            para.runs = []
            para.paragraph_format.space_after = None
            para.paragraph_format.element = None
            mock_paragraphs.append(para)

        mock_doc.paragraphs = mock_paragraphs

        # Sections
        mock_section = MagicMock()
        mock_section.top_margin.cm = 2.54
        mock_section.bottom_margin.cm = 2.54
        mock_section.left_margin.cm = 2.54
        mock_section.right_margin.cm = 2.54
        mock_doc.sections = [mock_section]

        return mock_doc

    def test_extract_text_joins_paragraphs(self):
        proc = DocumentProcessor()
        mock_doc = self._make_mock_doc([
            ("First paragraph", "Normal"),
            ("Second paragraph", "Normal"),
        ])
        text = proc._extract_text(mock_doc)
        assert "First paragraph" in text
        assert "Second paragraph" in text

    def test_extract_text_skips_empty(self):
        proc = DocumentProcessor()
        mock_doc = self._make_mock_doc([
            ("", "Normal"),
            ("Content here", "Normal"),
        ])
        text = proc._extract_text(mock_doc)
        assert text == "Content here"

    def test_extract_style_returns_fingerprint(self):
        proc = DocumentProcessor()
        mock_doc = self._make_mock_doc()
        fp = proc._extract_style(mock_doc, document_type="cv")
        assert isinstance(fp, StyleFingerprint)

    def test_extract_style_uses_section_margins(self):
        proc = DocumentProcessor()
        mock_doc = self._make_mock_doc()
        mock_doc.sections[0].top_margin.cm = 1.5
        fp = proc._extract_style(mock_doc)
        assert fp.margin_top_cm == 1.5

    def test_extract_style_section_no_margin(self):
        """None margins should fall back to 2.54."""
        proc = DocumentProcessor()
        mock_doc = self._make_mock_doc()
        mock_doc.sections[0].top_margin = None
        fp = proc._extract_style(mock_doc)
        assert fp.margin_top_cm == 2.54

    def test_extract_cv_template_calls_document(self, tmp_path):
        proc = DocumentProcessor()
        mock_doc = self._make_mock_doc([("Test CV text", "Normal")])
        with patch('document_processor.Document', return_value=mock_doc):
            text, style = proc.extract_cv_template(tmp_path / "cv.docx")
        assert isinstance(text, str)
        assert isinstance(style, StyleFingerprint)

    def test_extract_cover_letter_template_detects_sign_off(self, tmp_path):
        proc = DocumentProcessor()
        mock_doc = self._make_mock_doc([
            ("Dear Hiring Manager,", "Normal"),
            ("I am applying for the role.", "Normal"),
            ("Yours sincerely,", "Normal"),
            ("Alice", "Normal"),
        ])
        with patch('document_processor.Document', return_value=mock_doc):
            text, style = proc.extract_cover_letter_template(tmp_path / "letter.docx")
        assert style.sign_off == "Yours sincerely"

    def test_extract_cv_template_with_heading_paragraphs(self, tmp_path):
        proc = DocumentProcessor()

        # Build a paragraph with a run that has font info
        para = MagicMock()
        para.text = "EDUCATION"
        para.style.name = "Heading 1"
        para.style.font.name = "Arial"
        para.style.font.size = None
        para.paragraph_format.space_after = None
        para.paragraph_format.element = None

        run = MagicMock()
        run.text = "EDUCATION"
        run.font.name = "Arial"
        run.font.size = None
        run.font.color.type = None
        para.runs = [run]

        mock_doc = MagicMock()
        mock_doc.paragraphs = [para]
        mock_doc.sections = [MagicMock()]
        mock_doc.sections[0].top_margin.cm = 2.54
        mock_doc.sections[0].bottom_margin.cm = 2.54
        mock_doc.sections[0].left_margin.cm = 2.54
        mock_doc.sections[0].right_margin.cm = 2.54

        with patch('document_processor.Document', return_value=mock_doc):
            text, style = proc.extract_cv_template(tmp_path / "cv.docx")
        assert isinstance(style, StyleFingerprint)

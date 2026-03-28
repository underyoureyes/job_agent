"""
tests/unit/test_doc_generator.py
=================================
Unit tests for doc_generator.py — DocGenerator markdown → docx/pdf converter.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from document_processor import StyleFingerprint
from doc_generator import DocGenerator


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def style():
    return StyleFingerprint(
        body_font="Calibri",
        heading_font="Calibri",
        body_size_pt=11.0,
        heading1_size_pt=16.0,
        heading2_size_pt=13.0,
        heading_colour="2E74B5",
        margin_top_cm=2.54,
        margin_bottom_cm=2.54,
        margin_left_cm=2.54,
        margin_right_cm=2.54,
        has_horizontal_rule=True,
        paragraph_space_after_pt=6.0,
    )


@pytest.fixture
def gen(style):
    return DocGenerator(style=style)


SAMPLE_CV = """# Alice Smith

**alice@example.com | 07700 900000 | London**

## Education

### MSc Public Policy — KCL (2024)
- Graduated with distinction

## Experience

### Policy Analyst — Cabinet Office (2023)
- Produced briefing notes for ministers
- **Key achievement**: Led cross-departmental review

---

Regular paragraph here.

> This is a blockquote to be skipped.

"""

SAMPLE_LETTER = """Dear Hiring Manager,

I am writing to express my interest in the Policy Analyst role.

Yours sincerely,
Alice Smith
"""


# ── Instantiation ──────────────────────────────────────────────────────────────

class TestInit:

    def test_init_with_style(self, style):
        gen = DocGenerator(style=style)
        assert gen.style is style

    def test_init_default_style(self):
        gen = DocGenerator()
        assert isinstance(gen.style, StyleFingerprint)

    def test_init_no_docx_raises(self):
        with patch('doc_generator.DOCX_AVAILABLE', False):
            with pytest.raises(RuntimeError, match="python-docx"):
                DocGenerator()


# ── generate_cv ───────────────────────────────────────────────────────────────

class TestGenerateCV:

    def test_generate_cv_creates_file(self, gen, tmp_path):
        output = tmp_path / "cv.docx"
        result = gen.generate_cv(SAMPLE_CV, output)
        assert result == output
        assert output.exists()

    def test_generate_cv_ats_mode_default(self, gen, tmp_path):
        output = tmp_path / "cv_ats.docx"
        gen.generate_cv(SAMPLE_CV, output, ats_mode=True)
        assert output.exists()

    def test_generate_cv_non_ats_mode(self, gen, tmp_path):
        output = tmp_path / "cv_noats.docx"
        gen.generate_cv(SAMPLE_CV, output, ats_mode=False)
        assert output.exists()

    def test_generate_cv_strips_html_comments(self, gen, tmp_path):
        md = "<!-- COMMENT -->\n# Alice Smith\n\n## Education"
        output = tmp_path / "cv.docx"
        gen.generate_cv(md, output)
        assert output.exists()

    def test_generate_cv_strips_blockquotes(self, gen, tmp_path):
        md = "> Warning: review before sending\n# Alice Smith"
        output = tmp_path / "cv.docx"
        gen.generate_cv(md, output)
        assert output.exists()

    def test_generate_cv_creates_parent_dir(self, gen, tmp_path):
        output = tmp_path / "subdir" / "cv.docx"
        gen.generate_cv(SAMPLE_CV, output)
        assert output.exists()


# ── generate_cover_letter ─────────────────────────────────────────────────────

class TestGenerateCoverLetter:

    def test_generate_cover_letter_creates_file(self, gen, tmp_path):
        output = tmp_path / "letter.docx"
        result = gen.generate_cover_letter(SAMPLE_LETTER, output)
        assert result == output
        assert output.exists()

    def test_generate_cover_letter_with_metadata(self, gen, tmp_path):
        output = tmp_path / "letter.docx"
        gen.generate_cover_letter(
            SAMPLE_LETTER, output,
            candidate_name="Alice Smith",
            job_title="Policy Analyst",
            employer="Cabinet Office",
        )
        assert output.exists()

    def test_generate_cover_letter_non_ats(self, gen, tmp_path):
        output = tmp_path / "letter.docx"
        gen.generate_cover_letter(SAMPLE_LETTER, output, ats_mode=False)
        assert output.exists()


# ── _render_markdown ──────────────────────────────────────────────────────────

class TestRenderMarkdown:

    def test_render_h1(self, gen, tmp_path):
        output = tmp_path / "h1.docx"
        gen.generate_cv("# Main Heading", output)
        assert output.exists()

    def test_render_h2(self, gen, tmp_path):
        output = tmp_path / "h2.docx"
        gen.generate_cv("## Section Heading", output)
        assert output.exists()

    def test_render_h3(self, gen, tmp_path):
        output = tmp_path / "h3.docx"
        gen.generate_cv("### Role Title", output)
        assert output.exists()

    def test_render_bullet_ats_mode(self, gen, tmp_path):
        output = tmp_path / "bullet.docx"
        gen.generate_cv("- A bullet point\n* Another bullet", output, ats_mode=True)
        assert output.exists()

    def test_render_bullet_non_ats_mode(self, gen, tmp_path):
        output = tmp_path / "bullet_noats.docx"
        gen.generate_cv("- A bullet point", output, ats_mode=False)
        assert output.exists()

    def test_render_horizontal_rule_ats(self, gen, tmp_path):
        output = tmp_path / "hr_ats.docx"
        gen.generate_cv("---\n***\n___", output, ats_mode=True)
        assert output.exists()

    def test_render_horizontal_rule_non_ats(self, gen, tmp_path):
        output = tmp_path / "hr_noats.docx"
        gen.generate_cv("---", output, ats_mode=False)
        assert output.exists()

    def test_render_contact_line_ats(self, gen, tmp_path):
        output = tmp_path / "contact_ats.docx"
        gen.generate_cv("**Email: alice@test.com | Phone: 07700**", output, ats_mode=True)
        assert output.exists()

    def test_render_contact_line_non_ats(self, gen, tmp_path):
        output = tmp_path / "contact_noats.docx"
        gen.generate_cv("**Email: alice@test.com | Phone: 07700**", output, ats_mode=False)
        assert output.exists()

    def test_render_empty_line_spacer(self, gen, tmp_path):
        output = tmp_path / "spacer.docx"
        gen.generate_cv("First line\n\nSecond line", output)
        assert output.exists()

    def test_render_plain_body(self, gen, tmp_path):
        output = tmp_path / "body.docx"
        gen.generate_cv("This is a regular paragraph.", output)
        assert output.exists()

    def test_render_blockquote_skipped(self, gen, tmp_path):
        output = tmp_path / "blockquote.docx"
        gen.generate_cv("> This should be skipped", output)
        assert output.exists()


# ── _add_heading ──────────────────────────────────────────────────────────────

class TestAddHeading:

    def test_heading_with_valid_colour(self, tmp_path):
        style = StyleFingerprint(heading_colour="2E74B5")
        gen = DocGenerator(style=style)
        output = tmp_path / "colour.docx"
        gen.generate_cv("# Coloured Heading", output)
        assert output.exists()

    def test_heading_with_invalid_colour_no_crash(self, tmp_path):
        style = StyleFingerprint(heading_colour="ZZZZZZ")
        gen = DocGenerator(style=style)
        output = tmp_path / "bad_colour.docx"
        gen.generate_cv("# Heading", output)
        assert output.exists()

    def test_h2_with_colour(self, tmp_path):
        style = StyleFingerprint(heading_colour="FF0000")
        gen = DocGenerator(style=style)
        output = tmp_path / "h2_colour.docx"
        gen.generate_cv("## Section", output)
        assert output.exists()

    def test_h2_no_colour(self, tmp_path):
        style = StyleFingerprint(heading_colour=None)
        gen = DocGenerator(style=style)
        output = tmp_path / "h2_nocol.docx"
        gen.generate_cv("## Section", output)
        assert output.exists()


# ── _add_section_heading ──────────────────────────────────────────────────────

class TestAddSectionHeading:

    def test_section_heading_with_rule(self, tmp_path):
        style = StyleFingerprint(has_horizontal_rule=True)
        gen = DocGenerator(style=style)
        output = tmp_path / "sec_rule.docx"
        gen.generate_cv("## EDUCATION", output)
        assert output.exists()

    def test_section_heading_without_rule(self, tmp_path):
        style = StyleFingerprint(has_horizontal_rule=False)
        gen = DocGenerator(style=style)
        output = tmp_path / "sec_norule.docx"
        gen.generate_cv("## Education", output)
        assert output.exists()

    def test_section_heading_uppercase_preserved(self, tmp_path):
        style = StyleFingerprint()
        gen = DocGenerator(style=style)
        output = tmp_path / "sec_upper.docx"
        gen.generate_cv("## EXPERIENCE", output)
        assert output.exists()


# ── _add_body ─────────────────────────────────────────────────────────────────

class TestAddBody:

    def test_add_body_empty_text_no_crash(self, gen, tmp_path):
        output = tmp_path / "empty.docx"
        gen.generate_cv("   ", output)
        assert output.exists()


# ── _add_inline_markdown ──────────────────────────────────────────────────────

class TestAddInlineMarkdown:

    def test_bold_text(self, gen, tmp_path):
        output = tmp_path / "bold.docx"
        gen.generate_cv("This is **bold** text.", output)
        assert output.exists()

    def test_italic_text(self, gen, tmp_path):
        output = tmp_path / "italic.docx"
        gen.generate_cv("This is *italic* text.", output)
        assert output.exists()

    def test_mixed_inline(self, gen, tmp_path):
        output = tmp_path / "mixed.docx"
        gen.generate_cv("**Bold** and *italic* and plain.", output)
        assert output.exists()


# ── _inline_md static helper ──────────────────────────────────────────────────

class TestInlineMd:

    def test_bold_converted(self):
        result = DocGenerator._inline_md("**hello**")
        assert "<strong>hello</strong>" in result

    def test_italic_converted(self):
        result = DocGenerator._inline_md("*world*")
        assert "<em>world</em>" in result

    def test_plain_text_unchanged(self):
        result = DocGenerator._inline_md("plain text")
        assert result == "plain text"

    def test_mixed_conversion(self):
        result = DocGenerator._inline_md("**Bold** and *italic*")
        assert "<strong>Bold</strong>" in result
        assert "<em>italic</em>" in result


# ── _markdown_to_html ─────────────────────────────────────────────────────────

class TestMarkdownToHtml:

    def test_h1_converted(self, gen):
        html = gen._markdown_to_html("# Heading One")
        assert "<h1>" in html
        assert "Heading One" in html

    def test_h2_converted(self, gen):
        html = gen._markdown_to_html("## Section")
        assert "<h2>" in html

    def test_h3_converted(self, gen):
        html = gen._markdown_to_html("### Role")
        assert "<h3>" in html

    def test_bullet_converted(self, gen):
        html = gen._markdown_to_html("- Bullet point")
        assert "<li>" in html

    def test_star_bullet_converted(self, gen):
        html = gen._markdown_to_html("* Star bullet")
        assert "<li>" in html

    def test_horizontal_rule(self, gen):
        html = gen._markdown_to_html("---")
        assert "<hr>" in html

    def test_triple_star_rule(self, gen):
        html = gen._markdown_to_html("***")
        assert "<hr>" in html

    def test_paragraph(self, gen):
        html = gen._markdown_to_html("A regular paragraph.")
        assert "<p>" in html

    def test_empty_line_skipped(self, gen):
        html = gen._markdown_to_html("\n\n")
        assert "<html>" in html
        assert "<p></p>" not in html

    def test_full_document(self, gen):
        md = "# Name\n\n## Education\n\n- Degree\n\n---"
        html = gen._markdown_to_html(md)
        assert "<h1>" in html
        assert "<h2>" in html
        assert "<li>" in html


# ── _build_pdf_css ────────────────────────────────────────────────────────────

class TestBuildPdfCss:

    def test_returns_string(self, gen):
        css = gen._build_pdf_css()
        assert isinstance(css, str)

    def test_contains_page_rule(self, gen):
        css = gen._build_pdf_css()
        assert "@page" in css

    def test_contains_body_rule(self, gen):
        css = gen._build_pdf_css()
        assert "body" in css

    def test_contains_heading_colour(self):
        style = StyleFingerprint(heading_colour="FF0000")
        gen = DocGenerator(style=style)
        css = gen._build_pdf_css()
        assert "FF0000" in css

    def test_no_heading_colour_uses_default(self):
        style = StyleFingerprint(heading_colour=None)
        gen = DocGenerator(style=style)
        css = gen._build_pdf_css()
        assert "#1a1a1a" in css


# ── convert_to_pdf ────────────────────────────────────────────────────────────

class TestConvertToPdf:

    def test_convert_returns_none_when_all_fail(self, gen, tmp_path):
        docx_path = tmp_path / "cv.docx"
        docx_path.write_bytes(b"fake docx")
        with patch.object(gen, '_try_weasyprint', return_value=False), \
             patch.object(gen, '_try_libreoffice', return_value=False):
            result = gen.convert_to_pdf(docx_path)
        assert result is None

    def test_convert_returns_path_when_weasyprint_succeeds(self, gen, tmp_path):
        docx_path = tmp_path / "cv.docx"
        docx_path.write_bytes(b"fake docx")
        with patch.object(gen, '_try_weasyprint', return_value=True):
            result = gen.convert_to_pdf(docx_path)
        assert result == docx_path.with_suffix(".pdf")

    def test_convert_falls_back_to_libreoffice(self, gen, tmp_path):
        docx_path = tmp_path / "cv.docx"
        docx_path.write_bytes(b"fake docx")
        with patch.object(gen, '_try_weasyprint', return_value=False), \
             patch.object(gen, '_try_libreoffice', return_value=True):
            result = gen.convert_to_pdf(docx_path)
        assert result == docx_path.with_suffix(".pdf")


# ── _try_libreoffice (static) ─────────────────────────────────────────────────

class TestTryLibreoffice:

    def test_returns_false_if_no_soffice(self, tmp_path):
        docx_path = tmp_path / "cv.docx"
        docx_path.write_bytes(b"fake")
        with patch('shutil.which', return_value=None):
            result = DocGenerator._try_libreoffice(docx_path, tmp_path / "cv.pdf")
        assert result is False

    def test_returns_false_if_subprocess_fails(self, tmp_path):
        docx_path = tmp_path / "cv.docx"
        docx_path.write_bytes(b"fake")
        with patch('shutil.which', return_value="/usr/bin/soffice"), \
             patch('subprocess.run', side_effect=Exception("soffice error")):
            result = DocGenerator._try_libreoffice(docx_path, tmp_path / "cv.pdf")
        assert result is False

    def test_returns_false_if_pdf_not_created(self, tmp_path):
        docx_path = tmp_path / "cv.docx"
        docx_path.write_bytes(b"fake")
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch('shutil.which', return_value="/usr/bin/soffice"), \
             patch('subprocess.run', return_value=mock_result):
            # pdf_path won't exist since subprocess is mocked
            result = DocGenerator._try_libreoffice(docx_path, tmp_path / "cv.pdf")
        assert result is False


# ── _try_applescript_word (static) ────────────────────────────────────────────

class TestTryApplescriptWord:

    def test_returns_false_on_exception(self, tmp_path):
        docx_path = tmp_path / "cv.docx"
        docx_path.write_bytes(b"fake")
        with patch('subprocess.run', side_effect=Exception("no osascript")):
            result = DocGenerator._try_applescript_word(docx_path, tmp_path / "cv.pdf")
        assert result is False

    def test_returns_false_when_returncode_nonzero(self, tmp_path):
        docx_path = tmp_path / "cv.docx"
        docx_path.write_bytes(b"fake")
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch('subprocess.run', return_value=mock_result):
            result = DocGenerator._try_applescript_word(docx_path, tmp_path / "cv.pdf")
        assert result is False


# ── _try_weasyprint ────────────────────────────────────────────────────────────

class TestTryWeasyprint:

    def test_returns_false_if_no_md_file(self, gen, tmp_path):
        docx_path = tmp_path / "cv.docx"
        docx_path.write_bytes(b"fake")
        # No .md file alongside docx → returns False
        result = gen._try_weasyprint(docx_path, tmp_path / "cv.pdf")
        assert result is False

    def test_returns_false_if_import_error(self, gen, tmp_path):
        docx_path = tmp_path / "cv.docx"
        md_path = tmp_path / "cv.md"
        docx_path.write_bytes(b"fake")
        md_path.write_text("# CV")
        with patch('builtins.__import__', side_effect=ImportError("no weasyprint")):
            result = gen._try_weasyprint(docx_path, tmp_path / "cv.pdf")
        assert result is False

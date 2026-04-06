"""
tests/unit/test_doc_generator.py
=================================
Unit tests for doc_generator.py — DocGenerator markdown → docx converter.
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


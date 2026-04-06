"""
tests/unit/test_log_capture.py
================================
Unit tests for log_capture.py — stdout capture for WebSocket log streaming.
"""

import io
import pytest
from log_capture import _strip_ansi, _LogCapture


# ── _strip_ansi ────────────────────────────────────────────────────────────────

class TestStripAnsi:

    def test_removes_colour_codes(self):
        assert _strip_ansi("\x1b[32mGreen\x1b[0m") == "Green"

    def test_removes_rich_markup(self):
        assert _strip_ansi("[bold]text[/bold]") == "text"

    def test_plain_text_unchanged(self):
        assert _strip_ansi("just plain text") == "just plain text"

    def test_empty_string(self):
        assert _strip_ansi("") == ""

    def test_mixed_ansi_and_text(self):
        result = _strip_ansi("\x1b[1mBold\x1b[0m normal")
        assert "Bold" in result
        assert "normal" in result
        assert "\x1b" not in result

    def test_removes_known_cursor_codes(self):
        # G and H are in the matched set
        result = _strip_ansi("\x1b[2Gsome text")
        assert "\x1b" not in result


# ── _LogCapture ────────────────────────────────────────────────────────────────

class TestLogCaptureInit:

    def test_lines_empty_on_init(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        assert cap.lines == []

    def test_real_stdout_stored(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        assert cap._real is real

    def test_on_line_callback_optional(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        assert cap._on_line is None

    def test_on_line_callback_stored(self):
        real = io.StringIO()
        callback = lambda line: None
        cap = _LogCapture(real, on_line=callback)
        assert cap._on_line is callback


class TestLogCaptureWrite:

    def test_writes_to_real_stdout(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        cap.write("hello\n")
        assert "hello" in real.getvalue()

    def test_appends_line_to_lines(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        cap.write("a line\n")
        assert "a line" in cap.lines

    def test_empty_lines_not_appended(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        cap.write("\n\n\n")
        assert cap.lines == []

    def test_strips_ansi_from_lines(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        cap.write("\x1b[32mcoloured\x1b[0m\n")
        assert "coloured" in cap.lines[0]
        assert "\x1b" not in cap.lines[0]

    def test_callback_called_per_line(self):
        real = io.StringIO()
        received = []
        cap = _LogCapture(real, on_line=received.append)
        cap.write("line one\nline two\n")
        assert received == ["line one", "line two"]

    def test_returns_length_of_input(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        n = cap.write("hello\n")
        assert n == 6

    def test_partial_line_buffered(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        cap.write("partial")
        assert cap.lines == []  # no newline yet
        cap.write(" complete\n")
        assert len(cap.lines) == 1
        assert "partial complete" in cap.lines[0]

    def test_multiple_lines_in_one_write(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        cap.write("alpha\nbeta\ngamma\n")
        assert len(cap.lines) == 3

    def test_no_callback_no_error(self):
        real = io.StringIO()
        cap = _LogCapture(real)
        cap.write("hello\n")  # should not raise even with no callback


class TestLogCaptureFlush:

    def test_flush_calls_real_flush(self):
        real = MagicMock = __import__('unittest.mock', fromlist=['MagicMock']).MagicMock
        real_stdout = real()
        cap = _LogCapture(real_stdout)
        cap.flush()
        real_stdout.flush.assert_called_once()

"""
log_capture.py
==============
Stdout wrapper used by the web API to stream background task output
to WebSocket clients in real time.
"""

import io
import re as _re


def _strip_ansi(text: str) -> str:
    """Remove ANSI / Rich escape sequences from a string."""
    return _re.sub(r"\x1b\[[0-9;]*[mGKHF]|\[/?[a-z_ ]+\]", "", text)


class _LogCapture(io.TextIOBase):
    """
    Drop-in stdout replacement that:
    - strips ANSI / Rich markup
    - appends plain lines to a list
    - calls an optional callback so the UI can update live
    - still writes to the original stdout so terminal stays intact
    """
    def __init__(self, real_stdout, on_line=None):
        self._real = real_stdout
        self._on_line = on_line
        self._buf = ""
        self.lines: list = []

    def write(self, text: str) -> int:
        self._real.write(text)
        clean = _strip_ansi(text)
        self._buf += clean
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self.lines.append(line)
                if self._on_line:
                    self._on_line(line)
        return len(text)

    def flush(self):
        self._real.flush()

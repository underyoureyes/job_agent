"""
ui/constants.py
===============
Colour palette, font constants, ANSI-stripping utilities, log capture,
and ttk style configuration.
"""

import sys
import io
import re as _re
from tkinter import ttk


# ── ANSI stripping ────────────────────────────────────────────────────────────

def _strip_ansi(text: str) -> str:
    """Remove ANSI / Rich escape sequences from a string."""
    return _re.sub(r"\x1b\[[0-9;]*[mGKHF]|\[/?[a-z_ ]+\]", "", text)


class _LogCapture(io.TextIOBase):
    """
    Drop-in stdout replacement that:
    - strips ANSI / Rich markup
    - appends plain lines to a list
    - calls an optional callback so the UI can update live
    - still writes to the original stdout so PyCharm/terminal stays intact
    """
    def __init__(self, real_stdout, on_line=None):
        self._real = real_stdout
        self._on_line = on_line      # callable(line: str) → None
        self._buf = ""
        self.lines: list = []

    def write(self, text: str) -> int:
        self._real.write(text)       # pass through to terminal
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


# ── Colour palette ────────────────────────────────────────────────────────────
BG       = "#F7F6F3"
BG2      = "#EEECEA"
CARD     = "#FFFFFF"
BORDER   = "#D8D6D0"
TEXT     = "#1A1916"
TEXT2    = "#6B6963"
BLUE     = "#185FA5"
BLUE_LT  = "#E6F1FB"
GREEN    = "#3B6D11"
GREEN_LT = "#EAF3DE"
AMBER    = "#854F0B"
AMBER_LT = "#FAEEDA"
RED      = "#A32D2D"
RED_LT   = "#FCEBEB"
PURPLE   = "#534AB7"
PURP_LT  = "#EEEDFE"

STATUS_COLOURS = {
    "discovered":     (BLUE,   BLUE_LT),
    "score_me":       (AMBER,  AMBER_LT),
    "scored":         (GREEN,  GREEN_LT),
    "filtered":       (TEXT2,  BG2),
    "dismissed":      (TEXT2,  BG2),
    "tailoring":      (AMBER,  AMBER_LT),
    "tailored":       (BLUE,   BLUE_LT),
    "pending_review": (AMBER,  AMBER_LT),
    "approved":       (GREEN,  GREEN_LT),
    "skipped":        (RED,    RED_LT),
    "submitted":      (GREEN,  GREEN_LT),
    "interview":      (PURPLE, PURP_LT),
    "rejected":       (RED,    RED_LT),
    "offer":          (GREEN,  GREEN_LT),
}

FONT_FAMILY = "SF Pro Display" if sys.platform == "darwin" else "Segoe UI"
FONT        = (FONT_FAMILY, 13)
FONT_SM     = (FONT_FAMILY, 11)
FONT_LG     = (FONT_FAMILY, 16, "bold")
FONT_HEAD   = (FONT_FAMILY, 22, "bold")


def configure_styles():
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame",       background=BG)
    style.configure("Card.TFrame",  background=CARD,  relief="flat")
    style.configure("TLabel",       background=BG,    foreground=TEXT, font=FONT)
    style.configure("Card.TLabel",  background=CARD,  foreground=TEXT, font=FONT)
    style.configure("Muted.TLabel", background=BG,    foreground=TEXT2, font=FONT_SM)
    style.configure("Head.TLabel",  background=BG,    foreground=TEXT, font=FONT_HEAD)
    style.configure("TButton",      font=FONT, padding=(12, 6))
    style.configure("Primary.TButton", background=BLUE, foreground="white", font=FONT)
    style.map("Primary.TButton", background=[("active", "#1050A0")])
    style.configure("TEntry",       font=FONT, padding=6)
    style.configure("TSeparator",   background=BORDER)
    style.configure("Treeview",     font=FONT_SM, rowheight=32, background=CARD,
                    fieldbackground=CARD, foreground=TEXT, borderwidth=0)
    style.configure("Treeview.Heading", font=(FONT_FAMILY, 11, "bold"),
                    background=BG2, foreground=TEXT2, relief="flat")
    style.map("Treeview", background=[("selected", BLUE_LT)], foreground=[("selected", BLUE)])

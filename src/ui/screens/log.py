"""
ui/screens/log.py
=================
LogScreen — live scan/tailor output, colour-coded by severity.
"""

import sys
import tkinter as tk
from tkinter import messagebox, scrolledtext

from ui.constants import (
    BG, BG2, TEXT, TEXT2,
    FONT_SM, FONT_HEAD,
)
from ui.context import AppContext
from ui.screens.base import BaseScreen


class LogScreen(BaseScreen):
    def __init__(self, parent: tk.Frame, ctx: AppContext):
        super().__init__(parent, ctx)
        self._build(self.frame)

    def _build(self, parent: tk.Frame):
        header = tk.Frame(parent, bg=BG)
        header.pack(fill="x", padx=32, pady=(28, 8))
        tk.Label(header, text="Scan Log", font=FONT_HEAD, bg=BG, fg=TEXT).pack(side="left")

        btn_row = tk.Frame(header, bg=BG)
        btn_row.pack(side="right")
        tk.Button(btn_row, text="Clear", font=FONT_SM, bg=BG2, fg=TEXT,
                  relief="flat", padx=10, pady=4,
                  command=self._clear_log).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Copy all", font=FONT_SM, bg=BG2, fg=TEXT,
                  relief="flat", padx=10, pady=4,
                  command=self._copy_log).pack(side="left")

        tk.Label(parent,
                 text="Shows output from scans, scoring and tailoring — errors, jobs found, jobs filtered.",
                 font=FONT_SM, bg=BG, fg=TEXT2).pack(anchor="w", padx=32, pady=(0, 8))

        self._log_text = scrolledtext.ScrolledText(
            parent, font=("Menlo" if sys.platform == "darwin" else "Consolas", 11),
            bg="#1E1E1E", fg="#D4D4D4", insertbackground="#D4D4D4",
            relief="flat", bd=0, wrap="word", state="disabled",
        )
        self._log_text.pack(fill="both", expand=True, padx=32, pady=(0, 24))

        self._log_text.tag_configure("error",    foreground="#F48771")
        self._log_text.tag_configure("ok",        foreground="#89D185")
        self._log_text.tag_configure("filtered",  foreground="#808080")
        self._log_text.tag_configure("heading",   foreground="#569CD6")
        self._log_text.tag_configure("warn",      foreground="#CCA700")

        self._refresh_log_screen()

    def refresh(self):
        self._refresh_log_screen()

    def _log_line_tag(self, line: str) -> str:
        low = line.lower()
        if any(k in low for k in ("error", "failed", "exception", "traceback", "credit", "billing")):
            return "error"
        if any(k in low for k in ("✓", "saved", "scored", "tailored", "found")):
            return "ok"
        if any(k in low for k in ("⊘", "filtered", "senior", "irrelevant", "location", "salary", "skipped")):
            return "filtered"
        if any(k in low for k in ("scanning", "---", "===", "phase", "complete")):
            return "heading"
        if any(k in low for k in ("warning", "warn", "no jobs", "0 jobs", "blocked")):
            return "warn"
        return ""

    def _refresh_log_screen(self):
        if not hasattr(self, "_log_text"):
            return
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        lines = self.ctx.scan_log_lines
        if not lines:
            self._log_text.insert("end", "No scan has been run yet.\nClick 'Scan for jobs' to start.\n",
                                  "filtered")
        else:
            for line in lines:
                tag = self._log_line_tag(line)
                self._log_text.insert("end", line + "\n", tag)
            self._log_text.see("end")
        self._log_text.config(state="disabled")

    def append_line(self, line: str):
        """Called from scan/score/tailor threads — schedules UI update on main thread."""
        self.ctx.scan_log_lines.append(line)
        if hasattr(self, "_log_text"):
            def _update():
                self._log_text.config(state="normal")
                tag = self._log_line_tag(line)
                self._log_text.insert("end", line + "\n", tag)
                self._log_text.see("end")
                self._log_text.config(state="disabled")
            self.frame.after(0, _update)

    def _clear_log(self):
        self.ctx.scan_log_lines.clear()
        self._refresh_log_screen()

    def _copy_log(self):
        text = "\n".join(self.ctx.scan_log_lines)
        self.frame.clipboard_clear()
        self.frame.clipboard_append(text)
        messagebox.showinfo("Copied", "Log copied to clipboard.")

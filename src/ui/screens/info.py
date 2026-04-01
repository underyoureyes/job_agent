"""
ui/screens/info.py
==================
InfoScreen — links to documentation files.
"""

import sys
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

from ui.constants import (
    BG, CARD, TEXT, TEXT2, BLUE, BLUE_LT,
    FONT_SM, FONT_HEAD, FONT_FAMILY,
)
from ui.context import AppContext
from ui.utils import open_file
from ui.screens.base import BaseScreen


class InfoScreen(BaseScreen):
    def __init__(self, parent: tk.Frame, ctx: AppContext):
        super().__init__(parent, ctx)
        self._build(self.frame)

    def _build(self, parent: tk.Frame):
        tk.Label(parent, text="Info & Documentation", font=FONT_HEAD, bg=BG, fg=TEXT).pack(
            anchor="w", padx=40, pady=(32, 4))
        tk.Label(parent, text="Open project documents from the docs/ folder.",
                 font=FONT_SM, bg=BG, fg=TEXT2).pack(anchor="w", padx=40, pady=(0, 24))

        docs = [
            ("Business Requirements Document (BRD)", "job_agent_BRD.docx",
             "Full specification of what the Job Agent does and why."),
            ("User Guide", "job_agent_user_guide.docx",
             "Step-by-step instructions for using the application."),
        ]
        for title, filename, desc in docs:
            card = tk.Frame(parent, bg=CARD, relief="flat", bd=1)
            card.pack(fill="x", padx=40, pady=(0, 12))
            tk.Label(card, text=title, font=(FONT_FAMILY, 13, "bold"),
                     bg=CARD, fg=TEXT).pack(anchor="w", padx=20, pady=(14, 2))
            tk.Label(card, text=desc, font=FONT_SM, bg=CARD, fg=TEXT2).pack(
                anchor="w", padx=20, pady=(0, 10))
            tk.Button(card, text=f"Open {filename}", font=FONT_SM,
                      bg=BLUE_LT, fg=BLUE, relief="flat", padx=12, pady=6,
                      command=lambda f=filename: self._open_doc(f)).pack(
                anchor="w", padx=20, pady=(0, 14))

    def _open_user_guide(self):
        self._open_doc("job_agent_user_guide.docx")

    def _open_brd(self):
        self._open_doc("job_agent_BRD.docx")

    def _open_doc(self, filename: str):
        if getattr(sys, "frozen", False):
            docs_dir = Path(sys._MEIPASS) / "docs"
        else:
            docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        path = docs_dir / filename
        if not path.exists():
            messagebox.showwarning("File not found",
                f"{filename} not found.\n\nExpected location:\n{path}")
            return
        open_file(str(path))

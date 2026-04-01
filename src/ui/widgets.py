"""
ui/widgets.py
=============
Reusable widget factory functions used across multiple screens.
"""

import tkinter as tk
from ui.constants import BG, BG2, BORDER, CARD, TEXT, TEXT2, FONT, FONT_SM, FONT_FAMILY


def section_label(parent: tk.Frame, text: str):
    """Draw a horizontal rule followed by a bold section heading."""
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=40, pady=(20, 0))
    tk.Label(parent, text=text, font=(FONT_FAMILY, 12, "bold"),
             bg=BG, fg=TEXT2).pack(anchor="w", padx=40, pady=(8, 4))


def labeled_entry(parent: tk.Frame, label: str, placeholder: str = "",
                  show: str = "") -> tk.StringVar:
    """Create a label + entry pair with optional placeholder text."""
    tk.Label(parent, text=label, font=FONT_SM, bg=BG, fg=TEXT2).pack(anchor="w", padx=40, pady=(6, 0))
    var = tk.StringVar()
    entry_kwargs = dict(textvariable=var, font=FONT, width=52,
                        relief="solid", bd=1, bg=CARD)
    if show:
        entry_kwargs["show"] = show
    entry = tk.Entry(parent, **entry_kwargs)
    entry.pack(anchor="w", padx=40, pady=(2, 0), ipady=6)
    if placeholder and not var.get():
        entry.insert(0, placeholder)
        entry.config(fg=TEXT2)
        entry.bind("<FocusIn>", lambda e: (entry.delete(0, "end"), entry.config(fg=TEXT))
                   if entry.get() == placeholder else None)
    return var


def file_picker_row(parent: tk.Frame, label: str, var: tk.StringVar, command):
    """Create a label + readonly entry + browse button row for file/folder picking."""
    row = tk.Frame(parent, bg=BG)
    row.pack(anchor="w", padx=40, pady=4, fill="x")
    tk.Label(row, text=label, font=FONT_SM, bg=BG, fg=TEXT2, width=28, anchor="w").pack(side="left")
    tk.Entry(row, textvariable=var, font=FONT_SM, width=34,
             relief="solid", bd=1, bg=CARD, state="readonly").pack(side="left", padx=(0, 8), ipady=5)
    tk.Button(row, text="Browse…", font=FONT_SM, command=command,
              bg=BG2, fg=TEXT, relief="flat", padx=10, pady=4).pack(side="left")

"""
ui/screens/settings.py
======================
SettingsScreen — job search keywords, job boards, filter lists, salary thresholds.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from ui.constants import (
    BG, BG2, CARD, BORDER, TEXT, TEXT2, BLUE, BLUE_LT,
    GREEN, GREEN_LT, RED, RED_LT,
    FONT, FONT_SM, FONT_HEAD, FONT_FAMILY,
)
from ui.context import AppContext
from ui.widgets import labeled_entry, section_label
from ui.screens.base import BaseScreen


class SettingsScreen(BaseScreen):
    def __init__(self, parent: tk.Frame, ctx: AppContext):
        super().__init__(parent, ctx)
        self._build(self.frame)

    def _build(self, parent: tk.Frame):
        self._settings_parent = parent
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        tk.Label(inner, text="Settings", font=FONT_HEAD, bg=BG, fg=TEXT).pack(anchor="w", padx=40, pady=(32, 4))
        tk.Label(inner, text="Changes take effect on the next scan. Restart the app after saving.",
                 font=FONT_SM, bg=BG, fg=TEXT2).pack(anchor="w", padx=40, pady=(0, 8))

        # ── Job search ────────────────────────────────────────────────────────
        section_label(inner, "Job search")

        tk.Label(inner, text="Search keywords (one per line):", font=FONT_SM, bg=BG, fg=TEXT2).pack(anchor="w", padx=40, pady=(8, 2))
        self._kw_text = tk.Text(inner, height=7, font=FONT_SM, bg=CARD,
                                relief="solid", bd=1, fg=TEXT, width=52)
        self._kw_text.pack(anchor="w", padx=40)
        config = self.ctx.config
        if config:
            self._kw_text.insert("1.0", "\n".join(config.search_keywords))

        self._min_salary_var = labeled_entry(inner, "Minimum salary (£)", "20000")
        self._max_salary_var = labeled_entry(inner, "Maximum salary — 0 = no limit (£)", "0")
        self._max_age_var    = labeled_entry(inner, "Only show jobs posted within (days)", "14")
        self._min_score_var  = labeled_entry(inner, "Minimum match score to keep (%)", "75")

        if config:
            self._min_salary_var.set(str(config.min_salary_gbp))
            self._max_salary_var.set(str(getattr(config, 'max_salary_gbp', 0)))
            self._max_age_var.set(str(config.max_job_age_days))
            self._min_score_var.set(str(config.min_match_score))

        # ATS mode toggle
        self._ats_mode_var = tk.BooleanVar(value=config.ats_mode if config else True)
        ats_row = tk.Frame(inner, bg=BG)
        ats_row.pack(anchor="w", padx=40, pady=(8, 0))
        tk.Checkbutton(ats_row, text="ATS compatibility mode",
                       variable=self._ats_mode_var, font=FONT, bg=BG, fg=TEXT,
                       activebackground=BG, selectcolor=CARD).pack(side="left")
        tk.Label(ats_row, text="  (recommended — makes CVs readable by automated scanners)",
                 font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left")

        # ── Job boards ────────────────────────────────────────────────────────
        section_label(inner, "Job boards")

        self._scan_civil_var      = tk.BooleanVar(value=config.scan_civil_service if config else True)
        self._scan_guardian_var   = tk.BooleanVar(value=config.scan_guardian if config else True)
        self._scan_linkedin_var   = tk.BooleanVar(value=config.scan_linkedin if config else True)
        self._scan_w4mpjobs_var   = tk.BooleanVar(value=config.scan_w4mpjobs if config else True)
        self._scan_charityjob_var = tk.BooleanVar(value=config.scan_charityjob if config else True)
        for var, label in [
            (self._scan_civil_var,      "Civil Service Jobs"),
            (self._scan_guardian_var,   "Guardian Jobs"),
            (self._scan_linkedin_var,   "LinkedIn (RSS feed)"),
            (self._scan_w4mpjobs_var,   "W4MP Jobs (parliamentary & political roles)"),
            (self._scan_charityjob_var, "Charity Job"),
        ]:
            tk.Checkbutton(inner, text=label, variable=var, font=FONT, bg=BG, fg=TEXT,
                           activebackground=BG, selectcolor=CARD).pack(anchor="w", padx=40, pady=2)

        # ── Filter editor ─────────────────────────────────────────────────────
        section_label(inner, "Filters — Too senior (title keywords)")
        tk.Label(inner,
                 text="Jobs whose title contains any of these words are removed before scoring (free). Add words to reduce volume. Remove words if good roles are being filtered out.",
                 font=FONT_SM, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", padx=40, pady=(4, 4))
        self._senior_filter_frame = self._build_filter_editor(
            inner, "seniority_filter_titles",
            config.seniority_filter_titles if config else []
        )

        section_label(inner, "Filters — Irrelevant job titles")
        tk.Label(inner,
                 text="Jobs whose title contains any of these words are removed as clearly irrelevant. Add words to remove more noise. Remove words if relevant roles are being missed.",
                 font=FONT_SM, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", padx=40, pady=(4, 4))
        self._irrelevant_filter_frame = self._build_filter_editor(
            inner, "irrelevant_filter_titles",
            config.irrelevant_filter_titles if config else []
        )

        section_label(inner, "Filters — Excluded locations")
        tk.Label(inner,
                 text="Jobs whose location contains any of these words are removed. Add cities/countries to exclude. Remove entries to include more locations.",
                 font=FONT_SM, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", padx=40, pady=(4, 4))
        self._location_filter_frame = self._build_filter_editor(
            inner, "exclude_locations",
            config.exclude_locations if config else []
        )

        # ── Save ──────────────────────────────────────────────────────────────
        tk.Frame(inner, bg=BG, height=16).pack()
        save_row = tk.Frame(inner, bg=BG)
        save_row.pack(anchor="w", padx=40, pady=(0, 40))
        tk.Button(save_row, text="Save all settings", font=(FONT_FAMILY, 13, "bold"),
                  bg=BLUE, fg=TEXT,  relief="flat", padx=20, pady=8,
                  command=self._save_settings).pack(side="left", padx=(0, 12))
        tk.Button(save_row, text="Reset filters to defaults", font=FONT_SM,
                  bg=BG2, fg=TEXT, relief="flat", padx=12, pady=8,
                  command=self._reset_filters).pack(side="left")

    def refresh(self):
        self._refresh_settings()

    def _refresh_settings(self):
        if not hasattr(self, "_settings_parent"):
            return
        for w in self._settings_parent.winfo_children():
            w.destroy()
        self._build(self._settings_parent)

    def _build_filter_editor(self, parent, config_attr: str, initial_values: list) -> tk.Frame:
        outer = tk.Frame(parent, bg=BG)
        outer.pack(anchor="w", padx=40, pady=(0, 8), fill="x")

        list_frame = tk.Frame(outer, bg=BG)
        list_frame.pack(side="left", fill="both")

        listbox = tk.Listbox(list_frame, font=FONT_SM, height=6, width=38,
                             bg=CARD, fg=TEXT, relief="solid", bd=1,
                             selectbackground=BLUE_LT, selectforeground=BLUE,
                             activestyle="none")
        listbox.pack(side="left", fill="both")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        sb.pack(side="right", fill="y")
        listbox.config(yscrollcommand=sb.set)

        for val in sorted(initial_values, key=str.lower):
            listbox.insert("end", val)

        ctrl = tk.Frame(outer, bg=BG)
        ctrl.pack(side="left", padx=(12, 0), anchor="n")

        entry = tk.Entry(ctrl, font=FONT_SM, width=22, relief="solid", bd=1, bg=CARD)
        entry.pack(pady=(0, 6))
        entry.bind("<Return>", lambda e: self._filter_add(listbox, entry))

        tk.Button(ctrl, text="+ Add", font=FONT_SM, bg=GREEN_LT, fg=GREEN,
                  relief="flat", padx=10, pady=4, width=10,
                  command=lambda: self._filter_add(listbox, entry)).pack(pady=(0, 4))

        tk.Button(ctrl, text="Remove selected", font=FONT_SM, bg=RED_LT, fg=RED,
                  relief="flat", padx=10, pady=4, width=14,
                  command=lambda: self._filter_remove(listbox)).pack(pady=(0, 4))

        tk.Label(ctrl, text="Double-click to edit", font=(FONT_FAMILY, 10),
                 bg=BG, fg=TEXT2).pack()

        listbox.bind("<Double-1>", lambda e: self._filter_edit(listbox, entry))

        listbox._config_attr = config_attr
        outer._listbox = listbox
        outer._config_attr = config_attr
        return outer

    @staticmethod
    def _filter_add(listbox: tk.Listbox, entry: tk.Entry):
        val = entry.get().strip().lower()
        if val and val not in listbox.get(0, "end"):
            existing = list(listbox.get(0, "end"))
            existing.append(val)
            existing.sort(key=str.lower)
            listbox.delete(0, "end")
            for v in existing:
                listbox.insert("end", v)
            entry.delete(0, "end")

    @staticmethod
    def _filter_remove(listbox: tk.Listbox):
        sel = listbox.curselection()
        for idx in reversed(sel):
            listbox.delete(idx)

    @staticmethod
    def _filter_edit(listbox: tk.Listbox, entry: tk.Entry):
        sel = listbox.curselection()
        if not sel:
            return
        val = listbox.get(sel[0])
        entry.delete(0, "end")
        entry.insert(0, val)
        listbox.delete(sel[0])

    def _save_settings(self):
        config = self.ctx.config
        if not config:
            return

        try:
            import re
            config_path = Path(__file__).parent.parent.parent / "config.py"
            text = config_path.read_text(encoding="utf-8")

            def set_int(attr, val):
                return re.sub(
                    rf"({attr}:\s*int\s*=\s*)\d+",
                    rf"\g<1>{val}", text
                )
            def set_bool(attr, val):
                return re.sub(
                    rf"({attr}:\s*bool\s*=\s*)(?:True|False)",
                    rf"\g<1>{'True' if val else 'False'}", text
                )
            def set_list(attr, values):
                items = ",\n        ".join(f'"{v}"' for v in values)
                new_block = f'{attr}: List[str] = field(default_factory=lambda: [\n        {items},\n    ])'
                return re.sub(
                    rf'{attr}: List\[str\] = field\(default_factory=lambda: \[.*?\]\)',
                    new_block, text, flags=re.DOTALL
                )

            text = set_int("min_salary_gbp", self._min_salary_var.get() or "20000")
            text = set_int("max_salary_gbp", self._max_salary_var.get() or "0")
            text = set_int("max_job_age_days", self._max_age_var.get() or "14")
            text = set_int("min_match_score", self._min_score_var.get() or "75")
            text = set_bool("ats_mode", self._ats_mode_var.get())
            text = set_bool("scan_civil_service", self._scan_civil_var.get())
            text = set_bool("scan_guardian", self._scan_guardian_var.get())
            text = set_bool("scan_linkedin", self._scan_linkedin_var.get())
            text = set_bool("scan_w4mpjobs", self._scan_w4mpjobs_var.get())
            text = set_bool("scan_charityjob", self._scan_charityjob_var.get())

            keywords = [k.strip() for k in self._kw_text.get("1.0", "end").splitlines() if k.strip()]
            if keywords:
                text = set_list("search_keywords", keywords)

            for frame in [self._senior_filter_frame, self._irrelevant_filter_frame, self._location_filter_frame]:
                lb = frame._listbox
                values = list(lb.get(0, "end"))
                text = set_list(lb._config_attr, values)

            config_path.write_text(text, encoding="utf-8")

            if self.ctx.reload_backend:
                self.ctx.reload_backend()

            messagebox.showinfo("Settings saved",
                "✓ Settings saved successfully.\n\n"
                "Filter changes take effect immediately on the next scan.\n"
                "Restart the app to reload all other settings.")

        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save settings:\n{e}")

    def _reset_filters(self):
        if not messagebox.askyesno("Reset filters",
            "Reset seniority, irrelevant title, and location filters to defaults?\n\n"
            "Your current filter changes will be lost."):
            return

        from config import Config
        defaults = Config()

        for frame, attr in [
            (self._senior_filter_frame,     "seniority_filter_titles"),
            (self._irrelevant_filter_frame,  "irrelevant_filter_titles"),
            (self._location_filter_frame,    "exclude_locations"),
        ]:
            lb = frame._listbox
            lb.delete(0, "end")
            for val in getattr(defaults, attr, []):
                lb.insert("end", val)

        messagebox.showinfo("Filters reset", "Filters reset to defaults. Click Save all settings to apply.")

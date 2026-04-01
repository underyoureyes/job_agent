"""
ui/screens/add_job.py
=====================
AddJobScreen — paste a job description, enter title + employer,
and generate a tailored CV + cover letter immediately.
Bypasses scanning and scoring — goes straight to tailoring.
"""

import sys
import re
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from ui.constants import (
    BG, BG2, CARD, BORDER, TEXT, TEXT2, BLUE, BLUE_LT,
    GREEN, GREEN_LT,
    FONT, FONT_SM, FONT_LG, FONT_HEAD, FONT_FAMILY,
    _LogCapture,
)
from ui.context import AppContext
from ui.screens.base import BaseScreen


class AddJobScreen(BaseScreen):
    def __init__(self, parent: tk.Frame, ctx: AppContext):
        super().__init__(parent, ctx)
        self._build(self.frame)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self, parent: tk.Frame):
        # Scrollable outer container so it works on small screens
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        )

        px = 36  # common left/right padding

        # Header
        hdr = tk.Frame(inner, bg=BG)
        hdr.pack(fill="x", padx=px, pady=(28, 2))
        tk.Label(hdr, text="Add job by description", font=FONT_HEAD,
                 bg=BG, fg=TEXT).pack(side="left")

        tk.Label(
            inner,
            text="Paste a job description you received (e.g. from an email), "
                 "enter the employer and title, and generate a tailored CV + cover letter.",
            font=FONT_SM, bg=BG, fg=TEXT2, justify="left", wraplength=680,
        ).pack(anchor="w", padx=px, pady=(0, 16))

        # ── Required fields row ───────────────────────────────────────────────
        fields_row = tk.Frame(inner, bg=BG)
        fields_row.pack(fill="x", padx=px, pady=(0, 12))

        # Job title
        left = tk.Frame(fields_row, bg=BG)
        left.pack(side="left", fill="x", expand=True, padx=(0, 16))
        tk.Label(left, text="Job title  *", font=(FONT_FAMILY, 12, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w")
        self._title_var = tk.StringVar()
        tk.Entry(left, textvariable=self._title_var, font=FONT,
                 relief="solid", bd=1, bg=CARD).pack(fill="x", ipady=5, pady=(4, 0))

        # Employer
        right = tk.Frame(fields_row, bg=BG)
        right.pack(side="left", fill="x", expand=True)
        tk.Label(right, text="Employer  *", font=(FONT_FAMILY, 12, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w")
        self._employer_var = tk.StringVar()
        tk.Entry(right, textvariable=self._employer_var, font=FONT,
                 relief="solid", bd=1, bg=CARD).pack(fill="x", ipady=5, pady=(4, 0))

        # ── Optional fields row ───────────────────────────────────────────────
        opt_row = tk.Frame(inner, bg=BG)
        opt_row.pack(fill="x", padx=px, pady=(0, 12))

        loc_frame = tk.Frame(opt_row, bg=BG)
        loc_frame.pack(side="left", fill="x", expand=True, padx=(0, 16))
        tk.Label(loc_frame, text="Location  (optional)", font=FONT_SM,
                 bg=BG, fg=TEXT2).pack(anchor="w")
        self._location_var = tk.StringVar(value="London")
        tk.Entry(loc_frame, textvariable=self._location_var, font=FONT_SM,
                 relief="solid", bd=1, bg=CARD).pack(fill="x", ipady=4, pady=(4, 0))

        sal_frame = tk.Frame(opt_row, bg=BG)
        sal_frame.pack(side="left", fill="x", expand=True)
        tk.Label(sal_frame, text="Salary  (optional)", font=FONT_SM,
                 bg=BG, fg=TEXT2).pack(anchor="w")
        self._salary_var = tk.StringVar()
        tk.Entry(sal_frame, textvariable=self._salary_var, font=FONT_SM,
                 relief="solid", bd=1, bg=CARD).pack(fill="x", ipady=4, pady=(4, 0))

        # ── Description box ───────────────────────────────────────────────────
        tk.Label(inner, text="Job description  *", font=(FONT_FAMILY, 12, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w", padx=px, pady=(0, 4))
        tk.Label(
            inner,
            text="Paste the full job description here — the more detail, "
                 "the better the tailored output.",
            font=FONT_SM, bg=BG, fg=TEXT2,
        ).pack(anchor="w", padx=px, pady=(0, 6))

        desc_frame = tk.Frame(inner, bg=BG)
        desc_frame.pack(fill="both", expand=True, padx=px, pady=(0, 16))

        self._desc_text = tk.Text(
            desc_frame, font=FONT_SM, bg=CARD, fg=TEXT,
            relief="solid", bd=1, wrap="word",
            height=18, insertbackground=TEXT,
        )
        desc_vsb = ttk.Scrollbar(desc_frame, orient="vertical",
                                  command=self._desc_text.yview)
        self._desc_text.configure(yscrollcommand=desc_vsb.set)
        self._desc_text.pack(side="left", fill="both", expand=True)
        desc_vsb.pack(side="right", fill="y")

        # Clear button
        tk.Button(
            inner, text="Clear form", font=FONT_SM, bg=BG2, fg=TEXT2,
            relief="flat", padx=10, pady=4,
            command=self._clear_form,
        ).pack(anchor="e", padx=36, pady=(0, 4))

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=36, pady=(4, 12))

        # ── Action bar ────────────────────────────────────────────────────────
        action = tk.Frame(inner, bg=BG)
        action.pack(fill="x", padx=36, pady=(0, 28))

        self._status_label = tk.Label(action, text="", font=FONT_SM, bg=BG, fg=TEXT2)
        self._status_label.pack(side="left")

        self._generate_btn = tk.Button(
            action,
            text="✍  Generate CV & Cover Letter  (~$0.05)",
            font=(FONT_FAMILY, 13, "bold"),
            bg=GREEN, fg="black", relief="flat",
            padx=20, pady=10,
            command=self._on_generate,
        )
        self._generate_btn.pack(side="right")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_form(self):
        self._title_var.set("")
        self._employer_var.set("")
        self._location_var.set("London")
        self._salary_var.set("")
        self._desc_text.delete("1.0", tk.END)
        self._status_label.config(text="")

    def refresh(self):
        pass  # nothing to refresh on switch

    # ── Generate ──────────────────────────────────────────────────────────────

    def _on_generate(self):
        title       = self._title_var.get().strip()
        employer    = self._employer_var.get().strip()
        description = self._desc_text.get("1.0", tk.END).strip()
        location    = self._location_var.get().strip()
        salary      = self._salary_var.get().strip()

        if not title:
            messagebox.showwarning("Required", "Please enter the job title.")
            return
        if not employer:
            messagebox.showwarning("Required", "Please enter the employer name.")
            return
        if not description:
            messagebox.showwarning("Required", "Please paste the job description.")
            return

        tracker = self.ctx.tracker
        config  = self.ctx.config
        if not tracker or not config:
            messagebox.showerror("Not ready", "App not fully initialised. Check Setup.")
            return

        # Build a unique URL so the tracker doesn't deduplicate manual entries
        slug = re.sub(r"[^a-z0-9]+", "-", (title + "-" + employer).lower()).strip("-")
        ts   = datetime.now().strftime("%Y%m%d%H%M%S")
        url  = f"manual://{slug}-{ts}"

        job = {
            "title":       title,
            "employer":    employer,
            "location":    location or "London",
            "salary":      salary,
            "url":         url,
            "description": description,
            "source":      "manual",
            "date_closes": None,
        }

        # Add to DB and move straight to tailoring (skip scoring)
        job_id = tracker.add_job(job)
        tracker.update_status(job_id, "tailoring", "Added manually via 'Add job by description'")

        self._generate_btn.config(text="Generating…", state="disabled", bg="#555")
        self._status_label.config(text="Tailoring in progress…")
        self.frame.update_idletasks()

        append_log = self.ctx.append_log_line
        if append_log:
            append_log(
                f"── Manual tailoring started {datetime.now().strftime('%d %b %Y %H:%M:%S')} ──"
            )
            append_log(f"   {title} @ {employer}")

        def tailor_thread():
            capture = _LogCapture(sys.__stdout__, on_line=append_log)
            old_stdout = sys.stdout
            sys.stdout = capture
            try:
                from main import run_tailor_approved
                run_tailor_approved(config, tracker)
            except Exception as e:
                err = str(e)
                if append_log:
                    append_log(f"ERROR: {err}")
                self.frame.after(0, lambda: messagebox.showerror("Tailoring failed", err))
            finally:
                sys.stdout = old_stdout
                if append_log:
                    append_log(
                        f"── Manual tailoring finished {datetime.now().strftime('%H:%M:%S')} ──"
                    )
                self.frame.after(0, self._generate_done)

        threading.Thread(target=tailor_thread, daemon=True).start()

    def _generate_done(self):
        self._generate_btn.config(
            text="✍  Generate CV & Cover Letter  (~$0.05)",
            state="normal", bg=GREEN,
        )
        self._status_label.config(text="Done — check Review queue")

        session = self.ctx.session
        tracker = self.ctx.tracker
        if session and tracker:
            # Record the freshly tailored job
            job = next(
                (tracker.get_job(j["id"])
                 for j in tracker.get_all_jobs()
                 if j.get("source") == "manual" and j.get("status") == "pending_review"),
                None,
            )
            if job:
                session.record_tailored([job])

        if self.ctx.refresh_review:
            self.ctx.refresh_review()
        if self.ctx.refresh_dashboard:
            self.ctx.refresh_dashboard()

        if messagebox.askyesno(
            "Done",
            "CV and cover letter generated.\n\nGo to Review queue now?",
        ):
            if self.ctx.show_screen:
                self.ctx.show_screen("review")

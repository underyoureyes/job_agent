"""
ui/screens/review.py
====================
ReviewScreen — step through pending applications, approve/skip/auto-apply.
"""

import tkinter as tk
import webbrowser
from tkinter import messagebox
import threading
from pathlib import Path

from ui.constants import (
    BG, BG2, CARD, TEXT, TEXT2, BLUE, BLUE_LT,
    GREEN, AMBER, RED, RED_LT,
    FONT, FONT_SM, FONT_HEAD, FONT_FAMILY,
)
from ui.context import AppContext
from ui.utils import open_file
from ui.screens.base import BaseScreen


class ReviewScreen(BaseScreen):
    def __init__(self, parent: tk.Frame, ctx: AppContext):
        super().__init__(parent, ctx)
        self._review_jobs = []
        self._review_idx = 0
        self._build(self.frame)

    def _build(self, parent: tk.Frame):
        # Header
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill="x", padx=32, pady=(28, 0))
        tk.Label(hdr, text="Review queue", font=FONT_HEAD, bg=BG, fg=TEXT).pack(side="left")
        self._review_counter_label = tk.Label(hdr, text="", font=FONT_SM, bg=BG, fg=TEXT2)
        self._review_counter_label.pack(side="left", padx=16)

        # Job card
        self._review_card = tk.Frame(parent, bg=CARD, relief="flat", bd=1)
        self._review_card.pack(fill="x", padx=32, pady=16)

        self._rv_title     = tk.Label(self._review_card, text="", font=(FONT_FAMILY, 15, "bold"),
                                      bg=CARD, fg=TEXT, anchor="w")
        self._rv_title.pack(fill="x", padx=20, pady=(16, 2))
        self._rv_employer  = tk.Label(self._review_card, text="", font=FONT,
                                      bg=CARD, fg=TEXT2, anchor="w")
        self._rv_employer.pack(fill="x", padx=20)
        self._rv_meta      = tk.Label(self._review_card, text="", font=FONT_SM,
                                      bg=CARD, fg=TEXT2, anchor="w")
        self._rv_meta.pack(fill="x", padx=20, pady=(2, 4))
        self._rv_url       = tk.Label(self._review_card, text="", font=(FONT_FAMILY, 11, "underline"),
                                      bg=CARD, fg=BLUE, anchor="w", cursor="hand2")
        self._rv_url.pack(fill="x", padx=20, pady=(0, 4))
        self._rv_url.bind("<Button-1>", lambda e: self._open_review_url())
        self._rv_reason    = tk.Label(self._review_card, text="", font=FONT_SM,
                                      bg=CARD, fg=TEXT2, anchor="w", wraplength=700, justify="left")
        self._rv_reason.pack(fill="x", padx=20, pady=(0, 12))

        # File buttons
        btn_row = tk.Frame(self._review_card, bg=CARD)
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        tk.Button(btn_row, text="Open CV (.docx)", font=FONT_SM,
                  bg=BLUE_LT, fg=BLUE, relief="flat", padx=12, pady=6,
                  command=lambda: self._open_review_file("cv")).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Open cover letter (.docx)", font=FONT_SM,
                  bg=BLUE_LT, fg=BLUE, relief="flat", padx=12, pady=6,
                  command=lambda: self._open_review_file("letter")).pack(side="left")

        # Notes
        tk.Label(parent, text="Notes (optional):", font=FONT_SM, bg=BG, fg=TEXT2).pack(anchor="w", padx=32)
        self._rv_notes = tk.Text(parent, height=3, font=FONT_SM, bg=CARD,
                                 relief="solid", bd=1, fg=TEXT)
        self._rv_notes.pack(fill="x", padx=32, pady=(2, 12))

        # Decision buttons
        dec_row = tk.Frame(parent, bg=BG)
        dec_row.pack(fill="x", padx=32)

        tk.Button(dec_row, text="← Previous", font=FONT_SM,
                  bg=BG2, fg=TEXT, relief="flat", padx=14, pady=8,
                  command=self._review_prev).pack(side="left")

        tk.Button(dec_row, text="Skip this application", font=FONT,
                  bg=RED_LT, fg=RED, relief="flat", padx=16, pady=8,
                  command=self._review_skip).pack(side="left", padx=(0, 8))

        tk.Button(dec_row, text="✓ Approve", font=(FONT_FAMILY, 13, "bold"),
                  bg=GREEN, fg="white", relief="flat", padx=20, pady=8,
                  command=self._review_approve).pack(side="left")

        tk.Button(dec_row, text="Next →", font=FONT_SM,
                  bg=BG2, fg=TEXT, relief="flat", padx=14, pady=8,
                  command=self._review_next).pack(side="right")

        # Auto-apply row
        self._apply_row = tk.Frame(parent, bg=BG)
        self._apply_row.pack(fill="x", padx=32, pady=(12, 0))
        self._auto_apply_btn = tk.Button(
            self._apply_row,
            text="",
            font=(FONT_FAMILY, 13, "bold"),
            relief="flat", padx=20, pady=8,
            command=self._review_auto_apply,
        )
        self._auto_apply_btn.pack(side="left")
        self._auto_apply_status = tk.Label(
            self._apply_row, text="", font=FONT_SM, bg=BG, fg=TEXT2
        )
        self._auto_apply_status.pack(side="left", padx=12)
        self._apply_row.pack_forget()

    def refresh(self):
        self._refresh_review()

    def _refresh_review(self):
        tracker = self.ctx.tracker
        if not tracker:
            return

        self._rv_title.config(text="⏳  Refreshing…")
        self._rv_employer.config(text="")
        self._rv_meta.config(text="")
        self._rv_url.config(text="")
        self._rv_reason.config(text="")
        self._review_counter_label.config(text="")
        self.frame.update_idletasks()

        self._review_jobs = tracker.get_pending_review()
        self._review_idx = 0
        self._show_review_job()

    def _show_review_job(self):
        if not self._review_jobs:
            self._rv_title.config(text="No applications pending review")
            self._rv_employer.config(text="Run 'Scan for jobs' to find new positions.")
            self._rv_meta.config(text="")
            self._rv_url.config(text="")
            self._rv_reason.config(text="")
            self._review_counter_label.config(text="")
            return

        if self._review_idx >= len(self._review_jobs):
            self._review_idx = len(self._review_jobs) - 1

        job = self._review_jobs[self._review_idx]
        n = len(self._review_jobs)
        self._review_counter_label.config(text=f"{self._review_idx + 1} of {n}")

        score = f"{job['match_score']}%" if job.get("match_score") else "N/A"
        source = (job.get("source") or "").replace("_", " ").title()
        salary = job.get("salary") or "Salary not listed"
        location = job.get("location") or ""
        closes = job.get("date_closes") or ""
        closes_str = f" · Closes: {closes}" if closes else ""

        self._rv_title.config(text=job.get("title") or "Unknown role")
        self._rv_employer.config(text=job.get("employer") or "")
        self._rv_meta.config(text=f"{location}  ·  {salary}  ·  Match: {score}  ·  Source: {source}{closes_str}")

        url = job.get("url") or ""
        self._rv_url.config(text=url if url else "")
        self._rv_url._job_url = url

        self._rv_reason.config(text=job.get("match_reason") or "")
        self._rv_notes.delete("1.0", "end")
        if job.get("notes"):
            self._rv_notes.insert("1.0", job["notes"])

        src = (job.get("source") or "").lower()
        apply_label = None
        apply_colours = None
        tracker = self.ctx.tracker
        if src == "reed":
            apply_label = "Approve & Apply on Reed"
            apply_colours = ("#8B2FC9", "#F3E8FF")
        elif src in ("linkedin", "linkedin_rss", "linkedin_manual"):
            easy_apply = tracker.is_easy_apply(job) if tracker else None
            if easy_apply is not False:
                apply_label = "Approve & Easy Apply on LinkedIn"
                apply_colours = (BLUE, BLUE_LT)

        if apply_label:
            self._auto_apply_btn.config(
                text=apply_label,
                bg=apply_colours[0],
                fg=TEXT,
            )
            self._auto_apply_status.config(text="")
            self._apply_row.pack(fill="x", padx=32, pady=(12, 0))
        else:
            self._apply_row.pack_forget()

    def _open_review_url(self):
        url = getattr(self._rv_url, "_job_url", "")
        if url:
            webbrowser.open(url)

    def _open_review_file(self, which: str):
        if not self._review_jobs or self._review_idx >= len(self._review_jobs):
            return
        job = self._review_jobs[self._review_idx]
        path = None
        if which == "cv":
            path = job.get("tailored_cv_path")
        elif which == "letter":
            path = job.get("cover_letter_path")
        elif which == "cv_pdf":
            base = job.get("tailored_cv_path") or ""
            path = base.replace(".docx", ".pdf").replace(".md", ".pdf")
        elif which == "letter_pdf":
            base = job.get("cover_letter_path") or ""
            path = base.replace(".docx", ".pdf").replace(".md", ".pdf")
        if path and Path(path).exists():
            open_file(path)
        else:
            messagebox.showinfo("File not found", f"The file does not exist yet:\n{path}")

    def _save_review_notes(self):
        if not self._review_jobs:
            return
        job = self._review_jobs[self._review_idx]
        notes = self._rv_notes.get("1.0", "end").strip()
        if notes:
            self.ctx.tracker.add_note(job["id"], notes)

    def _review_approve(self):
        if not self._review_jobs:
            return
        self._save_review_notes()
        job = self._review_jobs[self._review_idx]
        self.ctx.tracker.update_status(job["id"], "approved", "Approved via UI review")
        self._review_jobs.pop(self._review_idx)
        if self._review_idx >= len(self._review_jobs):
            self._review_idx = max(0, len(self._review_jobs) - 1)
        n = len(self._review_jobs)
        self._review_counter_label.config(text=f"{self._review_idx + 1 if n else 0} of {n}")
        self._show_review_job()

    def _review_auto_apply(self):
        if not self._review_jobs:
            return
        self._save_review_notes()
        job = self._review_jobs[self._review_idx]
        src = (job.get("source") or "").lower()
        tracker = self.ctx.tracker
        config = self.ctx.config

        if src in ("linkedin", "linkedin_rss", "linkedin_manual"):
            easy_apply = tracker.is_easy_apply(job) if tracker else None
            if easy_apply is None:
                proceed = messagebox.askyesno(
                    "Easy Apply not confirmed",
                    "This job was scanned before Easy Apply detection was added, "
                    "so it's not known whether it supports LinkedIn Easy Apply.\n\n"
                    "If the job doesn't have Easy Apply, the browser will open "
                    "but won't be able to submit automatically.\n\n"
                    "Try anyway?",
                )
                if not proceed:
                    return

        self._auto_apply_btn.config(state="disabled")
        self._auto_apply_status.config(text="Opening browser…", fg=TEXT2)

        def run():
            try:
                if src == "reed":
                    from reed_apply import ReedApplicant
                    applicant = ReedApplicant(config, headless=False)
                    submitted = applicant.apply(job)
                elif src in ("linkedin", "linkedin_rss", "linkedin_manual"):
                    from linkedin_apply import LinkedInApplicant
                    applicant = LinkedInApplicant(config, headless=False)
                    submitted = applicant.apply(job)
                else:
                    submitted = False

                if submitted:
                    tracker.update_status(job["id"], "approved", "Approved via UI review")
                    tracker.update_status(job["id"], "submitted", f"Auto-submitted via {src} apply")
                    self.frame.after(0, lambda: self._auto_apply_done(job, platform=src, success=True))
                else:
                    self.frame.after(0, lambda: self._auto_apply_done(job, platform=src, success=False))
            except Exception as e:
                err = str(e)
                self.frame.after(0, lambda: self._auto_apply_done(job, platform=src, success=False, error=err))

        threading.Thread(target=run, daemon=True).start()

    def _auto_apply_done(self, job: dict, success: bool, platform: str = "", error: str = ""):
        session = self.ctx.session
        if session:
            session.record_apply(job, platform or "unknown", success)
        self._auto_apply_btn.config(state="normal")
        if success:
            self._auto_apply_status.config(text="✓ Submitted!", fg=GREEN)
            self._review_jobs.pop(self._review_idx)
            if self._review_idx >= len(self._review_jobs):
                self._review_idx = max(0, len(self._review_jobs) - 1)
            self._show_review_job()
        elif error:
            self._auto_apply_status.config(text=f"Error: {error}", fg=RED)
        else:
            self._auto_apply_status.config(
                text="No Easy Apply found — apply manually on LinkedIn.", fg=AMBER
            )

    def _review_skip(self):
        if not self._review_jobs:
            return
        self._save_review_notes()
        job = self._review_jobs[self._review_idx]
        self.ctx.tracker.update_status(job["id"], "skipped", "Skipped via UI review")
        self._review_jobs.pop(self._review_idx)
        if self._review_idx >= len(self._review_jobs):
            self._review_idx = max(0, len(self._review_jobs) - 1)
        self._show_review_job()

    def _review_next(self):
        self._save_review_notes()
        if self._review_jobs and self._review_idx < len(self._review_jobs) - 1:
            self._review_idx += 1
            self._show_review_job()

    def _review_prev(self):
        self._save_review_notes()
        if self._review_idx > 0:
            self._review_idx -= 1
            self._show_review_job()

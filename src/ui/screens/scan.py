"""
ui/screens/scan.py
==================
ScanScreen — browse scored jobs, select for tailoring, score/tailor actions.
"""

import sys
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox
import threading
from datetime import datetime

from ui.constants import (
    BG, BG2, CARD, BORDER, TEXT, TEXT2, BLUE, BLUE_LT,
    GREEN, GREEN_LT, AMBER, AMBER_LT, RED, RED_LT,
    FONT, FONT_SM, FONT_LG, FONT_HEAD, FONT_FAMILY,
)
from ui.context import AppContext
from ui.constants import _LogCapture
from ui.utils import export_to_excel
from ui.screens.base import BaseScreen


class ScanScreen(BaseScreen):
    def __init__(self, parent: tk.Frame, ctx: AppContext):
        super().__init__(parent, ctx)
        self._screen_all_jobs = []
        self._screen_sort_col = None
        self._screen_sort_asc = True
        self._screen_search_var = tk.StringVar()
        self._screen_high_only = tk.BooleanVar(value=False)
        self._screen_vars = {}
        self._build(self.frame)

    def _build(self, parent: tk.Frame):
        # Header
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill="x", padx=32, pady=(28, 4))
        tk.Label(hdr, text="Screen jobs", font=FONT_HEAD, bg=BG, fg=TEXT).pack(side="left")
        self._screen_counter = tk.Label(hdr, text="", font=FONT_SM, bg=BG, fg=TEXT2)
        self._screen_counter.pack(side="left", padx=14)

        tk.Label(parent,
                 text="Tick the jobs you want to apply for, then click Score selected (~$0.01 each). No money spent until you click Score.",
                 font=FONT_SM, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", padx=32, pady=(0, 8))

        # Toolbar row 1
        toolbar = tk.Frame(parent, bg=BG)
        toolbar.pack(fill="x", padx=32, pady=(0, 4))
        tk.Button(toolbar, text="Select all", font=(FONT_FAMILY, 11, "bold"), bg=BG2, fg=TEXT,
                  relief="flat", padx=10, pady=4, activebackground=BORDER, activeforeground=TEXT,
                  command=self._screen_select_all).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="Deselect all", font=(FONT_FAMILY, 11, "bold"), bg=BG2, fg=TEXT,
                  relief="flat", padx=10, pady=4, activebackground=BORDER, activeforeground=TEXT,
                  command=self._screen_deselect_all).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="Refresh", font=(FONT_FAMILY, 11, "bold"), bg=BG2, fg=TEXT,
                  relief="flat", padx=10, pady=4, activebackground=BORDER, activeforeground=TEXT,
                  command=self._refresh_screen).pack(side="left", padx=(0, 16))
        tk.Button(toolbar, text="Export to Excel", font=(FONT_FAMILY, 11, "bold"), bg=GREEN_LT, fg=GREEN,
                  relief="flat", padx=10, pady=4,
                  command=self._export_screen).pack(side="left", padx=(0, 6))

        tk.Label(toolbar, text="Search:", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left")
        search_entry = tk.Entry(toolbar, textvariable=self._screen_search_var,
                                font=FONT_SM, width=20, relief="solid", bd=1, bg=CARD)
        search_entry.pack(side="left", padx=(4, 4), ipady=3)
        self._screen_search_var.trace_add("write", lambda *_: self._apply_screen_filter())
        tk.Button(toolbar, text="✕", font=FONT_SM, bg=BG2, fg=TEXT2, relief="flat",
                  padx=4, command=lambda: self._screen_search_var.set("")).pack(side="left")

        # Toolbar row 2: filter chips
        filter_bar = tk.Frame(parent, bg=BG)
        filter_bar.pack(fill="x", padx=32, pady=(0, 6))

        tk.Label(filter_bar, text="Filter:", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left", padx=(0, 6))

        self._high_only_btn = tk.Button(
            filter_bar, text="⭐  High ≥70% only",
            font=(FONT_FAMILY, 11, "bold"), bg=BG2, fg=TEXT,
            relief="flat", padx=10, pady=3,
            activebackground=GREEN_LT, activeforeground=GREEN,
            command=self._toggle_high_only
        )
        self._high_only_btn.pack(side="left", padx=(0, 6))

        self._show_filtered_var = tk.BooleanVar(value=False)
        tk.Checkbutton(filter_bar, text="Show filtered & hidden jobs",
                       variable=self._show_filtered_var,
                       font=FONT_SM, bg=BG, fg=TEXT2, activebackground=BG,
                       command=self._refresh_screen).pack(side="left", padx=(8, 0))

        # Scoring summary bar
        self._screen_summary_bar = tk.Frame(parent, bg=BG2)
        self._screen_summary_bar.pack(fill="x", padx=32, pady=(0, 4))

        # Scrollable job list
        list_frame = tk.Frame(parent, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=32)

        self._screen_canvas = tk.Canvas(list_frame, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self._screen_canvas.yview)
        self._screen_inner = tk.Frame(self._screen_canvas, bg=BG)
        self._screen_inner.bind(
            "<Configure>",
            lambda e: self._screen_canvas.configure(scrollregion=self._screen_canvas.bbox("all"))
        )
        self._screen_canvas.create_window((0, 0), window=self._screen_inner, anchor="nw")
        self._screen_canvas.configure(yscrollcommand=vsb.set)
        self._screen_canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._screen_canvas.bind_all("<MouseWheel>",
            lambda e: self._screen_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Bottom action bar
        action_bar = tk.Frame(parent, bg=BG2)
        action_bar.pack(fill="x", side="bottom")
        self._score_btn = tk.Button(
            action_bar,
            text="📊  Score selected (~$0.01 each)",
            font=(FONT_FAMILY, 13, "bold"),
            bg=BLUE, fg=TEXT,
            padx=20, pady=10,
            command=self._score_selected
        )
        self._score_btn.pack(side="right", padx=(8, 16), pady=8)

        self._tailor_btn = tk.Button(
            action_bar,
            text="✍  Tailor scored jobs (~$0.05 each)",
            font=(FONT_FAMILY, 13, "bold"),
            bg=GREEN, fg="black", relief="flat",
            padx=20, pady=10,
            command=self._tailor_selected
        )
        self._tailor_btn.pack(side="right", padx=16, pady=8)
        self._screen_status_label = tk.Label(
            action_bar, text="", font=FONT_SM, bg=BG2, fg=TEXT2
        )
        self._screen_status_label.pack(side="left", padx=16, pady=8)

    def refresh(self):
        self._refresh_screen()

    def _bind_tooltip(self, widget, text: str):
        tip = None

        def show(event):
            nonlocal tip
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            lbl = tk.Label(tip, text=text, font=FONT_SM, bg="#FFFBE6",
                           fg=TEXT, relief="solid", bd=1,
                           wraplength=400, justify="left", padx=8, pady=6)
            lbl.pack()

        def hide(event):
            nonlocal tip
            if tip:
                tip.destroy()
                tip = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _update_screen_summary(self, all_db_jobs: list = None):
        if not hasattr(self, "_screen_summary_bar"):
            return
        for w in self._screen_summary_bar.winfo_children():
            w.destroy()

        tracker = self.ctx.tracker
        config = self.ctx.config
        if all_db_jobs is None and tracker:
            all_db_jobs = tracker.get_all_jobs()
        if not all_db_jobs:
            return

        scored_active = [j for j in all_db_jobs
                         if j["status"] == "scored" and j.get("match_score") is not None]
        scored_low    = [j for j in all_db_jobs
                         if j["status"] == "filtered" and j.get("match_score") is not None]
        dismissed     = sum(1 for j in all_db_jobs if j["status"] == "dismissed")

        if not scored_active and not scored_low:
            return

        min_score = getattr(config, "min_match_score", 65) if config else 65
        high   = sum(1 for j in scored_active if j["match_score"] >= 70)
        medium = sum(1 for j in scored_active if min_score <= j["match_score"] < 70)
        low    = len(scored_low)

        bar = self._screen_summary_bar
        tk.Label(bar, text="  Scoring summary:",
                 font=(FONT_FAMILY, 10, "bold"), bg=BG2, fg=TEXT2).pack(side="left", padx=(4, 8))

        if high:
            tk.Label(bar, text=f"● {high} high (≥70%)",
                     font=(FONT_FAMILY, 10), bg=BG2, fg=GREEN).pack(side="left", padx=(0, 10))
        if medium:
            tk.Label(bar, text=f"● {medium} medium ({min_score}–69%)",
                     font=(FONT_FAMILY, 10), bg=BG2, fg=AMBER).pack(side="left", padx=(0, 10))
        if low:
            tk.Label(bar, text=f"● {low} low (<{min_score}%) — auto-hidden",
                     font=(FONT_FAMILY, 10), bg=BG2, fg=RED).pack(side="left", padx=(0, 10))
        if dismissed:
            tk.Label(bar, text=f"● {dismissed} dismissed by you",
                     font=(FONT_FAMILY, 10), bg=BG2, fg=TEXT2).pack(side="left", padx=(0, 10))
        if low or dismissed:
            tk.Label(bar, text="— tick 'Show filtered & hidden' to reveal",
                     font=(FONT_FAMILY, 10), bg=BG2, fg=TEXT2).pack(side="left")

    def _dismiss_job(self, job_id: int):
        tracker = self.ctx.tracker
        if not tracker:
            return
        tracker.update_status(job_id, "dismissed", "Dismissed by user in Screen Jobs")
        self._screen_all_jobs = [j for j in self._screen_all_jobs if j["id"] != job_id]
        if job_id in self._screen_vars:
            del self._screen_vars[job_id]
        self._apply_screen_filter()
        self._update_screen_summary()

    def _refresh_screen(self):
        tracker = self.ctx.tracker
        if not tracker:
            return

        for w in self._screen_inner.winfo_children():
            w.destroy()
        self._screen_vars.clear()

        loading = tk.Label(self._screen_inner, text="⏳  Loading jobs…",
                           font=FONT_LG, bg=BG, fg=TEXT2)
        loading.pack(pady=60)
        self._screen_inner.update_idletasks()
        self._screen_canvas.update_idletasks()

        show_filtered = self._show_filtered_var.get()

        all_db_jobs = tracker.get_all_jobs()
        if show_filtered:
            jobs = [j for j in all_db_jobs if j["status"] in
                    ("discovered", "score_me", "scored", "filtered", "dismissed")]
        else:
            jobs = [j for j in all_db_jobs if j["status"] in
                    ("discovered", "score_me", "scored")]

        discovered = sum(1 for j in jobs if j["status"] == "discovered")
        scored = sum(1 for j in jobs if j["status"] == "scored")
        self._screen_counter.config(text=f"{len(jobs)} jobs — {discovered} to review, {scored} scored")
        self._update_screen_summary(all_db_jobs)

        for w in self._screen_inner.winfo_children():
            w.destroy()

        if not jobs:
            tk.Label(self._screen_inner,
                     text="No jobs yet. Click 'Scan for jobs' to start.",
                     font=FONT_SM, bg=BG, fg=TEXT2).pack(pady=40)
            return

        col_hdr = tk.Frame(self._screen_inner, bg=BG2)
        col_hdr.pack(fill="x", pady=(0, 2))
        tk.Label(col_hdr, text="", width=3, bg=BG2).pack(side="left")

        col_defs = [
            ("Role",     "title",        30),
            ("Employer", "employer",     18),
            ("Match",    "match_score",   7),
            ("Salary",   "salary",       14),
            ("Source",   "source",       10),
        ]
        for label, col_key, width in col_defs:
            def make_sort(k=col_key):
                def _sort():
                    if self._screen_sort_col == k:
                        self._screen_sort_asc = not self._screen_sort_asc
                    else:
                        self._screen_sort_col = k
                        self._screen_sort_asc = True
                    self._apply_screen_filter()
                return _sort
            arrow = ""
            if self._screen_sort_col == col_key:
                arrow = " ▲" if self._screen_sort_asc else " ▼"
            btn = tk.Button(col_hdr, text=label + arrow, width=width, anchor="w",
                            font=(FONT_FAMILY, 11, "bold"), bg=BG2, fg=TEXT2,
                            relief="flat", bd=0, activebackground=BORDER,
                            command=make_sort())
            btn.pack(side="left")

        tk.Frame(self._screen_inner, bg=BORDER, height=1).pack(fill="x")

        self._screen_all_jobs = jobs
        self._apply_screen_filter()

    def _apply_screen_filter(self):
        if not hasattr(self, "_screen_all_jobs"):
            return
        query = self._screen_search_var.get().lower().strip()
        jobs = self._screen_all_jobs

        if getattr(self, "_screen_high_only", tk.BooleanVar()).get():
            jobs = [j for j in jobs if j.get("match_score") is not None and j["match_score"] >= 70]

        if query:
            jobs = [j for j in jobs if
                    query in (j.get("title") or "").lower() or
                    query in (j.get("employer") or "").lower() or
                    query in (j.get("salary") or "").lower() or
                    query in (j.get("source") or "").lower() or
                    query in (j.get("location") or "").lower() or
                    query in (j.get("description") or "").lower()]

        if self._screen_sort_col:
            def sort_key(j):
                v = j.get(self._screen_sort_col)
                if v is None:
                    return (1, "")
                return (0, v) if isinstance(v, (int, float)) else (0, str(v).lower())
            jobs = sorted(jobs, key=sort_key, reverse=not self._screen_sort_asc)

        existing_checks = {jid: var.get() for jid, var in self._screen_vars.items()}

        children = self._screen_inner.winfo_children()
        for w in children[2:]:
            w.destroy()
        self._screen_vars.clear()

        if not jobs:
            high_only = getattr(self, "_screen_high_only", tk.BooleanVar()).get()
            msg = ("No high-scoring jobs (≥70%) found yet. Score some jobs first, or turn off the filter."
                   if high_only else "No jobs match your search.")
            tk.Label(self._screen_inner, text=msg,
                     font=FONT_SM, bg=BG, fg=TEXT2).pack(pady=20)
        else:
            for job in jobs:
                self._add_screen_row(job)
                if job["id"] in existing_checks:
                    self._screen_vars[job["id"]].set(existing_checks[job["id"]])

        # Update sort arrows
        col_defs = [("Role","title",30),("Employer","employer",18),
                    ("Match","match_score",7),("Salary","salary",14),("Source","source",10)]
        if children:
            col_hdr = children[0]
            hdr_btns = [w for w in col_hdr.winfo_children() if isinstance(w, tk.Button)]
            for btn, (label, col_key, _) in zip(hdr_btns, col_defs):
                arrow = ""
                if self._screen_sort_col == col_key:
                    arrow = " ▲" if self._screen_sort_asc else " ▼"
                btn.config(text=label + arrow)

        self._screen_status_label.config(
            text=f"{sum(v.get() for v in self._screen_vars.values())} selected"
        )
        self._screen_canvas.update_idletasks()

    def _add_screen_row(self, job: dict):
        job_id  = job["id"]
        score   = job.get("match_score")
        status  = job.get("status", "")
        is_filtered = status in ("filtered", "dismissed")

        row_bg = BG if not is_filtered else BG2

        row = tk.Frame(self._screen_inner, bg=row_bg, pady=3)
        row.pack(fill="x")

        if not is_filtered:
            hide_btn = tk.Button(
                row, text="✕ Hide",
                font=(FONT_FAMILY, 9, "bold"), bg=RED_LT, fg=RED,
                relief="flat", padx=8, pady=2,
                activebackground="#F5CCCC", activeforeground=RED, cursor="hand2",
                command=lambda jid=job_id: self._dismiss_job(jid)
            )
            hide_btn.pack(side="right", padx=(0, 8))

        var = tk.BooleanVar(value=False)
        self._screen_vars[job_id] = var
        cb = tk.Checkbutton(row, variable=var, bg=row_bg,
                            activebackground=row_bg,
                            command=self._update_screen_count)
        cb.pack(side="left", padx=(4, 0))

        if score is None:
            score_text = "—"
            score_fg, score_bg = TEXT2, BG2
        elif score >= 70:
            score_text = f"{score}%"
            score_fg, score_bg = GREEN, GREEN_LT
        elif score >= 55:
            score_text = f"{score}%"
            score_fg, score_bg = AMBER, AMBER_LT
        else:
            score_text = f"{score}%"
            score_fg, score_bg = RED, RED_LT

        title    = (job.get("title") or "—")[:48]
        employer = (job.get("employer") or "—")[:28]
        salary   = (job.get("salary") or "—")[:22]
        source   = (job.get("source") or "—").replace("_", " ")[:16]
        url      = job.get("url") or ""

        title_fg   = TEXT2 if is_filtered else BLUE
        title_font = (FONT_FAMILY, 11, "underline") if url and not is_filtered else FONT_SM

        title_lbl = tk.Label(row, text=title, width=30, anchor="w",
                             font=title_font, bg=row_bg, fg=title_fg, cursor="hand2" if url else "")
        title_lbl.pack(side="left")
        if url and not is_filtered:
            title_lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            title_lbl.bind("<Enter>", lambda e, l=title_lbl: l.config(fg=RED))
            title_lbl.bind("<Leave>", lambda e, l=title_lbl: l.config(fg=title_fg))

        tk.Label(row, text=employer, width=18, anchor="w", font=FONT_SM, bg=row_bg, fg=TEXT2).pack(side="left")

        reason_text = (job.get("match_reason") or "").strip()
        badge = tk.Label(row, text=score_text, font=(FONT_FAMILY, 10, "bold"),
                         bg=score_bg, fg=score_fg, padx=6, pady=1,
                         cursor="question_arrow" if reason_text else "")
        badge.pack(side="left", padx=(0, 8))
        if reason_text:
            self._bind_tooltip(badge, reason_text)

        tk.Label(row, text=salary, width=14, anchor="w", font=FONT_SM, bg=row_bg, fg=TEXT2).pack(side="left")
        tk.Label(row, text=source, width=10, anchor="w", font=FONT_SM, bg=row_bg, fg=TEXT2).pack(side="left")

        if is_filtered:
            reason = (job.get("match_reason") or status)[:40]
            tk.Label(row, text=f"[{reason}]", font=(FONT_FAMILY, 10), bg=row_bg, fg=TEXT2).pack(side="left", padx=8)

        tk.Frame(self._screen_inner, bg=BORDER, height=1).pack(fill="x")

    def _toggle_high_only(self):
        val = not self._screen_high_only.get()
        self._screen_high_only.set(val)
        if val:
            self._high_only_btn.config(bg=GREEN_LT, fg=GREEN)
        else:
            self._high_only_btn.config(bg=BG2, fg=TEXT)
        self._apply_screen_filter()

    def _update_screen_count(self):
        n = sum(v.get() for v in self._screen_vars.values())
        self._screen_status_label.config(text=f"{n} selected")

    def _screen_select_all(self):
        for var in self._screen_vars.values():
            var.set(True)
        self._update_screen_count()

    def _screen_deselect_all(self):
        for var in self._screen_vars.values():
            var.set(False)
        self._update_screen_count()

    def _score_selected(self):
        selected_ids = [jid for jid, var in self._screen_vars.items() if var.get()]
        if not selected_ids:
            messagebox.showinfo("Nothing selected", "Tick at least one job to score.")
            return

        tracker = self.ctx.tracker
        config = self.ctx.config

        to_score = []
        for job_id in selected_ids:
            job = tracker.get_job(job_id)
            if job and job["status"] == "discovered":
                to_score.append(job_id)

        if not to_score:
            messagebox.showinfo("Nothing to score",
                "Selected jobs have already been scored or are filtered.\n"
                "Only tick jobs with blue badges to score them.")
            return

        cost_est = len(to_score) * 0.01
        if not messagebox.askyesno(
            "Score jobs",
            f"Score {len(to_score)} job(s)?\n\n"
            f"Estimated cost: ~${cost_est:.2f} in Claude API credits.\n\n"
            f"Jobs scoring below {config.min_match_score}% will be filtered automatically."
        ):
            return

        for job_id in to_score:
            tracker.update_status(job_id, "score_me", "Selected for scoring in UI")

        self._last_scored_ids = to_score
        self._score_btn.config(text="Scoring…", state="disabled", bg="#555")
        self.frame.update_idletasks()

        self.ctx.scan_log_lines.append(
            f"── Scoring started {datetime.now().strftime('%d %b %Y %H:%M:%S')} ──"
        )

        append_log = self.ctx.append_log_line

        def score_thread():
            capture = _LogCapture(sys.__stdout__, on_line=append_log)
            old_stdout = sys.stdout
            sys.stdout = capture
            try:
                from main import run_score_selected
                run_score_selected(config, tracker)
            except Exception as e:
                err = str(e)
                if append_log:
                    append_log(f"ERROR: {err}")
                self.frame.after(0, lambda: messagebox.showerror("Scoring failed", err))
            finally:
                sys.stdout = old_stdout
                if append_log:
                    append_log(f"── Scoring finished {datetime.now().strftime('%H:%M:%S')} ──")
                self.frame.after(0, self._score_done)

        threading.Thread(target=score_thread, daemon=True).start()

    def _score_done(self):
        self._score_btn.config(text="📊  Score selected (~$0.01 each)",
                               state="normal", bg=BLUE)
        self._refresh_screen()
        tracker = self.ctx.tracker
        config = self.ctx.config
        session = self.ctx.session
        batch_ids = set(getattr(self, "_last_scored_ids", []))
        batch_jobs = [tracker.get_job(jid) for jid in batch_ids if tracker.get_job(jid)]
        if session:
            session.record_scored(batch_jobs)
        scored   = [j for j in batch_jobs if j["status"] == "scored"]
        filtered = [j for j in batch_jobs if j["status"] == "filtered"]
        if scored or filtered:
            min_score = getattr(config, "min_match_score", 65) if config else 65
            high   = sum(1 for j in scored if j.get("match_score", 0) >= 70)
            medium = sum(1 for j in scored if min_score <= j.get("match_score", 0) < 70)
            low    = len(filtered)
            lines = [f"Scoring complete — {len(scored)} job(s) passed threshold.\n"]
            if high:
                lines.append(f"  ✓  {high} high match (≥70%) — strong candidates")
            if medium:
                lines.append(f"  ~  {medium} medium match ({min_score}–69%) — worth considering")
            if low:
                lines.append(f"  ✗  {low} low score (<{min_score}%) — auto-hidden")
            lines.append("\nReview scores below. Tick jobs to tailor and click 'Tailor scored jobs'.")
            messagebox.showinfo("Scoring complete", "\n".join(lines))

    def _tailor_selected(self):
        selected_ids = [jid for jid, var in self._screen_vars.items() if var.get()]
        if not selected_ids:
            messagebox.showinfo("Nothing selected", "Tick at least one job to tailor.")
            return

        tracker = self.ctx.tracker
        config = self.ctx.config

        to_tailor = []
        for job_id in selected_ids:
            job = tracker.get_job(job_id)
            if job and job["status"] == "scored":
                to_tailor.append(job_id)

        if not to_tailor:
            messagebox.showinfo("Nothing to tailor",
                "Please score jobs first before tailoring.\n"
                "Tick discovered jobs and click 'Score selected' first.")
            return

        cost_est = len(to_tailor) * 0.06
        if not messagebox.askyesno(
            "Tailor applications",
            f"Tailor {len(to_tailor)} application(s)?\n\n"
            f"Estimated cost: ~${cost_est:.2f} in Claude API credits.\n\n"
            f"CV and cover letter will be generated for each."
        ):
            return

        for job_id in to_tailor:
            tracker.update_status(job_id, "tailoring", "Selected in screening UI")
        self._last_tailored_ids = to_tailor

        self._tailor_btn.config(text="Tailoring…", state="disabled", bg="#555")
        self.frame.update_idletasks()

        self.ctx.scan_log_lines.append(
            f"── Tailoring started {datetime.now().strftime('%d %b %Y %H:%M:%S')} ──"
        )

        append_log = self.ctx.append_log_line

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
                    append_log(f"── Tailoring finished {datetime.now().strftime('%H:%M:%S')} ──")
                self.frame.after(0, self._tailor_done)

        threading.Thread(target=tailor_thread, daemon=True).start()

    def _tailor_done(self):
        self._tailor_btn.config(text="✍  Tailor selected jobs", state="normal", bg=BLUE)
        self._refresh_screen()
        if self.ctx.refresh_review:
            self.ctx.refresh_review()
        tracker = self.ctx.tracker
        session = self.ctx.session
        tailored_ids = set(getattr(self, "_last_tailored_ids", []))
        tailored_jobs = [tracker.get_job(jid) for jid in tailored_ids if tracker.get_job(jid)]
        if session:
            session.record_tailored(tailored_jobs)
        n = len(tracker.get_pending_review()) if tracker else 0
        if n:
            messagebox.showinfo("Done", f"{n} application(s) tailored.\n\nGo to Review queue to check them.")
            if self.ctx.show_screen:
                self.ctx.show_screen("review")

    def _export_screen(self):
        if not hasattr(self, "_screen_all_jobs") or not self._screen_all_jobs:
            messagebox.showinfo("Export", "No data to export.")
            return

        query = self._screen_search_var.get().lower().strip()
        high_only = getattr(self, "_screen_high_only", tk.BooleanVar()).get()
        jobs = self._screen_all_jobs

        if high_only:
            jobs = [j for j in jobs if j.get("match_score") is not None and j["match_score"] >= 70]
        if query:
            jobs = [j for j in jobs if
                    query in (j.get("title") or "").lower() or
                    query in (j.get("employer") or "").lower() or
                    query in (j.get("salary") or "").lower() or
                    query in (j.get("source") or "").lower() or
                    query in (j.get("location") or "").lower() or
                    query in (j.get("description") or "").lower()]

        headers = ["ID", "Role", "Employer", "Location", "Salary", "Match %", "Status", "Source", "Found", "URL"]
        rows = []
        for j in jobs:
            rows.append([
                j.get("id"),
                j.get("title") or "",
                j.get("employer") or "",
                j.get("location") or "",
                j.get("salary") or "",
                j.get("match_score") or "",
                (j.get("status") or "").replace("_", " ").title(),
                j.get("source") or "",
                (j.get("date_found") or "")[:10],
                j.get("url") or "",
            ])

        export_to_excel(headers, rows, default_name="screen_jobs_export.xlsx")

    def _run_refilter(self):
        config = self.ctx.config
        tracker = self.ctx.tracker
        if not config or not tracker:
            return

        def refilter_thread():
            try:
                from main import run_refilter
                run_refilter(config, tracker)
            except Exception as e:
                self.frame.after(0, lambda: messagebox.showerror("Refilter failed", str(e)))
            finally:
                self.frame.after(0, self._refresh_screen)
                if self.ctx.refresh_dashboard:
                    self.frame.after(0, self.ctx.refresh_dashboard)

        threading.Thread(target=refilter_thread, daemon=True).start()
        if self.ctx.show_screen:
            self.ctx.show_screen("screen")
        messagebox.showinfo("Refiltering", "Re-applying filters to discovered jobs...\nThe list will update when done.")

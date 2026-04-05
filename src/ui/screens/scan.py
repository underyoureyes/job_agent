"""
ui/screens/scan.py
==================
ScanScreen — browse scored jobs, select for tailoring, score/tailor actions.
Uses ttk.Treeview for fast rendering; filtering is delete+reinsert, not
widget-destroy/recreate, so it stays responsive with hundreds of rows.
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
        self._screen_all_jobs  = []
        self._screen_job_map   = {}          # job_id -> job dict
        self._selected_ids     = set()       # currently checked job IDs
        self._screen_sort_col  = None
        self._screen_sort_asc  = True
        self._screen_search_var = tk.StringVar()
        self._screen_high_only  = tk.BooleanVar(value=False)
        self._show_filtered_var = tk.BooleanVar(value=False)
        self._tooltip_win       = None
        self._build(self.frame)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self, parent: tk.Frame):
        # Header
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill="x", padx=32, pady=(28, 4))
        tk.Label(hdr, text="Screen jobs", font=FONT_HEAD, bg=BG, fg=TEXT).pack(side="left")
        self._screen_counter = tk.Label(hdr, text="", font=FONT_SM, bg=BG, fg=TEXT2)
        self._screen_counter.pack(side="left", padx=14)

        tk.Label(parent,
                 text="Tick the jobs you want to apply for, then click Score selected (~$0.01 each). "
                      "No money spent until you click Score.",
                 font=FONT_SM, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", padx=32, pady=(0, 8))

        # Toolbar
        toolbar = tk.Frame(parent, bg=BG)
        toolbar.pack(fill="x", padx=32, pady=(0, 4))

        for label, cmd, bg_col, fg_col in [
            ("Select all",    self._screen_select_all,   BG2,      TEXT),
            ("Deselect all",  self._screen_deselect_all, BG2,      TEXT),
            ("Refresh",       self._refresh_screen,      BG2,      TEXT),
            ("Hide selected", self._hide_selected,       RED_LT,   RED),
            ("Export to Excel", self._export_screen,     GREEN_LT, GREEN),
        ]:
            tk.Button(toolbar, text=label, font=(FONT_FAMILY, 11, "bold"),
                      bg=bg_col, fg=fg_col, relief="flat", padx=10, pady=4,
                      activebackground=BORDER, activeforeground=fg_col,
                      command=cmd).pack(side="left", padx=(0, 6))

        tk.Label(toolbar, text="Search:", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left", padx=(8, 0))
        tk.Entry(toolbar, textvariable=self._screen_search_var,
                 font=FONT_SM, width=20, relief="solid", bd=1, bg=CARD
                 ).pack(side="left", padx=(4, 2), ipady=3)
        self._screen_search_var.trace_add("write", lambda *_: self._apply_screen_filter())
        tk.Button(toolbar, text="✕", font=FONT_SM, bg=BG2, fg=TEXT2, relief="flat",
                  padx=4, command=lambda: self._screen_search_var.set("")).pack(side="left")

        # Filter chips
        filter_bar = tk.Frame(parent, bg=BG)
        filter_bar.pack(fill="x", padx=32, pady=(0, 6))
        tk.Label(filter_bar, text="Filter:", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left", padx=(0, 6))

        self._high_only_btn = tk.Button(
            filter_bar, text="⭐  High ≥70% only",
            font=(FONT_FAMILY, 11, "bold"), bg=BG2, fg=TEXT,
            relief="flat", padx=10, pady=3,
            activebackground=GREEN_LT, activeforeground=GREEN,
            command=self._toggle_high_only,
        )
        self._high_only_btn.pack(side="left", padx=(0, 6))

        tk.Checkbutton(filter_bar, text="Show filtered & hidden jobs",
                       variable=self._show_filtered_var,
                       font=FONT_SM, bg=BG, fg=TEXT2, activebackground=BG,
                       command=self._refresh_screen).pack(side="left", padx=(8, 0))

        # Scoring summary bar
        self._screen_summary_bar = tk.Frame(parent, bg=BG2)
        self._screen_summary_bar.pack(fill="x", padx=32, pady=(0, 4))

        # Treeview
        list_frame = tk.Frame(parent, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=32)

        cols = ("sel", "title", "employer", "match", "salary", "source")
        self._tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                                   selectmode="none")

        self._tree.heading("sel",      text="",         anchor="center")
        self._tree.heading("title",    text="Role",     anchor="w",
                           command=lambda: self._sort_col("title"))
        self._tree.heading("employer", text="Employer", anchor="w",
                           command=lambda: self._sort_col("employer"))
        self._tree.heading("match",    text="Match",    anchor="center",
                           command=lambda: self._sort_col("match_score"))
        self._tree.heading("salary",   text="Salary",   anchor="w",
                           command=lambda: self._sort_col("salary"))
        self._tree.heading("source",   text="Source",   anchor="w",
                           command=lambda: self._sort_col("source"))

        self._tree.column("sel",      width=36,  minwidth=36,  stretch=False, anchor="center")
        self._tree.column("title",    width=320, minwidth=180, stretch=True,  anchor="w")
        self._tree.column("employer", width=180, minwidth=100, stretch=False, anchor="w")
        self._tree.column("match",    width=72,  minwidth=60,  stretch=False, anchor="center")
        self._tree.column("salary",   width=145, minwidth=80,  stretch=False, anchor="w")
        self._tree.column("source",   width=115, minwidth=60,  stretch=False, anchor="w")

        self._tree.tag_configure("high",      foreground=GREEN)
        self._tree.tag_configure("medium",    foreground=AMBER)
        self._tree.tag_configure("low_score", foreground=RED)
        self._tree.tag_configure("grayed",    foreground=TEXT2)
        self._tree.tag_configure("checked",   background=BLUE_LT)
        self._tree.tag_configure("odd",       background=CARD)
        self._tree.tag_configure("even",      background=BG)

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<Button-1>",        self._on_tree_click)
        self._tree.bind("<Double-Button-1>", self._on_tree_double_click)
        self._tree.bind("<Motion>",          self._on_tree_motion)
        self._tree.bind("<Leave>",           self._hide_tooltip)
        self._tree.bind("<MouseWheel>",
            lambda e: self._tree.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # Bottom action bar
        action_bar = tk.Frame(parent, bg=BG2)
        action_bar.pack(fill="x", side="bottom")

        self._score_btn = tk.Button(
            action_bar, text="📊  Score selected (~$0.01 each)",
            font=(FONT_FAMILY, 13, "bold"), bg=BLUE, fg=TEXT,
            padx=20, pady=10, command=self._score_selected,
        )
        self._score_btn.pack(side="right", padx=(8, 16), pady=8)

        self._tailor_btn = tk.Button(
            action_bar, text="✍  Tailor scored jobs (~$0.05 each)",
            font=(FONT_FAMILY, 13, "bold"), bg=GREEN, fg="black",
            relief="flat", padx=20, pady=10, command=self._tailor_selected,
        )
        self._tailor_btn.pack(side="right", padx=16, pady=8)

        self._screen_status_label = tk.Label(
            action_bar, text="", font=FONT_SM, bg=BG2, fg=TEXT2,
        )
        self._screen_status_label.pack(side="left", padx=16, pady=8)

    # ── Tree interaction ──────────────────────────────────────────────────────

    def _on_tree_click(self, event):
        region = self._tree.identify_region(event.x, event.y)
        col    = self._tree.identify_column(event.x)
        iid    = self._tree.identify_row(event.y)
        if not iid or region != "cell" or col != "#1":
            return
        job_id = int(iid)
        job    = self._screen_job_map.get(job_id)
        if not job or job.get("status") in ("filtered", "dismissed"):
            return
        if job_id in self._selected_ids:
            self._selected_ids.discard(job_id)
        else:
            self._selected_ids.add(job_id)
        self._refresh_row(job_id)
        self._update_screen_count()

    def _on_tree_double_click(self, event):
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        job = self._screen_job_map.get(int(iid))
        if job and job.get("url"):
            webbrowser.open(job["url"])

    def _on_tree_motion(self, event):
        iid = self._tree.identify_row(event.y)
        if not iid:
            self._hide_tooltip()
            return
        job      = self._screen_job_map.get(int(iid))
        tip_text = (job.get("match_reason") or "").strip() if job else ""
        if tip_text:
            self._show_tooltip(event, tip_text)
        else:
            self._hide_tooltip()

    def _show_tooltip(self, event, text: str):
        if self._tooltip_win:
            self._tooltip_win.destroy()
        x = self._tree.winfo_rootx() + event.x + 16
        y = self._tree.winfo_rooty() + event.y + 16
        self._tooltip_win = tk.Toplevel(self._tree)
        self._tooltip_win.wm_overrideredirect(True)
        self._tooltip_win.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tooltip_win, text=text, font=FONT_SM, bg="#FFFBE6",
                 fg=TEXT, relief="solid", bd=1,
                 wraplength=420, justify="left", padx=8, pady=6).pack()

    def _hide_tooltip(self, event=None):
        if self._tooltip_win:
            self._tooltip_win.destroy()
            self._tooltip_win = None

    # ── Row tag helpers ───────────────────────────────────────────────────────

    def _row_tags(self, job: dict, row_index: int) -> tuple:
        score  = job.get("match_score")
        status = job.get("status", "")
        job_id = job["id"]

        parity = "odd" if row_index % 2 else "even"

        if status in ("filtered", "dismissed"):
            score_tag = "grayed"
        elif score is None:
            score_tag = ""
        elif score >= 70:
            score_tag = "high"
        elif score >= 55:
            score_tag = "medium"
        else:
            score_tag = "low_score"

        tags = tuple(t for t in (parity, score_tag) if t)
        if job_id in self._selected_ids:
            tags += ("checked",)
        return tags

    def _refresh_row(self, job_id: int):
        """Update a single row's checkbox symbol and tags after toggle."""
        job = self._screen_job_map.get(job_id)
        if not job:
            return
        try:
            children = self._tree.get_children()
            idx  = list(children).index(str(job_id))
            checked = job_id in self._selected_ids
            self._tree.set(str(job_id), "sel", "☑" if checked else "☐")
            self._tree.item(str(job_id), tags=self._row_tags(job, idx))
        except (ValueError, tk.TclError):
            pass

    # ── Data loading ──────────────────────────────────────────────────────────

    def refresh(self):
        self._refresh_screen()

    def _refresh_screen(self):
        tracker = self.ctx.tracker
        if not tracker:
            return

        all_db_jobs   = tracker.get_all_jobs()
        show_filtered = self._show_filtered_var.get()

        if show_filtered:
            jobs = [j for j in all_db_jobs if j["status"] in
                    ("discovered", "score_me", "scored", "filtered", "dismissed")]
        else:
            jobs = [j for j in all_db_jobs if j["status"] in
                    ("discovered", "score_me", "scored")]

        discovered = sum(1 for j in jobs if j["status"] == "discovered")
        scored     = sum(1 for j in jobs if j["status"] == "scored")
        self._screen_counter.config(
            text=f"{len(jobs)} jobs — {discovered} to review, {scored} scored")
        self._update_screen_summary(all_db_jobs)

        self._screen_all_jobs = jobs
        self._screen_job_map  = {j["id"]: j for j in jobs}
        self._selected_ids   &= self._screen_job_map.keys()   # drop stale selections

        self._apply_screen_filter()

    def _apply_screen_filter(self):
        if not hasattr(self, "_screen_all_jobs"):
            return

        query     = self._screen_search_var.get().lower().strip()
        high_only = self._screen_high_only.get()
        jobs      = self._screen_all_jobs

        if high_only:
            jobs = [j for j in jobs
                    if j.get("match_score") is not None and j["match_score"] >= 70]

        if query:
            jobs = [j for j in jobs if
                    query in (j.get("title")       or "").lower() or
                    query in (j.get("employer")    or "").lower() or
                    query in (j.get("salary")      or "").lower() or
                    query in (j.get("source")      or "").lower() or
                    query in (j.get("location")    or "").lower() or
                    query in (j.get("description") or "").lower()]

        if self._screen_sort_col:
            def sort_key(j):
                v = j.get(self._screen_sort_col)
                return (1, "") if v is None else \
                       (0, v) if isinstance(v, (int, float)) else (0, str(v).lower())
            jobs = sorted(jobs, key=sort_key, reverse=not self._screen_sort_asc)

        self._populate_tree(jobs)
        self._update_column_arrows()
        self._update_screen_count()

    def _populate_tree(self, jobs: list):
        self._tree.delete(*self._tree.get_children())
        for i, job in enumerate(jobs):
            job_id = job["id"]
            score  = job.get("match_score")
            status = job.get("status", "")

            match_str = f"{score}%" if score is not None else "—"
            title     = (job.get("title")    or "—")[:60]
            employer  = (job.get("employer") or "—")[:32]
            salary    = (job.get("salary")   or "—")[:26]
            source    = (job.get("source")   or "—").replace("_", " ")[:18]

            if status in ("filtered", "dismissed"):
                reason = (job.get("match_reason") or status)[:30]
                title  = f"{title}  [{reason}]"
                sel    = ""
            else:
                sel = "☑" if job_id in self._selected_ids else "☐"

            self._tree.insert(
                "", "end",
                iid=str(job_id),
                values=(sel, title, employer, match_str, salary, source),
                tags=self._row_tags(job, i),
            )

    # ── Column sort ───────────────────────────────────────────────────────────

    def _sort_col(self, col_key: str):
        if self._screen_sort_col == col_key:
            self._screen_sort_asc = not self._screen_sort_asc
        else:
            self._screen_sort_col = col_key
            self._screen_sort_asc = True
        self._apply_screen_filter()

    def _update_column_arrows(self):
        mapping = {
            "title":       ("title",    "Role"),
            "employer":    ("employer", "Employer"),
            "match_score": ("match",    "Match"),
            "salary":      ("salary",   "Salary"),
            "source":      ("source",   "Source"),
        }
        for key, (col_id, label) in mapping.items():
            arrow = ""
            if self._screen_sort_col == key:
                arrow = " ▲" if self._screen_sort_asc else " ▼"
            self._tree.heading(col_id, text=label + arrow)

    # ── Selection ─────────────────────────────────────────────────────────────

    def _screen_select_all(self):
        for job in self._screen_all_jobs:
            if job.get("status") not in ("filtered", "dismissed"):
                self._selected_ids.add(job["id"])
        self._apply_screen_filter()

    def _screen_deselect_all(self):
        self._selected_ids.clear()
        self._apply_screen_filter()

    def _update_screen_count(self):
        self._screen_status_label.config(text=f"{len(self._selected_ids)} selected")

    def _hide_selected(self):
        if not self._selected_ids:
            messagebox.showinfo("Nothing selected", "Tick at least one job to hide.")
            return
        tracker = self.ctx.tracker
        if not tracker:
            return
        for job_id in list(self._selected_ids):
            tracker.update_status(job_id, "dismissed", "Dismissed by user in Screen Jobs")
        self._selected_ids.clear()
        self._refresh_screen()
        self._update_screen_summary()

    # ── Scoring summary bar ───────────────────────────────────────────────────

    def _update_screen_summary(self, all_db_jobs: list = None):
        if not hasattr(self, "_screen_summary_bar"):
            return
        for w in self._screen_summary_bar.winfo_children():
            w.destroy()

        tracker = self.ctx.tracker
        config  = self.ctx.config
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

    # ── Score ─────────────────────────────────────────────────────────────────

    def _score_selected(self):
        if not self._selected_ids:
            messagebox.showinfo("Nothing selected", "Tick at least one job to score.")
            return

        tracker = self.ctx.tracker
        config  = self.ctx.config

        to_score = [jid for jid in self._selected_ids
                    if self._screen_job_map.get(jid, {}).get("status") == "discovered"]

        if not to_score:
            messagebox.showinfo("Nothing to score",
                "Selected jobs have already been scored or are filtered.\n"
                "Only tick jobs with no match score to score them.")
            return

        cost_est = len(to_score) * 0.01
        if not messagebox.askyesno(
            "Score jobs",
            f"Score {len(to_score)} job(s)?\n\n"
            f"Estimated cost: ~${cost_est:.2f} in Claude API credits.\n\n"
            f"Jobs scoring below {config.min_match_score}% will be filtered automatically.",
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
            capture    = _LogCapture(sys.__stdout__, on_line=append_log)
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
        tracker    = self.ctx.tracker
        config     = self.ctx.config
        session    = self.ctx.session
        batch_ids  = set(getattr(self, "_last_scored_ids", []))
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
            lines  = [f"Scoring complete — {len(scored)} job(s) passed threshold.\n"]
            if high:
                lines.append(f"  ✓  {high} high match (≥70%) — strong candidates")
            if medium:
                lines.append(f"  ~  {medium} medium match ({min_score}–69%) — worth considering")
            if low:
                lines.append(f"  ✗  {low} low score (<{min_score}%) — auto-hidden")
            lines.append("\nReview scores below. Tick jobs to tailor and click 'Tailor scored jobs'.")
            messagebox.showinfo("Scoring complete", "\n".join(lines))

    # ── Tailor ────────────────────────────────────────────────────────────────

    def _tailor_selected(self):
        if not self._selected_ids:
            messagebox.showinfo("Nothing selected", "Tick at least one job to tailor.")
            return

        tracker = self.ctx.tracker
        config  = self.ctx.config

        to_tailor = [jid for jid in self._selected_ids
                     if self._screen_job_map.get(jid, {}).get("status") == "scored"]

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
            f"CV and cover letter will be generated for each.",
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
            capture    = _LogCapture(sys.__stdout__, on_line=append_log)
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
        self._tailor_btn.config(text="✍  Tailor scored jobs (~$0.05 each)",
                                state="normal", bg=GREEN)
        self._refresh_screen()
        if self.ctx.refresh_review:
            self.ctx.refresh_review()
        tracker      = self.ctx.tracker
        session      = self.ctx.session
        tailored_ids  = set(getattr(self, "_last_tailored_ids", []))
        tailored_jobs = [tracker.get_job(jid) for jid in tailored_ids if tracker.get_job(jid)]
        if session:
            session.record_tailored(tailored_jobs)
        n = len(tracker.get_pending_review()) if tracker else 0
        if n:
            messagebox.showinfo("Done", f"{n} application(s) tailored.\n\nGo to Review queue to check them.")
            if self.ctx.show_screen:
                self.ctx.show_screen("review")

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_screen(self):
        if not self._screen_all_jobs:
            messagebox.showinfo("Export", "No data to export.")
            return

        query     = self._screen_search_var.get().lower().strip()
        high_only = self._screen_high_only.get()
        jobs      = self._screen_all_jobs

        if high_only:
            jobs = [j for j in jobs
                    if j.get("match_score") is not None and j["match_score"] >= 70]
        if query:
            jobs = [j for j in jobs if
                    query in (j.get("title")       or "").lower() or
                    query in (j.get("employer")    or "").lower() or
                    query in (j.get("salary")      or "").lower() or
                    query in (j.get("source")      or "").lower() or
                    query in (j.get("location")    or "").lower() or
                    query in (j.get("description") or "").lower()]

        headers = ["ID", "Role", "Employer", "Location", "Salary",
                   "Match %", "Status", "Source", "Found", "URL"]
        rows = [[
            j.get("id"),
            j.get("title")    or "",
            j.get("employer") or "",
            j.get("location") or "",
            j.get("salary")   or "",
            j.get("match_score") or "",
            (j.get("status") or "").replace("_", " ").title(),
            j.get("source")   or "",
            (j.get("date_found") or "")[:10],
            j.get("url")      or "",
        ] for j in jobs]

        export_to_excel(headers, rows, default_name="screen_jobs_export.xlsx")

    # ── Toggle high-only ──────────────────────────────────────────────────────

    def _toggle_high_only(self):
        val = not self._screen_high_only.get()
        self._screen_high_only.set(val)
        self._high_only_btn.config(bg=GREEN_LT if val else BG2,
                                   fg=GREEN    if val else TEXT)
        self._apply_screen_filter()

    # ── Refilter (called externally) ──────────────────────────────────────────

    def _run_refilter(self):
        config  = self.ctx.config
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
        messagebox.showinfo("Refiltering",
            "Re-applying filters to discovered jobs...\nThe list will update when done.")

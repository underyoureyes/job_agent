"""
ui/screens/dashboard.py
=======================
DashboardScreen — overview table, stat cards, context menu, URL-add dialog.
"""

import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox
import threading
from pathlib import Path

from ui.constants import (
    BG, BG2, CARD, TEXT, TEXT2, BLUE, BLUE_LT, GREEN, GREEN_LT,
    FONT, FONT_SM, FONT_HEAD, FONT_FAMILY, STATUS_COLOURS,
)
from ui.context import AppContext
from ui.utils import open_file, export_to_excel
from ui.screens.base import BaseScreen


class DashboardScreen(BaseScreen):
    def __init__(self, parent: tk.Frame, ctx: AppContext):
        super().__init__(parent, ctx)
        self._dash_sort_col = "Found"
        self._dash_sort_asc = False
        self._dash_search_var = tk.StringVar()
        self._dash_all_jobs = []
        self._build(self.frame)

    def _build(self, parent: tk.Frame):
        # Header
        header = tk.Frame(parent, bg=BG)
        header.pack(fill="x", padx=32, pady=(28, 12))
        tk.Label(header, text="Dashboard", font=FONT_HEAD, bg=BG, fg=TEXT).pack(side="left")
        tk.Button(header, text="Refresh", font=FONT_SM, bg=BG2, fg=TEXT,
                  relief="flat", padx=10, pady=4,
                  command=self.refresh).pack(side="right")
        tk.Button(header, text="Export to Excel", font=FONT_SM, bg=GREEN_LT, fg=GREEN,
                  relief="flat", padx=10, pady=4,
                  command=self._export_dashboard).pack(side="right", padx=(0, 8))
        tk.Button(header, text="+ Add job by URL", font=(FONT_FAMILY, 12, "bold"), bg=BLUE, fg=TEXT,
                  relief="flat", padx=12, pady=4,
                  command=self._add_job_by_url).pack(side="right", padx=(0, 8))

        # Summary stat cards
        self._stat_frame = tk.Frame(parent, bg=BG)
        self._stat_frame.pack(fill="x", padx=32, pady=(0, 8))

        # Search bar
        search_bar = tk.Frame(parent, bg=BG)
        search_bar.pack(fill="x", padx=32, pady=(0, 6))
        tk.Label(search_bar, text="Search:", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left")
        dash_search = tk.Entry(search_bar, textvariable=self._dash_search_var,
                               font=FONT_SM, width=28, relief="solid", bd=1, bg=CARD)
        dash_search.pack(side="left", padx=(4, 4), ipady=3)
        self._dash_search_var.trace_add("write", lambda *_: self._apply_dash_filter())
        tk.Button(search_bar, text="✕", font=FONT_SM, bg=BG2, fg=TEXT2, relief="flat",
                  padx=4, command=lambda: self._dash_search_var.set("")).pack(side="left")

        # Applications table
        table_frame = tk.Frame(parent, bg=BG)
        table_frame.pack(fill="both", expand=True, padx=32)

        cols = ("ID", "Role", "Employer", "Match", "Status", "Found")
        self._tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        col_cfg = {
            "ID":       dict(width=40,  minwidth=30,  stretch=False),
            "Role":     dict(width=260, minwidth=120, stretch=True),
            "Employer": dict(width=160, minwidth=80,  stretch=True),
            "Match":    dict(width=60,  minwidth=50,  stretch=False),
            "Status":   dict(width=120, minwidth=80,  stretch=False),
            "Found":    dict(width=90,  minwidth=70,  stretch=False),
        }
        for col in cols:
            self._tree.heading(col, text=col, command=lambda c=col: self._dash_sort(c))
            self._tree.column(col, **col_cfg[col])

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<Double-1>", self._on_tree_double_click)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Bottom action bar
        action_bar = tk.Frame(parent, bg=BG2)
        action_bar.pack(fill="x", side="bottom")
        tk.Label(action_bar, text="Double-click a row to open files · Right-click for status update",
                 font=FONT_SM, bg=BG2, fg=TEXT2).pack(side="left", padx=16, pady=8)

        self._build_context_menu()

    def _build_context_menu(self):
        self._ctx_menu = tk.Menu(self.frame, tearoff=0, font=FONT_SM)
        for status in ["submitted", "interview", "offer", "rejected"]:
            self._ctx_menu.add_command(
                label=f"Mark as {status}",
                command=lambda s=status: self._update_selected_status(s)
            )
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Open files", command=self._open_selected_files)
        self._tree.bind("<Button-2>", self._show_context_menu)
        self._tree.bind("<Control-Button-1>", self._show_context_menu)

    def _show_context_menu(self, event):
        row = self._tree.identify_row(event.y)
        if row:
            self._tree.selection_set(row)
            self._ctx_menu.post(event.x_root, event.y_root)

    def refresh(self):
        self._refresh_dashboard()

    def _refresh_dashboard(self):
        tracker = self.ctx.tracker
        if not tracker:
            return

        for w in self._stat_frame.winfo_children():
            w.destroy()

        jobs = tracker.get_all_jobs()
        self._dash_all_jobs = jobs
        counts = {}
        for job in jobs:
            s = job["status"]
            counts[s] = counts.get(s, 0) + 1

        stat_order = ["tailored", "pending_review", "approved", "submitted", "interview", "offer"]
        labels = {"tailored": "To review", "pending_review": "Pending",
                  "approved": "Approved", "submitted": "Applied",
                  "interview": "Interviews", "offer": "Offers"}

        for status in stat_order:
            count = counts.get(status, 0)
            fg, bg = STATUS_COLOURS.get(status, (TEXT, BG2))
            card = tk.Frame(self._stat_frame, bg=bg, padx=16, pady=10)
            card.pack(side="left", padx=(0, 10), pady=4)
            tk.Label(card, text=str(count), font=(FONT_FAMILY, 22, "bold"),
                     bg=bg, fg=fg).pack()
            tk.Label(card, text=labels.get(status, status),
                     font=FONT_SM, bg=bg, fg=fg).pack()

        self._apply_dash_filter()

    def _dash_sort(self, col: str):
        if self._dash_sort_col == col:
            self._dash_sort_asc = not self._dash_sort_asc
        else:
            self._dash_sort_col = col
            self._dash_sort_asc = True
        col_map = {"ID": "id", "Role": "title", "Employer": "employer",
                   "Match": "match_score", "Status": "status", "Found": "date_found"}
        for c in ("ID", "Role", "Employer", "Match", "Status", "Found"):
            arrow = ""
            if c == col:
                arrow = " ▲" if self._dash_sort_asc else " ▼"
            self._tree.heading(c, text=c + arrow)
        self._apply_dash_filter()

    def _apply_dash_filter(self):
        if not hasattr(self, "_dash_all_jobs"):
            return
        query = self._dash_search_var.get().lower().strip()
        jobs = self._dash_all_jobs

        if query:
            jobs = [j for j in jobs if
                    query in (j.get("title") or "").lower() or
                    query in (j.get("employer") or "").lower() or
                    query in (j.get("status") or "").lower()]

        col_map = {"ID": "id", "Role": "title", "Employer": "employer",
                   "Match": "match_score", "Status": "status", "Found": "date_found"}
        if self._dash_sort_col and self._dash_sort_col in col_map:
            key = col_map[self._dash_sort_col]
            def sort_key(j):
                v = j.get(key)
                if v is None:
                    return (1, "")
                return (0, v) if isinstance(v, (int, float)) else (0, str(v).lower())
            jobs = sorted(jobs, key=sort_key, reverse=not self._dash_sort_asc)

        self._tree.delete(*self._tree.get_children())
        for job in jobs:
            score = f"{job['match_score']}%" if job.get("match_score") else "—"
            date = (job.get("date_found") or "")[:10]
            status = job.get("status", "")
            self._tree.insert("", "end",
                              iid=str(job["id"]),
                              values=(job["id"],
                                      job.get("title") or "—",
                                      job.get("employer") or "—",
                                      score,
                                      status.replace("_", " ").title(),
                                      date))

    def _export_dashboard(self):
        if not hasattr(self, "_dash_all_jobs") or not self._dash_all_jobs:
            messagebox.showinfo("Export", "No data to export.")
            return
        rows = []
        for iid in self._tree.get_children():
            rows.append(self._tree.item(iid)["values"])
        headers = ["ID", "Role", "Employer", "Match", "Status", "Found"]
        export_to_excel(headers, rows, default_name="dashboard_export.xlsx")

    def _on_tree_select(self, event):
        pass

    def _on_tree_double_click(self, event):
        self._open_selected_files()

    def _open_selected_files(self):
        selected = self._tree.selection()
        if not selected:
            messagebox.showinfo("No selection", "Select a row first.")
            return
        job_id = int(selected[0])
        tracker = self.ctx.tracker
        job = tracker.get_job(job_id)
        if not job:
            return
        opened = False
        for path_key in ("tailored_cv_path", "cover_letter_path"):
            path = job.get(path_key)
            if path and Path(path).exists():
                open_file(path)
                opened = True
        if not opened:
            messagebox.showinfo("No files", "No tailored documents found for this job.\n\nScore and tailor it first.")

    def _update_selected_status(self, status: str):
        selected = self._tree.selection()
        if not selected:
            return
        job_id = int(selected[0])
        self.ctx.tracker.update_status(job_id, status, f"Updated via dashboard")
        self._refresh_dashboard()

    def _add_job_by_url(self):
        tracker = self.ctx.tracker
        config = self.ctx.config
        if not tracker or not config:
            messagebox.showwarning("Not ready", "Complete setup before adding jobs.")
            return

        dlg = tk.Toplevel(self.frame)
        dlg.title("Add job by URL")
        dlg.geometry("560x340")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text="Add job by URL", font=(FONT_FAMILY, 15, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w", padx=28, pady=(24, 4))
        tk.Label(dlg, text="Paste the job listing URL below. The app will scrape the description\n"
                           "and generate a tailored CV and cover letter.",
                 font=FONT_SM, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", padx=28, pady=(0, 16))

        tk.Label(dlg, text="Job URL", font=FONT_SM, bg=BG, fg=TEXT).pack(anchor="w", padx=28)
        url_var = tk.StringVar()
        tk.Entry(dlg, textvariable=url_var, font=FONT, bg=CARD, fg=TEXT,
                 relief="flat", bd=1, insertbackground=TEXT).pack(
            fill="x", padx=28, pady=(2, 12), ipady=6)

        overrides = tk.Frame(dlg, bg=BG)
        overrides.pack(fill="x", padx=28, pady=(0, 8))
        tk.Label(overrides, text="Job title (optional)", font=FONT_SM, bg=BG, fg=TEXT2).grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        tk.Label(overrides, text="Employer (optional)", font=FONT_SM, bg=BG, fg=TEXT2).grid(
            row=0, column=1, sticky="w")
        title_var = tk.StringVar()
        employer_var = tk.StringVar()
        tk.Entry(overrides, textvariable=title_var, font=FONT_SM, bg=CARD,
                 relief="flat", bd=1).grid(row=1, column=0, sticky="ew", padx=(0, 12), ipady=4)
        tk.Entry(overrides, textvariable=employer_var, font=FONT_SM, bg=CARD,
                 relief="flat", bd=1).grid(row=1, column=1, sticky="ew", ipady=4)
        overrides.columnconfigure(0, weight=1)
        overrides.columnconfigure(1, weight=1)

        status_var = tk.StringVar()
        tk.Label(dlg, textvariable=status_var, font=FONT_SM, bg=BG, fg=TEXT2).pack(
            anchor="w", padx=28, pady=(4, 0))

        btn_frame = tk.Frame(dlg, bg=BG)
        btn_frame.pack(fill="x", padx=28, pady=(12, 20))
        tk.Button(btn_frame, text="Cancel", font=FONT_SM, bg=BG2, fg=TEXT,
                  relief="flat", padx=14, pady=6,
                  command=dlg.destroy).pack(side="right")

        def submit():
            url = url_var.get().strip()
            if not url:
                messagebox.showwarning("Missing URL", "Please paste a job URL.", parent=dlg)
                return
            go_btn.config(state="disabled", text="Fetching…")
            status_var.set("Fetching job page…")
            dlg.update_idletasks()

            def worker():
                try:
                    job = self._scrape_job_from_url(
                        url,
                        title_override=title_var.get().strip(),
                        employer_override=employer_var.get().strip(),
                    )
                    job_id = tracker.add_job(job)
                    tracker.update_status(job_id, "tailoring", "Added manually by URL")
                    dlg.after(0, lambda: status_var.set("Tailoring CV and cover letter…"))

                    from main import run_tailor_approved
                    run_tailor_approved(config, tracker)

                    tailored = tracker.get_job(job_id)
                    if tailored and self.ctx.session:
                        self.ctx.session.record_tailored([tailored])

                    dlg.after(0, dlg.destroy)
                    if self.ctx.refresh_dashboard:
                        dlg.after(0, self.ctx.refresh_dashboard)
                    if self.ctx.refresh_review:
                        dlg.after(0, self.ctx.refresh_review)
                    dlg.after(0, lambda: messagebox.showinfo(
                        "Done",
                        f"Tailored CV and cover letter ready.\n\nJob: {job.get('title', url)}\n\n"
                        "Go to Review queue to view them."))
                    if self.ctx.show_screen:
                        dlg.after(0, lambda: self.ctx.show_screen("review"))
                except Exception as e:
                    err = str(e)
                    dlg.after(0, lambda: go_btn.config(state="normal", text="Fetch & Tailor"))
                    dlg.after(0, lambda: status_var.set(f"Error: {err}"))

            threading.Thread(target=worker, daemon=True).start()

        go_btn = tk.Button(btn_frame, text="Fetch & Tailor", font=(FONT_FAMILY, 12, "bold"), bg=BLUE, fg=TEXT,
                           relief="flat", padx=14, pady=6, command=submit)
        go_btn.pack(side="right", padx=(0, 8))

    def _scrape_job_from_url(self, url: str, title_override: str = "",
                             employer_override: str = "") -> dict:
        import requests
        from bs4 import BeautifulSoup

        headers = {"User-Agent": "Mozilla/5.0 (compatible; JobAgent/1.0)"}
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "nav", "header", "footer",
                         "noscript", "iframe", "form"]):
            tag.decompose()

        title = title_override
        if not title:
            for sel in [
                "h1", "[class*='job-title']", "[class*='jobTitle']",
                "[itemprop='title']", "[class*='title']",
            ]:
                el = soup.select_one(sel)
                if el and el.get_text(strip=True):
                    title = el.get_text(strip=True)
                    break
            if not title and soup.title:
                title = soup.title.string or ""

        employer = employer_override
        if not employer:
            for sel in [
                "[itemprop='hiringOrganization']", "[class*='employer']",
                "[class*='company']", "[class*='organisation']",
            ]:
                el = soup.select_one(sel)
                if el and el.get_text(strip=True):
                    employer = el.get_text(strip=True)
                    break

        description = ""
        for sel in [
            "[class*='job-description']", "[class*='jobDescription']",
            "[class*='description']", "[itemprop='description']",
            "article", "main", ".content", "#content",
        ]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) > len(description):
                    description = text
        if not description:
            description = soup.get_text(separator="\n", strip=True)

        from urllib.parse import urlparse
        source = urlparse(url).netloc.replace("www.", "").split(".")[0]

        return {
            "title":       title.strip() or "Untitled",
            "employer":    employer.strip() or "Unknown employer",
            "url":         url,
            "description": description[:8000],
            "location":    "London",
            "salary":      "",
            "source":      source,
        }

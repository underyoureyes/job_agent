"""
ui/screens/database.py
======================
DatabaseScreen — all-records view + SQL editor + query results.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from ui.constants import (
    BG, BG2, CARD, TEXT, TEXT2, BLUE, GREEN, GREEN_LT,
    FONT, FONT_SM, FONT_HEAD, FONT_FAMILY,
)
from ui.context import AppContext
from ui.utils import export_to_excel
from ui.screens.base import BaseScreen


class DatabaseScreen(BaseScreen):
    def __init__(self, parent: tk.Frame, ctx: AppContext):
        super().__init__(parent, ctx)
        self._db_result_cols: list = []
        self._db_result_rows: list = []
        self._build(self.frame)

    def _build(self, parent: tk.Frame):
        tk.Label(parent, text="Database", font=FONT_HEAD, bg=BG, fg=TEXT).pack(
            anchor="w", padx=32, pady=(28, 2))
        tk.Label(parent, text="Browse all records, or write SQL to query the database.",
                 font=FONT_SM, bg=BG, fg=TEXT2).pack(anchor="w", padx=32, pady=(0, 16))

        # ── Top pane: all records ─────────────────────────────────────────────
        top_frame = tk.Frame(parent, bg=BG)
        top_frame.pack(fill="both", expand=True, padx=32, pady=(0, 8))

        top_bar = tk.Frame(top_frame, bg=BG)
        top_bar.pack(fill="x", pady=(0, 6))
        tk.Label(top_bar, text="All records", font=(FONT_FAMILY, 12, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Button(top_bar, text="Refresh", font=FONT_SM, bg=BG2, fg=TEXT,
                  relief="flat", padx=10, pady=4,
                  command=self._db_refresh_all).pack(side="right")

        all_cols = ("id", "title", "employer", "location", "salary",
                    "status", "match_score", "date_found", "date_updated", "url")
        tree_frame = tk.Frame(top_frame, bg=BG)
        tree_frame.pack(fill="both", expand=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        self._db_all_tree = ttk.Treeview(
            tree_frame, columns=all_cols, show="headings",
            yscrollcommand=vsb.set, xscrollcommand=hsb.set, height=8)
        vsb.config(command=self._db_all_tree.yview)
        hsb.config(command=self._db_all_tree.xview)

        col_widths = {"id": 40, "title": 220, "employer": 150, "location": 100,
                      "salary": 90, "status": 90, "match_score": 70,
                      "date_found": 120, "date_updated": 120, "url": 180}
        for c in all_cols:
            self._db_all_tree.heading(c, text=c.replace("_", " ").title())
            self._db_all_tree.column(c, width=col_widths.get(c, 100), anchor="w")

        self._db_all_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # ── Middle pane: SQL editor ───────────────────────────────────────────
        mid_frame = tk.Frame(parent, bg=BG)
        mid_frame.pack(fill="x", padx=32, pady=(0, 8))

        mid_bar = tk.Frame(mid_frame, bg=BG)
        mid_bar.pack(fill="x", pady=(0, 4))
        tk.Label(mid_bar, text="SQL query", font=(FONT_FAMILY, 12, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Button(mid_bar, text="Run  ▶", font=FONT_SM, bg=BLUE, fg="white",
                  relief="flat", padx=14, pady=4,
                  command=self._db_run_query).pack(side="right")

        self._db_sql_editor = scrolledtext.ScrolledText(
            mid_frame, height=5, font=("Courier New", 12),
            bg=CARD, fg=TEXT, insertbackground=TEXT,
            relief="flat", bd=1, wrap="none")
        self._db_sql_editor.pack(fill="x")
        self._db_sql_editor.insert("1.0", "SELECT * FROM jobs ORDER BY date_found DESC LIMIT 100;")

        # ── Bottom pane: query results ────────────────────────────────────────
        bot_frame = tk.Frame(parent, bg=BG)
        bot_frame.pack(fill="both", expand=True, padx=32, pady=(0, 24))

        bot_bar = tk.Frame(bot_frame, bg=BG)
        bot_bar.pack(fill="x", pady=(0, 6))
        self._db_result_label = tk.Label(bot_bar, text="Results", font=(FONT_FAMILY, 12, "bold"),
                                         bg=BG, fg=TEXT)
        self._db_result_label.pack(side="left")
        tk.Button(bot_bar, text="Export to Excel", font=FONT_SM, bg=GREEN_LT, fg=GREEN,
                  relief="flat", padx=12, pady=4,
                  command=self._db_export_results).pack(side="right")

        res_frame = tk.Frame(bot_frame, bg=BG)
        res_frame.pack(fill="both", expand=True)

        vsb2 = ttk.Scrollbar(res_frame, orient="vertical")
        hsb2 = ttk.Scrollbar(res_frame, orient="horizontal")
        self._db_result_tree = ttk.Treeview(
            res_frame, show="headings",
            yscrollcommand=vsb2.set, xscrollcommand=hsb2.set, height=8)
        vsb2.config(command=self._db_result_tree.yview)
        hsb2.config(command=self._db_result_tree.xview)

        self._db_result_tree.grid(row=0, column=0, sticky="nsew")
        vsb2.grid(row=0, column=1, sticky="ns")
        hsb2.grid(row=1, column=0, sticky="ew")
        res_frame.rowconfigure(0, weight=1)
        res_frame.columnconfigure(0, weight=1)

        self._db_refresh_all()

    def refresh(self):
        self._db_refresh_all()

    def _db_refresh_all(self):
        tracker = self.ctx.tracker
        if not tracker:
            return
        jobs = tracker.get_all_jobs()
        self._db_all_tree.delete(*self._db_all_tree.get_children())
        cols = ("id", "title", "employer", "location", "salary",
                "status", "match_score", "date_found", "date_updated", "url")
        for job in jobs:
            self._db_all_tree.insert("", "end", values=[job.get(c, "") for c in cols])

    def _db_run_query(self):
        tracker = self.ctx.tracker
        if not tracker:
            messagebox.showerror("Database", "No database connected.")
            return
        sql = self._db_sql_editor.get("1.0", "end").strip()
        if not sql:
            return
        import sqlite3
        try:
            conn = sqlite3.connect(tracker.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql)
            rows = cur.fetchall()
            col_names = [d[0] for d in cur.description] if cur.description else []
            conn.close()
        except Exception as e:
            messagebox.showerror("SQL error", str(e))
            return

        self._db_result_cols = col_names
        self._db_result_rows = [list(r) for r in rows]

        self._db_result_tree["columns"] = col_names
        self._db_result_tree.delete(*self._db_result_tree.get_children())
        for c in col_names:
            self._db_result_tree.heading(c, text=c.replace("_", " ").title())
            self._db_result_tree.column(c, width=120, anchor="w")
        for row in self._db_result_rows:
            self._db_result_tree.insert("", "end", values=row)

        n = len(rows)
        self._db_result_label.config(
            text=f"Results — {n} row{'s' if n != 1 else ''}")

    def _db_export_results(self):
        if not self._db_result_cols:
            messagebox.showinfo("Export", "Run a query first to get results.")
            return
        export_to_excel(
            self._db_result_cols,
            self._db_result_rows,
            default_name="db_query_export.xlsx",
        )

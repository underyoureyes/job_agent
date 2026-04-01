"""
ui/app_shell.py
===============
JobAgentShell(tk.Tk) — top-level window, sidebar, screen router, scan button.
Instantiates all screens and wires callbacks into AppContext.
"""

import sys
import threading
import tkinter as tk
from pathlib import Path
from datetime import datetime

from ui.constants import (
    BG, BG2, BORDER, TEXT, TEXT2, BLUE,
    FONT, FONT_SM, FONT_FAMILY,
    configure_styles, _LogCapture,
)
from ui.context import AppContext


class JobAgentShell(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Job Application Agent")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(bg=BG)
        configure_styles()

        # Build shared context
        self._ctx = AppContext()

        # Load config + tracker lazily (may not be set up yet)
        self._load_backend()

        # Session activity log
        from session_log import SessionLog
        self._ctx.session = SessionLog()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # First-run: prompt for output folder if path doesn't exist
        self._check_output_dir_on_startup()

        # Layout: sidebar + content
        self._sidebar = self._build_sidebar()
        self._sidebar.pack(side="left", fill="y")

        self._content = tk.Frame(self, bg=BG)
        self._content.pack(side="left", fill="both", expand=True)

        # Screens
        self._screens: dict = {}
        self._current_screen = None
        self._build_all_screens()

        # Wire callbacks onto context
        self._ctx.show_screen      = self._show_screen
        self._ctx.refresh_dashboard = self._refresh_dashboard
        self._ctx.refresh_review    = self._refresh_review
        self._ctx.refresh_screen    = self._refresh_screen
        self._ctx.reload_backend    = self._load_backend
        self._ctx.append_log_line   = self._append_log_line
        self._ctx.needs_setup       = self._needs_setup

        # Show setup if not configured, else dashboard
        if self._needs_setup():
            self._show_screen("setup")
        else:
            self._show_screen("dashboard")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_close(self):
        session = self._ctx.session
        config = self._ctx.config
        if session and session.has_activity() and config:
            sent = session.send_summary(config)
            if sent:
                print("[Session Log] Summary email sent.")
        self.destroy()

    # ── Backend loading ───────────────────────────────────────────────────────

    def _load_backend(self):
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from config import Config
            from tracker import ApplicationTracker
            self._ctx.config = Config()
            self._ctx.tracker = ApplicationTracker(self._ctx.config.db_path)
            self._seed_bundled_files()
        except Exception as e:
            print(f"Backend load warning: {e}")

    def _seed_bundled_files(self):
        if not getattr(sys, "frozen", False):
            return

        import shutil
        meipass = Path(sys._MEIPASS)
        target_dir = Path.home() / "Library" / "Application Support" / "JobAgent"
        target_dir.mkdir(parents=True, exist_ok=True)

        for src_name, dest_name in [
            ("base_cv.md",                 "base_cv.md"),
            ("cv_template.docx",           "cv_template.docx"),
            ("cv_style.json",              "cv_style.json"),
            ("cover_letter_template.docx", "cover_letter_template.docx"),
            ("cover_letter_style.json",    "cover_letter_style.json"),
        ]:
            src  = meipass / src_name
            dest = target_dir / dest_name
            if src.exists() and not dest.exists():
                try:
                    import shutil as _shutil
                    _shutil.copy2(src, dest)
                except Exception as e:
                    print(f"Could not seed {src_name}: {e}")

    def _needs_setup(self) -> bool:
        config = self._ctx.config
        if not config:
            return True
        return config.candidate_name in ("YOUR_NAME", "", None)

    def _check_output_dir_on_startup(self):
        config = self._ctx.config
        if not config:
            return
        output_dir = Path(config.output_dir)
        if output_dir.exists():
            return

        dialog = tk.Toplevel(self)
        dialog.title("Choose a save folder")
        dialog.geometry("520x240")
        dialog.resizable(False, False)
        dialog.configure(bg=BG)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="Welcome to Job Agent!",
            font=(FONT_FAMILY, 16, "bold"),
            bg=BG, fg=TEXT,
        ).pack(pady=(28, 4))

        tk.Label(
            dialog,
            text="Please choose a folder where your tailored CVs\nand cover letters will be saved.",
            font=FONT, bg=BG, fg=TEXT2, justify="center",
        ).pack(pady=(0, 16))

        path_var = tk.StringVar(value=str(Path.home() / "Documents" / "JobAgent"))
        path_row = tk.Frame(dialog, bg=BG)
        path_row.pack(fill="x", padx=32)
        path_entry = tk.Entry(path_row, textvariable=path_var, font=FONT, width=38)
        path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        from tkinter import filedialog
        def browse():
            chosen = filedialog.askdirectory(title="Choose save folder", parent=dialog)
            if chosen:
                path_var.set(chosen)

        tk.Button(path_row, text="Browse…", font=FONT_SM, bg=BG2, fg=TEXT,
                  relief="flat", padx=8, command=browse).pack(side="left")

        from tkinter import messagebox
        def confirm():
            chosen = path_var.get().strip()
            if not chosen:
                messagebox.showwarning("Required", "Please choose a folder.", parent=dialog)
                return
            try:
                Path(chosen).mkdir(parents=True, exist_ok=True)
                config.output_dir = Path(chosen)
                self._save_output_dir_to_prefs(chosen)
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Could not create folder:\n{e}", parent=dialog)

        tk.Button(
            dialog, text="Save & continue",
            font=(FONT_FAMILY, 13, "bold"), bg=BLUE, fg="white",
            relief="flat", padx=16, pady=8,
            command=confirm,
        ).pack(pady=20)

        self.wait_window(dialog)

    def _save_output_dir_to_prefs(self, output_dir: str):
        import re
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from config import USER_PREFS_PATH
            prefs_path = USER_PREFS_PATH
        except Exception:
            prefs_path = Path.home() / "Library" / "Application Support" / "JobAgent" / "user.env"

        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        text = prefs_path.read_text(encoding="utf-8") if prefs_path.exists() else ""
        if "OUTPUT_DIR=" in text:
            text = re.sub(r"OUTPUT_DIR=.*", f"OUTPUT_DIR={output_dir}", text)
        else:
            text = text.rstrip("\n") + f"\nOUTPUT_DIR={output_dir}\n"
        prefs_path.write_text(text, encoding="utf-8")

    def _save_linkedin_creds_to_prefs(self, email: str, password: str):
        import re
        try:
            from config import USER_PREFS_PATH
            prefs_path = USER_PREFS_PATH
        except Exception:
            prefs_path = Path.home() / "Library" / "Application Support" / "JobAgent" / "user.env"

        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        text = prefs_path.read_text(encoding="utf-8") if prefs_path.exists() else ""

        if email:
            if "LINKEDIN_APPLY_EMAIL=" in text:
                text = re.sub(r"LINKEDIN_APPLY_EMAIL=.*", f"LINKEDIN_APPLY_EMAIL={email}", text)
            else:
                text = text.rstrip("\n") + f"\nLINKEDIN_APPLY_EMAIL={email}\n"

        if password:
            if "LINKEDIN_APPLY_PASSWORD=" in text:
                text = re.sub(r"LINKEDIN_APPLY_PASSWORD=.*", f"LINKEDIN_APPLY_PASSWORD={password}", text)
            else:
                text = text.rstrip("\n") + f"\nLINKEDIN_APPLY_PASSWORD={password}\n"

        prefs_path.write_text(text, encoding="utf-8")

    def _save_email_prefs(self, notify_email: str, smtp_user: str, smtp_password: str):
        import re
        try:
            from config import USER_PREFS_PATH
            prefs_path = USER_PREFS_PATH
        except Exception:
            prefs_path = Path.home() / "Library" / "Application Support" / "JobAgent" / "user.env"

        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        text = prefs_path.read_text(encoding="utf-8") if prefs_path.exists() else ""

        def set_pref(t, key, value):
            if not value:
                return t
            if f"{key}=" in t:
                return re.sub(rf"{key}=.*", f"{key}={value}", t)
            return t.rstrip("\n") + f"\n{key}={value}\n"

        text = set_pref(text, "NOTIFY_EMAIL",   notify_email)
        text = set_pref(text, "SMTP_USER",      smtp_user)
        text = set_pref(text, "SMTP_FROM",      smtp_user)
        text = set_pref(text, "SMTP_PASSWORD",  smtp_password)
        prefs_path.write_text(text, encoding="utf-8")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> tk.Frame:
        sidebar = tk.Frame(self, bg=BG, width=200)
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="Job Agent", font=(FONT_FAMILY, 17, "bold"),
                 bg=BG, fg=TEXT, pady=20).pack(fill="x", padx=20)

        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=16)

        self._nav_buttons = {}
        nav_items = [
            ("dashboard", "  Dashboard"),
            ("screen",    "  Screen jobs"),
            ("add_job",   "  Add by description"),
            ("review",    "  Review queue"),
            ("settings",  "  Settings"),
            ("setup",     "  Setup"),
            ("log",       "  Scan log"),
            ("database",  "  Database"),
            ("info",      "  Info"),
        ]
        for key, label in nav_items:
            btn = tk.Button(
                sidebar, text=label, anchor="w",
                font=FONT, bg=BG, fg=TEXT,
                activebackground=BG2, activeforeground=TEXT,
                relief="flat", bd=0, pady=10, padx=16,
                command=lambda k=key: self._show_screen(k)
            )
            btn.pack(fill="x")
            self._nav_buttons[key] = btn

        tk.Frame(sidebar, bg=BG).pack(fill="both", expand=True)
        self._scan_btn = tk.Button(
            sidebar, text="  Scan for jobs",
            font=(FONT_FAMILY, 13, "bold"), anchor="w",
            bg=BLUE, fg=TEXT,
            activebackground="#1050A0", activeforeground=TEXT,
            relief="flat", bd=0, pady=12, padx=16,
            command=self._run_scan
        )
        self._scan_btn.pack(fill="x", padx=12, pady=12)

        return sidebar

    def _show_screen(self, name: str):
        if self._current_screen:
            self._screens[self._current_screen].frame.pack_forget()
        for key, btn in self._nav_buttons.items():
            if key == name:
                btn.config(bg=BG2, fg=TEXT, font=(FONT_FAMILY, 13, "bold"))
            else:
                btn.config(bg=BG, fg=TEXT, font=FONT)
        screen = self._screens[name]
        screen.frame.pack(fill="both", expand=True)
        self._current_screen = name
        # Call screen's refresh on switch
        if name == "dashboard":
            screen.refresh()
        elif name == "review":
            screen.refresh()
        elif name == "screen":
            screen.refresh()
        elif name == "add_job":
            screen.refresh()
        elif name == "setup":
            pass  # setup pre-fills from config on build; no live refresh needed
        elif name == "log":
            screen.refresh()
        elif name == "database":
            screen.refresh()
        elif name == "settings":
            screen.refresh()
        elif name == "info":
            pass

    # ── Screen construction ───────────────────────────────────────────────────

    def _build_all_screens(self):
        from ui.screens.setup     import SetupScreen
        from ui.screens.dashboard import DashboardScreen
        from ui.screens.scan      import ScanScreen
        from ui.screens.add_job   import AddJobScreen
        from ui.screens.review    import ReviewScreen
        from ui.screens.settings  import SettingsScreen
        from ui.screens.log       import LogScreen
        from ui.screens.database  import DatabaseScreen
        from ui.screens.info      import InfoScreen

        screen_classes = [
            ("setup",     SetupScreen),
            ("dashboard", DashboardScreen),
            ("screen",    ScanScreen),
            ("add_job",   AddJobScreen),
            ("review",    ReviewScreen),
            ("settings",  SettingsScreen),
            ("log",       LogScreen),
            ("database",  DatabaseScreen),
            ("info",      InfoScreen),
        ]

        for name, cls in screen_classes:
            screen = cls(self._content, self._ctx)
            self._screens[name] = screen

    # ── Convenience refresh forwarders ────────────────────────────────────────

    def _refresh_dashboard(self):
        if "dashboard" in self._screens:
            self._screens["dashboard"].refresh()

    def _refresh_review(self):
        if "review" in self._screens:
            self._screens["review"].refresh()

    def _refresh_screen(self):
        if "screen" in self._screens:
            self._screens["screen"].refresh()

    # ── Log append (forwarded to LogScreen) ──────────────────────────────────

    def _append_log_line(self, line: str):
        if "log" in self._screens:
            self._screens["log"].append_line(line)
        else:
            # Screen not yet built — append directly to ctx list
            self._ctx.scan_log_lines.append(line)

    # ── Scan ──────────────────────────────────────────────────────────────────

    def _run_scan(self):
        from tkinter import messagebox
        if self._needs_setup():
            messagebox.showwarning("Setup required", "Please complete setup before scanning.")
            self._show_screen("setup")
            return

        self._scan_btn.config(text="  Scanning…", state="disabled", bg="#555")
        self.update_idletasks()

        self._ctx.scan_log_lines.append(
            f"── Scan started {datetime.now().strftime('%d %b %Y %H:%M:%S')} ──"
        )

        config  = self._ctx.config
        tracker = self._ctx.tracker

        def scan_thread():
            capture = _LogCapture(sys.__stdout__, on_line=self._append_log_line)
            old_stdout = sys.stdout
            sys.stdout = capture
            try:
                from main import run_scan
                run_scan(config, tracker)
            except Exception as e:
                err = str(e)
                self._append_log_line(f"ERROR: {err}")
                self.after(0, lambda: messagebox.showerror("Scan failed", err))
            finally:
                sys.stdout = old_stdout
                self._append_log_line(
                    f"── Scan finished {datetime.now().strftime('%H:%M:%S')} ──"
                )
                self.after(0, self._scan_done)

        threading.Thread(target=scan_thread, daemon=True).start()

    def _scan_done(self):
        from tkinter import messagebox
        self._scan_btn.config(text="  Scan for jobs", state="normal", bg=BLUE)
        self._refresh_dashboard()
        self._refresh_review()
        tracker = self._ctx.tracker
        pending    = len(tracker.get_pending_review()) if tracker else 0
        discovered = len(tracker.get_discovered_jobs()) if tracker else 0
        if discovered:
            messagebox.showinfo("Scan complete",
                                f"Scan finished.\n\n{discovered} job(s) found and ready to review.\n\n"
                                f"No credits spent yet — review titles in Screen jobs first.")
            self._show_screen("screen")

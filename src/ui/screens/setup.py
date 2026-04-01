"""
ui/screens/setup.py
===================
SetupScreen — candidate details, API keys, templates, output folder.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from ui.constants import (
    BG, CARD, TEXT, TEXT2, BLUE, BORDER,
    FONT, FONT_SM, FONT_HEAD, FONT_FAMILY,
)
from ui.context import AppContext
from ui.widgets import section_label, labeled_entry, file_picker_row
from ui.screens.base import BaseScreen


class SetupScreen(BaseScreen):
    def __init__(self, parent: tk.Frame, ctx: AppContext):
        super().__init__(parent, ctx)
        self._build(self.frame)

    def _build(self, parent: tk.Frame):
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        pad = dict(padx=40, pady=8)

        tk.Label(inner, text="Setup", font=FONT_HEAD, bg=BG, fg=TEXT).pack(anchor="w", padx=40, pady=(32, 4))
        tk.Label(inner, text="Connect your templates and API keys to get started.",
                 font=FONT_SM, bg=BG, fg=TEXT2).pack(anchor="w", **pad)

        # ── Section: Candidate ────────────────────────────────────────────────
        section_label(inner, "Candidate details")

        self._setup_name_var    = labeled_entry(inner, "Full name", "e.g. James Smith")
        self._setup_email_var   = labeled_entry(inner, "Email", "e.g. james@email.com")
        self._setup_phone_var   = labeled_entry(inner, "Phone", "+44 7XXX XXXXXX")
        self._setup_linkedin_var= labeled_entry(inner, "LinkedIn URL", "https://linkedin.com/in/...")

        self._setup_address_var  = labeled_entry(inner, "Address line 1", "e.g. 12 Example Street")
        self._setup_address2_var = labeled_entry(inner, "Address line 2 (city, postcode)", "e.g. London, SW1A 1AA")

        config = self.ctx.config
        if config:
            self._setup_name_var.set(config.candidate_name if config.candidate_name != "YOUR_SON_NAME" else "")
            self._setup_email_var.set(config.candidate_email if "@" in config.candidate_email else "")
            self._setup_phone_var.set(config.candidate_phone)
            self._setup_linkedin_var.set(config.candidate_linkedin if "linkedin" in config.candidate_linkedin else "")
            self._setup_address_var.set(getattr(config, "candidate_address", ""))
            self._setup_address2_var.set(getattr(config, "candidate_address2", ""))

        # ── Section: API Keys ─────────────────────────────────────────────────
        section_label(inner, "API keys")

        self._setup_anthropic_var = labeled_entry(inner, "Anthropic API key  (required for CV tailoring)",
                                                  "sk-ant-...", show="*")
        self._setup_reed_var      = labeled_entry(inner, "Reed API key  (optional — get free at reed.co.uk/developers)",
                                                  "xxxxxxxx-xxxx-...", show="*")

        if config:
            if config.anthropic_api_key not in ("YOUR_ANTHROPIC_API_KEY", ""):
                self._setup_anthropic_var.set(config.anthropic_api_key)
            if config.reed_api_key not in ("YOUR_REED_API_KEY", ""):
                self._setup_reed_var.set(config.reed_api_key)

        # ── Section: LinkedIn auto-apply ──────────────────────────────────────
        section_label(inner, "LinkedIn Easy Apply")
        tk.Label(inner, text="Used to log in when auto-applying to LinkedIn jobs.\nLeave blank if you don't want to use LinkedIn auto-apply.",
                 font=FONT_SM, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", padx=40, pady=(4, 0))

        self._setup_li_email_var    = labeled_entry(inner, "LinkedIn email", "you@email.com")
        self._setup_li_password_var = labeled_entry(inner, "LinkedIn password", "", show="*")

        if config:
            if getattr(config, "linkedin_apply_email", ""):
                self._setup_li_email_var.set(config.linkedin_apply_email)
            if getattr(config, "linkedin_apply_password", ""):
                self._setup_li_password_var.set(config.linkedin_apply_password)

        # ── Section: Session summary email ───────────────────────────────────
        section_label(inner, "Session summary email (optional)")
        tk.Label(inner, text="Sends a summary of activity (costs, scored jobs, tailored CVs, applications) when you close the app.\nUse a Gmail App Password — myaccount.google.com/apppasswords",
                 font=FONT_SM, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", padx=40, pady=(4, 0))

        self._setup_notify_email_var = labeled_entry(inner, "Send summary to (email)", "you@email.com")
        self._setup_smtp_user_var    = labeled_entry(inner, "Gmail address (sender)", "you@gmail.com")
        self._setup_smtp_pass_var    = labeled_entry(inner, "Gmail App Password", "", show="*")

        if config:
            if getattr(config, "notify_email", ""):
                self._setup_notify_email_var.set(config.notify_email)
            if getattr(config, "smtp_user", ""):
                self._setup_smtp_user_var.set(config.smtp_user)
            if getattr(config, "smtp_password", ""):
                self._setup_smtp_pass_var.set(config.smtp_password)

        # ── Section: Templates ────────────────────────────────────────────────
        section_label(inner, "Document templates (.docx)")
        tk.Label(inner, text="Upload the candidate's existing CV and cover letter.\n"
                             "The AI will match their style for every output document.",
                 font=FONT_SM, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", **pad)

        self._cv_template_path = tk.StringVar()
        self._letter_template_path = tk.StringVar()

        if config:
            cv_style = config.base_dir / "cv_template.docx"
            letter_style = config.base_dir / "cover_letter_template.docx"
            if cv_style.exists():
                self._cv_template_path.set(str(cv_style))
            if letter_style.exists():
                self._letter_template_path.set(str(letter_style))

        file_picker_row(inner, "CV template (.docx)", self._cv_template_path, self._pick_cv_template)
        file_picker_row(inner, "Cover letter template (.docx)", self._letter_template_path, self._pick_letter_template)

        # ── Section: Output folder ────────────────────────────────────────────
        section_label(inner, "Output folder")
        tk.Label(inner, text="Where tailored CVs and cover letters will be saved.",
                 font=FONT_SM, bg=BG, fg=TEXT2, justify="left").pack(anchor="w", **pad)

        self._output_dir_var = tk.StringVar()
        if config:
            self._output_dir_var.set(str(config.output_dir))

        file_picker_row(inner, "Output folder", self._output_dir_var, self._pick_output_dir)

        # ── Save button ────────────────────────────────────────────────────────
        tk.Frame(inner, bg=BG, height=16).pack()
        save_btn = tk.Button(inner, text="Save and continue →",
                             font=(FONT_FAMILY, 13, "bold"),
                             bg=BLUE, fg=TEXT,
                             padx=24, pady=10,
                             command=self._save_setup)
        save_btn.pack(anchor="w", padx=40, pady=(0, 40))

    def _pick_cv_template(self):
        path = filedialog.askopenfilename(
            title="Select CV template",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")]
        )
        if path:
            self._cv_template_path.set(path)

    def _pick_letter_template(self):
        path = filedialog.askopenfilename(
            title="Select cover letter template",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")]
        )
        if path:
            self._letter_template_path.set(path)

    def _pick_output_dir(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self._output_dir_var.set(path)

    def _save_setup(self):
        name     = self._setup_name_var.get().strip()
        email    = self._setup_email_var.get().strip()
        phone    = self._setup_phone_var.get().strip()
        linkedin = self._setup_linkedin_var.get().strip()
        address  = self._setup_address_var.get().strip()
        address2 = self._setup_address2_var.get().strip()
        anth     = self._setup_anthropic_var.get().strip()
        reed     = self._setup_reed_var.get().strip()
        li_email    = self._setup_li_email_var.get().strip()
        li_password = self._setup_li_password_var.get().strip()
        notify_email = self._setup_notify_email_var.get().strip()
        smtp_user    = self._setup_smtp_user_var.get().strip()
        smtp_pass    = self._setup_smtp_pass_var.get().strip()
        output_dir = self._output_dir_var.get().strip()

        if not name or name == "e.g. James Smith":
            messagebox.showwarning("Setup", "Please enter the candidate's full name.")
            return
        if not anth or anth.startswith("sk-ant-") is False and len(anth) < 10:
            if not messagebox.askyesno("Setup", "No Anthropic API key entered — CV tailoring will not work. Continue anyway?"):
                return

        config = self.ctx.config
        # Apply output dir immediately to config
        if output_dir and config:
            from pathlib import Path as _Path
            config.output_dir = _Path(output_dir)
            config.output_dir.mkdir(parents=True, exist_ok=True)

        # Process uploaded templates
        self._process_templates()

        # Write config.py with updated values
        self._write_config(name=name, email=email, phone=phone,
                           linkedin=linkedin, address=address, address2=address2,
                           output_dir=output_dir, anthropic_key=anth, reed_key=reed)
        if li_email or li_password:
            self._save_linkedin_creds_to_prefs(li_email, li_password)
        if notify_email or smtp_user or smtp_pass:
            self._save_email_prefs(notify_email, smtp_user, smtp_pass)

        # Reload backend
        if self.ctx.reload_backend:
            self.ctx.reload_backend()

        messagebox.showinfo("Setup", "✓ Setup saved! You're ready to scan for jobs.")
        if self.ctx.show_screen:
            self.ctx.show_screen("dashboard")

    def _process_templates(self):
        """Extract style fingerprints from uploaded docx templates."""
        try:
            from document_processor import DocumentProcessor
            processor = DocumentProcessor()
            import sys as _sys
            from pathlib import Path as _Path
            base_dir = _Path(_sys.modules[__name__].__file__).parent.parent

            cv_path = self._cv_template_path.get()
            if cv_path and Path(cv_path).exists():
                import shutil
                dest = base_dir / "cv_template.docx"
                shutil.copy2(cv_path, dest)
                cv_text, cv_style = processor.extract_cv_template(dest)
                (base_dir / "base_cv.md").write_text(cv_text, encoding="utf-8")
                (base_dir / "cv_style.json").write_text(cv_style.to_json(), encoding="utf-8")

            letter_path = self._letter_template_path.get()
            if letter_path and Path(letter_path).exists():
                import shutil
                dest = base_dir / "cover_letter_template.docx"
                shutil.copy2(letter_path, dest)
                _, letter_style = processor.extract_cover_letter_template(dest)
                (base_dir / "cover_letter_style.json").write_text(letter_style.to_json(), encoding="utf-8")

        except Exception as e:
            messagebox.showwarning("Templates", f"Could not process templates: {e}\n\nYou can re-upload them later.")

    def _write_config(self, name, email, phone, linkedin, address="", address2="",
                      output_dir="", anthropic_key="", reed_key=""):
        import sys as _sys
        from pathlib import Path as _Path
        import re

        config_path = _Path(_sys.modules[__name__].__file__).parent.parent / "config.py"
        if not config_path.exists():
            config_path = _Path(_sys.modules[__name__].__file__).parent.parent.parent / "config.py"
        if not config_path.exists():
            return
        text = config_path.read_text(encoding="utf-8")

        def replace_val(t, attr, new_val):
            pattern = rf'({attr}: str = ")[^"]*(")'
            return re.sub(pattern, rf'\g<1>{new_val}\g<2>', t)

        def replace_path(t, attr, new_val):
            pattern = rf'({attr}.*?Path\.home\(\))[^)]*(\))'
            result = re.sub(pattern, rf'\g<1> / "{new_val}"\g<2>', t)
            if result == t:
                pattern2 = rf'({attr}.*?Path\()[^)]*(\))'
                result = re.sub(pattern2, rf'\g<1>"{new_val}"\g<2>', t)
            return result

        if name:
            text = replace_val(text, "candidate_name", name)
        if email:
            text = replace_val(text, "candidate_email", email)
        if phone:
            text = replace_val(text, "candidate_phone", phone)
        if linkedin:
            text = replace_val(text, "candidate_linkedin", linkedin)
        if address:
            text = replace_val(text, "candidate_address", address)
        if address2:
            text = replace_val(text, "candidate_address2", address2)
        if output_dir:
            self._save_output_dir_to_prefs(output_dir)
        if anthropic_key:
            text = text.replace('os.getenv("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_API_KEY")', f'"{anthropic_key}"')
            text = replace_val(text, "anthropic_api_key", anthropic_key)
        if reed_key:
            text = text.replace('os.getenv("REED_API_KEY", "YOUR_REED_API_KEY")', f'"{reed_key}"')
            text = replace_val(text, "reed_api_key", reed_key)

        config_path.write_text(text, encoding="utf-8")

    def _save_output_dir_to_prefs(self, output_dir: str):
        import re
        from pathlib import Path as _Path
        try:
            import sys as _sys
            _sys.path.insert(0, str(_Path(__file__).parent.parent.parent))
            from config import USER_PREFS_PATH
            prefs_path = USER_PREFS_PATH
        except Exception:
            prefs_path = _Path.home() / "Library" / "Application Support" / "JobAgent" / "user.env"

        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        text = prefs_path.read_text(encoding="utf-8") if prefs_path.exists() else ""
        if "OUTPUT_DIR=" in text:
            text = re.sub(r"OUTPUT_DIR=.*", f"OUTPUT_DIR={output_dir}", text)
        else:
            text = text.rstrip("\n") + f"\nOUTPUT_DIR={output_dir}\n"
        prefs_path.write_text(text, encoding="utf-8")

    def _save_linkedin_creds_to_prefs(self, email: str, password: str):
        import re
        from pathlib import Path as _Path
        try:
            from config import USER_PREFS_PATH
            prefs_path = USER_PREFS_PATH
        except Exception:
            prefs_path = _Path.home() / "Library" / "Application Support" / "JobAgent" / "user.env"

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
        from pathlib import Path as _Path
        try:
            from config import USER_PREFS_PATH
            prefs_path = USER_PREFS_PATH
        except Exception:
            prefs_path = _Path.home() / "Library" / "Application Support" / "JobAgent" / "user.env"

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

    def refresh(self):
        pass

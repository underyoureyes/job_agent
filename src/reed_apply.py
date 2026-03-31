"""
reed_apply.py - Automated Reed.co.uk Application Submitter
===========================================================
Uses Playwright to automate applying to Reed-managed job postings.
Always pauses for user confirmation before final submission.

Requirements:
    pip install playwright
    playwright install chromium
"""

import time
from pathlib import Path
from typing import Dict, Optional


def _extract_text_from_docx(docx_path: str) -> str:
    """Extract plain text from a .docx cover letter."""
    try:
        from docx import Document
        doc = Document(docx_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        print(f"[Reed Apply] Warning: could not read cover letter text: {e}")
        return ""


class ReedApplyError(Exception):
    pass


class ReedApplicant:
    """
    Automates applying to a Reed-managed job posting via Playwright.

    Usage:
        applicant = ReedApplicant(config)
        submitted = applicant.apply(job_dict)
    """

    # Reed selectors — may need updating if Reed redesigns their site
    _SELECTORS = {
        "apply_button": [
            'a[data-qa="apply-button"]',
            'button[data-qa="apply-button"]',
            'a[class*="apply"][class*="btn"]',
            'a[href*="/apply/"]',
            'button:has-text("Apply now")',
            'a:has-text("Apply now")',
        ],
        "first_name": [
            'input[name="firstName"]',
            'input[id*="firstName"]',
            'input[id*="first-name"]',
            'input[placeholder*="First name"]',
        ],
        "last_name": [
            'input[name="lastName"]',
            'input[id*="lastName"]',
            'input[id*="last-name"]',
            'input[placeholder*="Last name"]',
        ],
        "email": [
            'input[type="email"]',
            'input[name="email"]',
            'input[id*="email"]',
        ],
        "phone": [
            'input[type="tel"]',
            'input[name="phone"]',
            'input[name="telephone"]',
            'input[id*="phone"]',
            'input[id*="telephone"]',
        ],
        "cover_letter": [
            'textarea[name="coverLetter"]',
            'textarea[name="coverNote"]',
            'textarea[name="message"]',
            'textarea[id*="cover"]',
            'textarea[id*="message"]',
            'textarea[placeholder*="cover"]',
            'textarea[placeholder*="Cover"]',
            'textarea[placeholder*="message"]',
        ],
        "cv_upload": [
            'input[type="file"][name*="cv"]',
            'input[type="file"][name*="CV"]',
            'input[type="file"][accept*=".doc"]',
            'input[type="file"][accept*=".pdf"]',
            'input[type="file"]',
        ],
        "submit": [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit application")',
            'button:has-text("Submit")',
            'button:has-text("Send application")',
        ],
        "login_email": [
            'input[name="email"][type="email"]',
            'input[id*="login"][id*="email"]',
            '#email',
        ],
        "login_password": [
            'input[type="password"]',
            'input[name="password"]',
        ],
        "login_submit": [
            'button[type="submit"]:has-text("Sign in")',
            'button[type="submit"]:has-text("Log in")',
            'button[type="submit"]:has-text("Login")',
            'button[type="submit"]',
        ],
    }

    def __init__(self, config, headless: bool = False):
        self.config = config
        self.headless = headless

    def apply(self, job: Dict) -> bool:
        """
        Apply to a Reed job.
        Opens a browser, fills the form, then waits for user confirmation before submitting.
        Returns True if the application was submitted, False if aborted or failed.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ReedApplyError(
                "Playwright is not installed.\n"
                "Run: pip install playwright && playwright install chromium"
            )

        job_url = job.get("url", "")
        if "reed.co.uk" not in job_url:
            raise ReedApplyError(f"Not a Reed URL: {job_url}")

        cv_path = job.get("tailored_cv_path")
        if not cv_path or not Path(cv_path).exists():
            raise ReedApplyError(f"Tailored CV not found at: {cv_path}")

        letter_path = job.get("cover_letter_path")
        cover_letter_text = ""
        if letter_path and Path(letter_path).exists():
            cover_letter_text = _extract_text_from_docx(letter_path)

        print(f"\n[Reed Apply] Starting application for: {job.get('title')} at {job.get('employer')}")
        print(f"[Reed Apply] URL: {job_url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, slow_mo=80)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                accept_downloads=True,
            )
            page = context.new_page()
            try:
                result = self._run(page, job, cv_path, cover_letter_text)
            except KeyboardInterrupt:
                print("\n[Reed Apply] Aborted by user.")
                result = False
            except Exception as e:
                print(f"\n[Reed Apply] Error: {e}")
                _save_debug_screenshot(page, "error")
                result = False
            finally:
                time.sleep(3)  # Let user see the final state
                browser.close()

        return result

    def _run(self, page, job: Dict, cv_path: str, cover_letter_text: str) -> bool:
        """Main application flow."""
        page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)

        # ── Step 1: Find and click Apply ────────────────────────────────────
        apply_btn = self._find_element(page, "apply_button", timeout=10000)
        if not apply_btn:
            print("[Reed Apply] Could not find an Apply button on this page.")
            _save_debug_screenshot(page, "no_apply_button")
            return False

        # Check if it redirects externally
        href = apply_btn.get_attribute("href") or ""
        if href and not href.startswith("/") and "reed.co.uk" not in href:
            print(f"[Reed Apply] This job links to an external application site:\n  {href}")
            print("[Reed Apply] External applications cannot be auto-filled.")
            return False

        print("[Reed Apply] Clicking Apply...")
        apply_btn.click()
        page.wait_for_load_state("domcontentloaded", timeout=20000)
        time.sleep(1)

        # ── Step 2: Handle login if credentials are available ────────────────
        reed_email = getattr(self.config, "reed_email", "") or ""
        reed_password = getattr(self.config, "reed_password", "") or ""

        if reed_email and reed_password and self._is_login_page(page):
            print("[Reed Apply] Login page detected — signing in...")
            if not self._login(page, reed_email, reed_password):
                print("[Reed Apply] Login failed. You may need to log in manually.")
                _save_debug_screenshot(page, "login_failed")
                return False
            print("[Reed Apply] Logged in successfully.")
            time.sleep(1)

        # ── Step 3: Fill the application form ───────────────────────────────
        print("[Reed Apply] Filling application form...")
        filled = self._fill_form(page, cv_path, cover_letter_text)
        if not filled:
            print("[Reed Apply] Could not fill form fields — the form structure may have changed.")
            _save_debug_screenshot(page, "form_fill_failed")
            # Still pause so user can see / manually fill
        else:
            print("[Reed Apply] Form filled.")

        # ── Step 4: User confirmation ────────────────────────────────────────
        print("\n" + "─" * 60)
        print("  Browser window is open. Please review the filled form.")
        print("  Press ENTER to submit the application.")
        print("  Press Ctrl+C to abort without submitting.")
        print("─" * 60)
        input()

        # ── Step 5: Submit ───────────────────────────────────────────────────
        submit_btn = self._find_element(page, "submit", timeout=5000)
        if not submit_btn:
            print("[Reed Apply] Could not find Submit button. The form may have changed.")
            _save_debug_screenshot(page, "no_submit_button")
            return False

        print("[Reed Apply] Submitting application...")
        submit_btn.click()
        page.wait_for_load_state("domcontentloaded", timeout=20000)
        time.sleep(2)
        _save_debug_screenshot(page, "confirmation")
        print("[Reed Apply] Application submitted! Screenshot saved to /tmp/reed_apply_confirmation.png")
        return True

    def _fill_form(self, page, cv_path: str, cover_letter_text: str) -> bool:
        """Fill the Reed application form. Returns True if at least the CV was handled."""
        success = False

        self._try_fill(page, "first_name", self._first_name())
        self._try_fill(page, "last_name", self._last_name())
        self._try_fill(page, "email", self.config.candidate_email)
        self._try_fill(page, "phone", self.config.candidate_phone)

        if cover_letter_text:
            # Reed limits cover notes to roughly 3000 chars
            self._try_fill(page, "cover_letter", cover_letter_text[:3000])

        # CV upload
        cv_input = self._find_element(page, "cv_upload", timeout=3000)
        if cv_input:
            cv_input.set_input_files(cv_path)
            print(f"[Reed Apply] CV uploaded: {Path(cv_path).name}")
            success = True
        else:
            print("[Reed Apply] Warning: CV upload field not found.")

        return success

    def _login(self, page, email: str, password: str) -> bool:
        """Attempt to log in to Reed."""
        email_field = self._find_element(page, "login_email", timeout=5000)
        password_field = self._find_element(page, "login_password", timeout=5000)
        if not email_field or not password_field:
            return False
        email_field.fill(email)
        password_field.fill(password)
        submit = self._find_element(page, "login_submit", timeout=3000)
        if submit:
            submit.click()
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            return True
        return False

    def _is_login_page(self, page) -> bool:
        """Heuristic: is this a login/sign-in page?"""
        url = page.url.lower()
        return any(kw in url for kw in ("login", "signin", "sign-in", "account/login"))

    def _find_element(self, page, selector_key: str, timeout: int = 3000):
        """Try each selector in order, return first match or None."""
        for selector in self._SELECTORS[selector_key]:
            try:
                el = page.wait_for_selector(selector, timeout=timeout, state="visible")
                if el:
                    return el
            except Exception:
                continue
        return None

    def _try_fill(self, page, selector_key: str, value: str):
        """Fill a field if found; silently skip if not."""
        if not value:
            return
        el = self._find_element(page, selector_key, timeout=2000)
        if el:
            el.fill(value)

    def _first_name(self) -> str:
        parts = (self.config.candidate_name or "").split()
        return parts[0] if parts else ""

    def _last_name(self) -> str:
        parts = (self.config.candidate_name or "").split()
        return " ".join(parts[1:]) if len(parts) > 1 else ""


def _save_debug_screenshot(page, label: str):
    path = f"/tmp/reed_apply_{label}.png"
    try:
        page.screenshot(path=path)
        print(f"[Reed Apply] Screenshot saved: {path}")
    except Exception:
        pass

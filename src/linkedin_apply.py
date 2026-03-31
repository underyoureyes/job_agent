"""
linkedin_apply.py - Automated LinkedIn Easy Apply Submitter
============================================================
Uses Playwright to automate LinkedIn Easy Apply applications.

Key differences from Reed:
  - Requires LinkedIn login (no guest apply)
  - Multi-step modal form — steps vary per job
  - Screening questions vary; unknown questions pause for manual input
  - Always pauses before final submission for user review

Requirements:
    pip install playwright
    playwright install chromium

.env fields needed:
    LINKEDIN_EMAIL=you@email.com
    LINKEDIN_PASSWORD=yourpassword
"""

import time
from pathlib import Path
from typing import Dict, Optional


LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_FEED_URL  = "https://www.linkedin.com/feed/"


def _extract_text_from_docx(docx_path: str) -> str:
    """Extract plain text from a .docx cover letter."""
    try:
        from docx import Document
        doc = Document(docx_path)
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        print(f"[LinkedIn Apply] Warning: could not read cover letter: {e}")
        return ""


class LinkedInApplyError(Exception):
    pass


class LinkedInApplicant:
    """
    Automates LinkedIn Easy Apply via Playwright.

    Usage:
        applicant = LinkedInApplicant(config)
        submitted = applicant.apply(job_dict)
    """

    # Max steps to click through before giving up (safety valve)
    _MAX_STEPS = 10

    def __init__(self, config, headless: bool = False):
        self.config = config
        self.headless = headless
        self._email    = getattr(config, "linkedin_apply_email",    "") or ""
        self._password = getattr(config, "linkedin_apply_password", "") or ""

    def apply(self, job: Dict) -> bool:
        """
        Apply to a LinkedIn job via Easy Apply.
        Opens a browser, logs in, fills the modal, pauses for user review,
        then submits on confirmation.
        Returns True if submitted, False if aborted or failed.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise LinkedInApplyError(
                "Playwright is not installed.\n"
                "Run: pip install playwright && playwright install chromium"
            )

        if not self._email or not self._password:
            raise LinkedInApplyError(
                "LinkedIn credentials not set.\n"
                "Add LINKEDIN_APPLY_EMAIL and LINKEDIN_APPLY_PASSWORD to your .env file."
            )

        job_url = job.get("url", "")
        if "linkedin.com" not in job_url:
            raise LinkedInApplyError(f"Not a LinkedIn URL: {job_url}")

        cv_path = job.get("tailored_cv_path")
        if not cv_path or not Path(cv_path).exists():
            raise LinkedInApplyError(f"Tailored CV not found: {cv_path}")

        letter_path = job.get("cover_letter_path")
        cover_letter_text = ""
        if letter_path and Path(letter_path).exists():
            cover_letter_text = _extract_text_from_docx(letter_path)

        print(f"\n[LinkedIn Apply] Starting: {job.get('title')} at {job.get('employer')}")
        print(f"[LinkedIn Apply] URL: {job_url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, slow_mo=80)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                accept_downloads=True,
                # Use a realistic user agent to reduce bot detection
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            try:
                result = self._run(page, job, cv_path, cover_letter_text)
            except KeyboardInterrupt:
                print("\n[LinkedIn Apply] Aborted by user.")
                result = False
            except Exception as e:
                print(f"\n[LinkedIn Apply] Error: {e}")
                _screenshot(page, "error")
                result = False
            finally:
                time.sleep(3)
                browser.close()

        return result

    # ── Main flow ──────────────────────────────────────────────────────────────

    def _run(self, page, job: Dict, cv_path: str, cover_letter_text: str) -> bool:
        # Step 1: Log in
        if not self._login(page):
            return False

        # Step 2: Open job page
        print("[LinkedIn Apply] Loading job page...")
        page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Step 3: Click Easy Apply
        if not self._click_easy_apply(page):
            return False

        # Step 4: Work through the modal steps
        submitted = self._handle_modal(page, cv_path, cover_letter_text)
        return submitted

    # ── Login ──────────────────────────────────────────────────────────────────

    def _login(self, page) -> bool:
        print("[LinkedIn Apply] Logging in...")
        page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)

        # Already logged in?
        if any(k in page.url for k in ("feed", "mynetwork", "jobs/search")):
            print("[LinkedIn Apply] Already logged in.")
            return True

        # Try to fill the login form with several fallback selectors
        email_selectors = ['#username', 'input[name="session_key"]',
                           'input[autocomplete="username"]', 'input[type="email"]']
        pwd_selectors   = ['#password', 'input[name="session_password"]',
                           'input[autocomplete="current-password"]', 'input[type="password"]']

        email_field = self._find_one(page, email_selectors, timeout=6000)
        pwd_field   = self._find_one(page, pwd_selectors,   timeout=4000)

        if not email_field or not pwd_field:
            # Form not found — ask user to log in manually in the open browser
            print("\n[LinkedIn Apply] Could not find login form automatically.")
            print("  Please log in manually in the browser window, then press ENTER.")
            _screenshot(page, "login_manual")
            try:
                input()
            except KeyboardInterrupt:
                return False
        else:
            email_field.fill(self._email)
            time.sleep(0.3)
            pwd_field.fill(self._password)
            time.sleep(0.3)

            submit = self._find_one(page, ['button[type="submit"]',
                                           'button[data-litms-control-urn*="login"]'],
                                    timeout=4000)
            if submit:
                submit.click()
                page.wait_for_load_state("domcontentloaded", timeout=20000)
                time.sleep(2)

        # Handle security challenge / CAPTCHA
        if any(k in page.url for k in ("checkpoint", "challenge", "authwall")):
            print("\n[LinkedIn Apply] LinkedIn is showing a security challenge.")
            print("  Please complete it in the browser, then press ENTER.")
            try:
                input()
            except KeyboardInterrupt:
                return False
            page.wait_for_load_state("domcontentloaded", timeout=30000)

        if any(k in page.url for k in ("feed", "jobs", "mynetwork")):
            print("[LinkedIn Apply] Login successful.")
            return True

        # Not clearly logged in — let the user decide whether to continue
        print(f"[LinkedIn Apply] Login state unclear — current URL: {page.url}")
        print("  If you are logged in, press ENTER to continue. Otherwise Ctrl+C to abort.")
        _screenshot(page, "login_result")
        try:
            input()
        except KeyboardInterrupt:
            return False
        return True

    # ── Easy Apply button ──────────────────────────────────────────────────────

    def _click_easy_apply(self, page) -> bool:
        """Find and click the Easy Apply button. Returns False if not found."""
        # Wait for the job details panel to fully render (LinkedIn fires background
        # requests indefinitely so networkidle never fires — use a fixed pause instead)
        time.sleep(4)

        # Scroll the top-card into view — button is sometimes below the fold
        try:
            page.evaluate("window.scrollTo(0, 300)")
            time.sleep(1)
        except Exception:
            pass

        selectors = [
            'button.jobs-apply-button[aria-label*="Easy Apply"]',
            'button[aria-label*="Easy Apply"]',
            'button.jobs-apply-button:has-text("Easy Apply")',
            '.jobs-apply-button:has-text("Easy Apply")',
            '.jobs-unified-top-card__content button:has-text("Easy Apply")',
            '.job-details-jobs-unified-top-card__container--two-pane button:has-text("Easy Apply")',
            'button:has-text("Easy Apply")',
        ]
        for sel in selectors:
            try:
                btn = page.wait_for_selector(sel, timeout=4000, state="visible")
                if btn:
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    print("[LinkedIn Apply] Clicked Easy Apply.")
                    time.sleep(1)
                    return True
            except Exception:
                continue

        # Check for a regular (non-Easy Apply) apply button — means external application
        try:
            all_buttons = page.query_selector_all("button")
            for btn in all_buttons:
                text = btn.inner_text().strip().lower()
                label = (btn.get_attribute("aria-label") or "").lower()
                if "apply" in text or "apply" in label:
                    full_text = btn.inner_text().strip()
                    print(f"[LinkedIn Apply] Found an Apply button: '{full_text}'")
                    if "easy" not in text and "easy" not in label:
                        print("[LinkedIn Apply] This job uses external Apply — not Easy Apply.")
                        print("         The button opens the employer's own website.")
                        print("         Auto-apply is only supported for LinkedIn Easy Apply jobs.")
                        return False
        except Exception:
            pass

        print(f"[LinkedIn Apply] No apply button found. Current URL: {page.url}")
        _screenshot(page, "no_easy_apply")
        return False

    # ── Modal step handler ─────────────────────────────────────────────────────

    def _handle_modal(self, page, cv_path: str, cover_letter_text: str) -> bool:
        """
        Navigate the Easy Apply modal step by step.
        On each step:
          - Fill contact fields if present
          - Upload CV if a file input is visible
          - Fill cover letter textarea if present
          - If unknown question fields exist, pause for the user
          - Click Next/Continue, repeat until Submit appears
        """
        modal_selector = '.artdeco-modal, .jobs-easy-apply-content'

        for step in range(1, self._MAX_STEPS + 1):
            try:
                page.wait_for_selector(modal_selector, timeout=8000, state="visible")
            except Exception:
                print(f"[LinkedIn Apply] Modal not visible on step {step}.")
                _screenshot(page, f"no_modal_step{step}")
                break

            print(f"[LinkedIn Apply] Step {step}...")

            # Fill known fields
            self._fill_contact_fields(page)
            self._handle_phone_field(page)
            self._upload_cv_if_present(page, cv_path)
            self._fill_cover_letter_if_present(page, cover_letter_text)

            # Detect unanswered required questions — pause for user
            if self._has_unanswered_required(page):
                print("\n[LinkedIn Apply] This step has questions that need your input.")
                print("  Please fill them in the browser window, then press ENTER.")
                try:
                    input()
                except KeyboardInterrupt:
                    print("[LinkedIn Apply] Aborted.")
                    return False

            # Check for Submit button (final step)
            submit_btn = self._find_one(page, [
                'button[aria-label="Submit application"]',
                'button:has-text("Submit application")',
            ], timeout=1500)
            if submit_btn:
                return self._confirm_and_submit(page, submit_btn)

            # Check for Review button (second-to-last step)
            review_btn = self._find_one(page, [
                'button[aria-label="Review your application"]',
                'button:has-text("Review your application")',
                'button:has-text("Review")',
            ], timeout=1500)
            if review_btn:
                review_btn.click()
                time.sleep(1)
                continue

            # Otherwise click Next/Continue
            next_btn = self._find_one(page, [
                'button[aria-label="Continue to next step"]',
                'button:has-text("Next")',
                'button:has-text("Continue")',
                'footer button.artdeco-button--primary',
            ], timeout=3000)
            if next_btn:
                next_btn.click()
                time.sleep(1)
            else:
                print(f"[LinkedIn Apply] No Next/Submit button found on step {step}.")
                _screenshot(page, f"stuck_step{step}")
                print("  Please advance the form manually, then press ENTER.")
                try:
                    input()
                except KeyboardInterrupt:
                    return False

        print("[LinkedIn Apply] Reached max step limit without submitting.")
        return False

    def _confirm_and_submit(self, page, submit_btn) -> bool:
        """Pause for user review, then click Submit."""
        print("\n" + "─" * 60)
        print("  The application is ready to submit.")
        print("  Review the browser window, then press ENTER to submit.")
        print("  Press Ctrl+C to abort without submitting.")
        print("─" * 60)
        try:
            input()
        except KeyboardInterrupt:
            print("[LinkedIn Apply] Aborted by user.")
            return False

        submit_btn.click()
        time.sleep(2)
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        _screenshot(page, "confirmation")
        print("[LinkedIn Apply] Application submitted!")
        return True

    # ── Form field helpers ─────────────────────────────────────────────────────

    def _fill_contact_fields(self, page):
        """Fill name/email/location fields if they appear empty."""
        self._fill_if_empty(page, 'input[id*="firstName"], input[autocomplete="given-name"]',
                            self._first_name())
        self._fill_if_empty(page, 'input[id*="lastName"], input[autocomplete="family-name"]',
                            self._last_name())
        self._fill_if_empty(page, 'input[type="email"], input[autocomplete="email"]',
                            self.config.candidate_email)

    def _handle_phone_field(self, page):
        """Fill phone number. LinkedIn sometimes splits country code and number."""
        phone = self.config.candidate_phone or ""
        if not phone:
            return

        # Try the combined field first
        combined = self._find_one(page, [
            'input[id*="phoneNumber"]',
            'input[name*="phone"]',
            'input[type="tel"]',
        ], timeout=1500)
        if combined:
            # Only fill if empty
            current = combined.input_value() if hasattr(combined, "input_value") else ""
            if not current.strip():
                combined.fill(phone)

    def _upload_cv_if_present(self, page, cv_path: str):
        """Upload CV if a file input is visible in the modal."""
        file_input = self._find_one(page, [
            '.jobs-document-upload input[type="file"]',
            '.jobs-easy-apply-form-section input[type="file"]',
            'input[type="file"][accept*=".pdf"]',
            'input[type="file"][accept*=".doc"]',
            'input[type="file"]',
        ], timeout=1500)
        if file_input:
            file_input.set_input_files(cv_path)
            print(f"[LinkedIn Apply] CV uploaded: {Path(cv_path).name}")
            time.sleep(1)

    def _fill_cover_letter_if_present(self, page, cover_letter_text: str):
        """Paste cover letter text if a cover letter textarea is visible."""
        if not cover_letter_text:
            return
        textarea = self._find_one(page, [
            '.jobs-easy-apply-form-section--cover-letter textarea',
            'textarea[id*="cover"]',
            'textarea[name*="cover"]',
            'textarea[placeholder*="cover"]',
            'textarea[placeholder*="Cover"]',
        ], timeout=1500)
        if textarea:
            current = textarea.input_value() if hasattr(textarea, "input_value") else ""
            if not current.strip():
                textarea.fill(cover_letter_text[:3000])
                print("[LinkedIn Apply] Cover letter filled.")

    def _has_unanswered_required(self, page) -> bool:
        """
        Heuristic: are there required input/select fields in the modal
        that are still empty (i.e. screening questions we can't answer)?
        """
        try:
            # Look for required fields that aren't name/email/phone/file
            fields = page.query_selector_all(
                '.artdeco-modal input[required]:not([type="file"]):not([type="hidden"]), '
                '.artdeco-modal select[required], '
                '.artdeco-modal textarea[required]'
            )
            for field in fields:
                el_id = (field.get_attribute("id") or "").lower()
                el_name = (field.get_attribute("name") or "").lower()
                # Skip fields we already handle
                if any(k in el_id + el_name for k in
                       ("firstname", "lastname", "email", "phone", "cover")):
                    continue
                value = ""
                try:
                    value = field.input_value()
                except Exception:
                    pass
                if not value.strip():
                    return True
        except Exception:
            pass
        return False

    # ── Utilities ──────────────────────────────────────────────────────────────

    def _find_one(self, page, selectors: list, timeout: int = 3000):
        """Return first matching visible element, or None."""
        for sel in selectors:
            try:
                el = page.wait_for_selector(sel, timeout=timeout, state="visible")
                if el:
                    return el
            except Exception:
                continue
        return None

    def _fill_if_empty(self, page, selector: str, value: str):
        """Fill a field only if it is currently empty."""
        if not value:
            return
        try:
            el = page.wait_for_selector(selector, timeout=1500, state="visible")
            if el:
                current = ""
                try:
                    current = el.input_value()
                except Exception:
                    pass
                if not current.strip():
                    el.fill(value)
        except Exception:
            pass

    def _first_name(self) -> str:
        parts = (self.config.candidate_name or "").split()
        return parts[0] if parts else ""

    def _last_name(self) -> str:
        parts = (self.config.candidate_name or "").split()
        return " ".join(parts[1:]) if len(parts) > 1 else ""


def _screenshot(page, label: str):
    path = f"/tmp/linkedin_apply_{label}.png"
    try:
        page.screenshot(path=path)
        print(f"[LinkedIn Apply] Screenshot: {path}")
    except Exception:
        pass

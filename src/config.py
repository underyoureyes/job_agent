"""
config.py - Central configuration for the Job Application Agent
===============================================================
Personal details, API keys and candidate info are loaded from a .env file
in the project root. This file contains only defaults and structure —
you never need to edit it when updating the app.

To set up: copy .env.template to .env and fill in your values.
"""

import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

# ── Load .env file if present ─────────────────────────────────────────────────
# Uses python-dotenv if installed, otherwise reads manually.
# This means secrets stay in .env and never get overwritten by app updates.

def _load_env_file(path: Path, override: bool = False):
    """Load a .env file into os.environ."""
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=override)
    except ImportError:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if override or key not in os.environ:
                    os.environ[key] = val

# 1. Bundled .env (API keys, candidate details — ships with the app)
# When frozen by PyInstaller, all bundled files land in sys._MEIPASS (named "bundled.env").
# In development they live at the project root as ".env".
if getattr(sys, "frozen", False):
    _env_path = Path(sys._MEIPASS) / "bundled.env"
else:
    _env_path = Path(__file__).parent.parent / ".env"
_load_env_file(_env_path, override=False)

# 2. User prefs file — survives app reinstalls, stores output_dir etc.
#    Lives at ~/Library/Application Support/JobAgent/user.env on Mac,
#    or ~/.config/JobAgent/user.env on other platforms.
_app_support = (
    Path.home() / "Library" / "Application Support" / "JobAgent"
    if sys.platform == "darwin"
    else Path.home() / ".config" / "JobAgent"
)
USER_PREFS_PATH = _app_support / "user.env"
_app_support.mkdir(parents=True, exist_ok=True)
_load_env_file(USER_PREFS_PATH, override=True)  # user prefs win over bundled .env


@dataclass
class Config:
    # ── Candidate ────────────────────────────────────────────────────────────
    # These read from .env — never hardcode here
    candidate_name:     str = field(default_factory=lambda: os.getenv("CANDIDATE_NAME",     "YOUR_NAME"))
    candidate_email:    str = field(default_factory=lambda: os.getenv("CANDIDATE_EMAIL",    "your@email.com"))
    candidate_phone:    str = field(default_factory=lambda: os.getenv("CANDIDATE_PHONE",    "+44 7XXX XXXXXX"))
    candidate_linkedin: str = field(default_factory=lambda: os.getenv("CANDIDATE_LINKEDIN", "https://linkedin.com/in/yourprofile"))
    candidate_location: str = field(default_factory=lambda: os.getenv("CANDIDATE_LOCATION", "London, UK"))
    candidate_address:  str = field(default_factory=lambda: os.getenv("CANDIDATE_ADDRESS",  ""))
    candidate_address2: str = field(default_factory=lambda: os.getenv("CANDIDATE_ADDRESS2", ""))

    # ── Reed auto-apply credentials (optional) ───────────────────────────────
    reed_email:    str = field(default_factory=lambda: os.getenv("REED_LOGIN_EMAIL",    ""))
    reed_password: str = field(default_factory=lambda: os.getenv("REED_LOGIN_PASSWORD", ""))

    # ── LinkedIn auto-apply credentials (required for Easy Apply) ────────────
    linkedin_apply_email:    str = field(default_factory=lambda: os.getenv("LINKEDIN_APPLY_EMAIL",    ""))
    linkedin_apply_password: str = field(default_factory=lambda: os.getenv("LINKEDIN_APPLY_PASSWORD", ""))

    # ── Session summary email ─────────────────────────────────────────────────
    notify_email:   str = field(default_factory=lambda: os.getenv("NOTIFY_EMAIL",   ""))
    smtp_from:      str = field(default_factory=lambda: os.getenv("SMTP_FROM",      ""))
    smtp_host:      str = field(default_factory=lambda: os.getenv("SMTP_HOST",      "smtp.gmail.com"))
    smtp_port:      str = field(default_factory=lambda: os.getenv("SMTP_PORT",      "587"))
    smtp_user:      str = field(default_factory=lambda: os.getenv("SMTP_USER",      ""))
    smtp_password:  str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD",  ""))

    # ── Education ─────────────────────────────────────────────────────────────
    current_degree: str = "MSc Public Policy, King's College London (2024-2025)"

    # ── Job Search Parameters ─────────────────────────────────────────────────
    target_field: str = "Public Policy"

    search_keywords: List[str] = field(default_factory=lambda: [
        "public policy",
        "policy analyst",
        "policy advisor",
        "policy officer",
        "policy research",
        "public affairs",
        "parliamentary research",
        "politics journalist",
        "policy assistant",
        "policy fellow",
        "government affairs",
        "research and policy",
        "think-tank",
    ])

    search_location:    str  = "London"
    search_radius_miles: int = 5
    include_remote:     bool = True
    max_job_age_days:   int  = 5
    min_salary_gbp:     int  = 30000
    max_salary_gbp:     int  = 0      # 0 = no upper limit

    # ── Scoring ───────────────────────────────────────────────────────────────
    min_match_score:     int  = 65
    ats_mode:            bool = True
    max_tailored_per_scan: int = 0

    # ── Seniority filter ──────────────────────────────────────────────────────
    seniority_filter_titles: List[str] = field(default_factory=lambda: [
        " manager",
        "affairs manager",
        "board trustee",
        "c-suite",
        "chair",
        "chief ",
        "cio",
        "deputy director",
        "director",
        "head of",
        "lead",
        "lead ",
        "manager",
        "manager -",
        "manager —",
        "manager,",
        "managing director",
        "partner",
        "policy manager",
        "PQE",
        "principal ",
        "professor",
        "project lead",
        "project manager",
        "senior",
        "senior manager",
        "stakeholder relations manager",
        "vice president",
        "vice-chair",
        "VP",
        "vp ",
    ])

    seniority_filter_experience: List[str] = field(default_factory=lambda: [
        "5+ years", "5 years experience", "five years experience",
        "6+ years", "7+ years", "7 years experience", "seven years",
        "8+ years", "10+ years", "minimum 5 years",
        "at least 5 years", "at least 7 years",
        "senior professional", "proven track record of 5",
    ])

    # ── Irrelevant title filter ────────────────────────────────────────────────
    irrelevant_filter_titles: List[str] = field(default_factory=lambda: [
        "account executive",
        "account management",
        "account manager",
        "accountant",
        "admin",
        "admin assistant",
        "admin coordinator",
        "administration assistant",
        "administrative",
        "administrative assistant",
        "administrator",
        "aml analyst",
        "analyst (banking)",
        "analytics",
        "application support",
        "applications support",
        "applied formal methods",
        "applied research",
        "apprentice",
        "arabic",
        "architect",
        "artificial intelligence",
        "asset owner",
        "assistant to ceo",
        "associate planner",
        "asssurance reviewer",
        "assurance reviewer",
        "assurnace",
        "attendance officer",
        "auditor",
        "banking analyst",
        "brand",
        "building surveyor",
        "business analyst",
        "business assistant",
        "business development",
        "business support",
        "cabin crew",
        "caseworker",
        "casual",
        "cdd analyst",
        "chef",
        "client advisor",
        "coach",
        "commercial advisor",
        "commercial analyst",
        "commercial insurance broker",
        "committee specialist",
        "communication support",
        "communications agent",
        "communications specialist",
        "community associate",
        "community patrol",
        "company secretary",
        "compliance",
        "consultant",
        "coordinator",
        "corporate affairs",
        "councel",
        "credit analyst",
        "credit research",
        "criminal investigator",
        "crm executive",
        "customer research",
        "customer sevices",
        "cyber security",
        "data analyst",
        "data engineer",
        "data entry",
        "data officer",
        "data protection",
        "data quailty",
        "data quality analyst",
        "data research",
        "data science trainee",
        "data scientist",
        "developer",
        "development coordinator",
        "devops",
        "diary researcher",
        "digital researcher",
        "driver",
        "dutch speaking",
        "ecommerce",
        "endowment",
        "energy market",
        "engagement officer",
        "engineer",
        "engineering",
        "equity research",
        "escalation specialist",
        "events coordinator",
        "examinations officer",
        "executive assistant",
        "executive operations",
        "facilities",
        "fellow",
        "film editor",
        "finance analyst",
        "financial advisor",
        "financial analyst",
        "financial assistant",
        "fixed income",
        "fp&a",
        "fpna",
        "freelance",
        "funding officer",
        "geopolitical analyst",
        "global mobility specialist",
        "grants officer",
        "health worker",
        "hedge fund",
        "helpdesk",
        "housekeeping supervisor",
        "housing advisor",
        "housing officer",
        "hr",
        "hub assistant",
        "infrastructure",
        "innovation officer",
        "insurance",
        "insurance advisor",
        "insurance analyst",
        "insurance officer",
        "intelligence analyst",
        "intern",
        "intervention officer",
        "investment analyst",
        "investments facilitation officer",
        "ir analyst",
        "it support",
        "join our iconic board of trustees",
        "kurdish",
        "lawyer",
        "lecturer",
        "legal advisor",
        "legal aid",
        "legal assistant",
        "licensing inspector",
        "litigation",
        "machine learning",
        "maintenance desk officer",
        "management trainee",
        "market research analyst",
        "marketing",
        "marketing executive",
        "marketing manager",
        "media analyst",
        "medical advisor",
        "modeling",
        "modelling",
        "mortgage",
        "multi-asset",
        "natural language",
        "nurse",
        "office management",
        "operations",
        "orthopaedic",
        "osint",
        "pa",
        "paralegal",
        "paraplanner",
        "parts advisor",
        "people advisor",
        "physicist",
        "pit boss",
        "planning officer",
        "practitioner",
        "premises officer",
        "press officer",
        "pricing analyst",
        "prison",
        "private equity analyst",
        "probation",
        "procurement",
        "producer",
        "product analyst",
        "product designer",
        "product governance",
        "production assistant",
        "project assistant",
        "project research officer",
        "project support officer",
        "psychology",
        "quantitative trading",
        "r&d",
        "reception",
        "receptionist",
        "records officer",
        "regional administrator",
        "research analyst",
        "reservation agent",
        "risk analyst",
        "risk pricing",
        "sales",
        "sales advisor",
        "science specialist",
        "scientist",
        "security consultant",
        "security guard",
        "security officer",
        "service advisor",
        "service improvement officer",
        "she advisor",
        "soc analyst",
        "social media assistant",
        "social worker",
        "software engineer",
        "solicitor",
        "solutions architect",
        "sous chef",
        "statistical",
        "stop gap",
        "strategy & operations",
        "student wellbeing officer",
        "style editor",
        "support and progression officers",
        "support worker",
        "systems analyst",
        "systems specialist",
        "talent pool",
        "tax accountant",
        "teacher",
        "teaching",
        "team assistant",
        "tech research",
        "town planner",
        "trade finance",
        "transfer pricing",
        "treasurer",
        "tutor",
        "underwriting assistant",
        "UX",
        "visiting officer",
        "voluntary",
        "volunteer",
        "warehouse",
        "wellbeing adviser",
        "workplace services",
        "リサーチ担当",
    ])

    # ── Location filter ────────────────────────────────────────────────────────
    exclude_locations: List[str] = field(default_factory=lambda: [
        "amsterdam",
        "australia",
        "belgium",
        "berlin",
        "brussels",
        "dublin",
        "france",
        "germany",
        "hong kong",
        "ireland",
        "netherlands",
        "new york",
        "paris",
        "singapore",
        "switzerland",
        "sydney",
        "united states",
        "usa",
        "zurich",
    ])

    # ── Job Boards ────────────────────────────────────────────────────────────
    # All API keys read from .env — never hardcode here
    reed_api_key:    str = field(default_factory=lambda: os.getenv("REED_API_KEY",    ""))
    adzuna_app_id:   str = field(default_factory=lambda: os.getenv("ADZUNA_APP_ID",   ""))
    adzuna_app_key:  str = field(default_factory=lambda: os.getenv("ADZUNA_APP_KEY",  ""))

    scan_civil_service:   bool = True
    scan_guardian:        bool = True
    scan_linkedin:        bool = True
    scan_totaljobs:       bool = False  # blocks scrapers (Cloudflare)
    scan_w4mpjobs:        bool = True
    scan_charityjob:      bool = True
    linkedin_manual_file: str  = None

    # ── AI (Claude API) ───────────────────────────────────────────────────────
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    claude_model:      str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"))

    # ── File Paths ────────────────────────────────────────────────────────────
    # When running as a PyInstaller .app, __file__ is inside a temp extraction dir.
    # User data (database, logs, CV) must live somewhere persistent — we use
    # ~/Library/Application Support/JobAgent/ on Mac or the project root in dev.
    base_dir: Path = field(default_factory=lambda: _app_support if getattr(sys, "frozen", False) else Path(__file__).parent.parent)
    db_path: Path = field(default_factory=lambda: _app_support / "applications.db" if getattr(sys, "frozen", False) else Path(__file__).parent.parent / "applications.db")
    logs_dir: Path = field(default_factory=lambda: _app_support / "logs" if getattr(sys, "frozen", False) else Path(__file__).parent.parent / "logs")
    base_cv_path: Path = field(default_factory=lambda: _app_support / "base_cv.md" if getattr(sys, "frozen", False) else Path(__file__).parent.parent / "base_cv.md")
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", str(Path.home() / "JobAgent" / "output"))))

    show_filtered_in_ui: bool = False

    def __post_init__(self):
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def validate(self) -> List[str]:
        warnings = []
        if not self.anthropic_api_key:
            warnings.append("ANTHROPIC_API_KEY not set in .env — CV tailoring will not work.")
        if not self.reed_api_key:
            warnings.append("REED_API_KEY not set in .env — Reed scanning disabled.")
        if not self.adzuna_app_id:
            warnings.append("ADZUNA_APP_ID not set in .env — Adzuna scanning disabled.")
        if self.candidate_name == "YOUR_NAME":
            warnings.append("CANDIDATE_NAME not set in .env.")
        if not self.base_cv_path.exists():
            warnings.append(f"base_cv.md not found at {self.base_cv_path}.")
        return warnings

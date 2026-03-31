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
    min_salary_gbp:     int  = 25000
    max_salary_gbp:     int  = 0      # 0 = no upper limit

    # ── Scoring ───────────────────────────────────────────────────────────────
    min_match_score:     int  = 65
    ats_mode:            bool = True
    max_tailored_per_scan: int = 0

    # ── Seniority filter ──────────────────────────────────────────────────────
    seniority_filter_titles: List[str] = field(default_factory=lambda: [
        "head of", "director", "chief ", "vp ", "vice president", "VP",
        "deputy director", "managing director", "c-suite", "cio",
        "senior manager", "manager,", "manager -", "manager —", "project manager",
        "lead ", "principal ", "senior",
        " manager", "project lead", "manager",
        "stakeholder relations manager", "policy manager",
        "affairs manager", "partner", "lead", "chair", "vice-chair", "PQE", "professor", "board trustee",
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
        # IT / tech
        "software engineer", "developer", "devops", "soc analyst",
        "cyber security", "it support", "helpdesk", "data engineer",
        "data entry", "machine learning", "infrastructure", "data scientist", "data analyst",
        "scientist", "natural language", "systems analyst", "artificial intelligence",
        "data protection", "service advisor", "solutions architect", "systems specialist","data science trainee", "UX", "tech research"
        # Mathematical / scientific
        "statistical", "engineering", "science specialist", "applied research", "applied formal methods","engineer", "modelling","modeling",
        # Medical
        "physicist", "psychology", "orthopaedic",
        # Finance / investment
        "accountant", "solicitor", "legal aid", "auditor",
        "financial advisor", "mortgage", "insurance officer","financial assistant",
        "equity research", "credit analyst", "credit research",
        "aml analyst", "cdd analyst", "risk pricing",
        "quantitative trading", "hedge fund", "investment analyst",
        "financial analyst", "finance analyst", "pricing analyst",
        "business analyst", "data analyst", "research analyst",
        "fpna", "fp&a", "endowment", "multi-asset", "treasurer", "trade finance", "tax accountant", "fixed income",
        # Sales / marketing
        "sales", "marketing executive", "marketing manager",
        "account manager", "business development",
        # Teaching
        "teacher", "teaching",
        # Other operational / admin
        "sous chef", "chef", "security officer", "security guard",
        "warehouse", "driver", "receptionist", "administrator",
        "social worker", "probation", "caseworker",
        "architect", "procurement", "facilities",
        "events coordinator", "regional administrator",
        "product governance", "customer research",
        "energy market", "geopolitical analyst", "osint",
        "application support", "commercial analyst",
        "market research analyst", "data research",
        "insurance analyst", "risk analyst", "asset owner",
        "media analyst", "intelligence analyst", "fellow", "film editor",
        "arabic", "kurdish", "coach", "administrative assistant", "office management", "press officer",
        "marketing", "engagement officer", "hr", "maintenance desk officer", "security consultant", "compliance",
        "committee specialist", "medical advisor", "product designer", "building surveyor", "global mobility specialist",
        "assistant to ceo", "people advisor", "she advisor", "sales advisor", "transfer pricing",
        "service improvement officer", "commercial insurance broker", "digital researcher", "dutch speaking",
        "business support", "business assistant", "executive operations", "communications specialist",
        "innovation officer", "corporate affairs", "records officer",
        "product analyst", "executive assistant", "account executive", "strategy & operations",
        "project support officer", "support and progression officers",
        "hub assistant", "community associate", "development coordinator", "team assistant",
        "administrative", "project assistant", "prison", "project research officer",
        "grants officer", "join our iconic board of trustees", "diary researcher",
        "crm executive", "admin assistant", "admin coordinator","administration assistant", "admin",
        # Internships removed for now
        "intern", "volunteer","talent pool","casual","freelance","voluntary","stop gap",
        
        "apprentice","insurance advisor","reception","reservation agent","customer sevices",
        "planning officer","assurnace", "リサーチ担当", "health worker","housekeeping supervisor","applications support",
        "community patrol","insurance","town planner","housing officer","funding officer","premises officer","parts advisor",
        "consultant","ecommerce","client advisor","style editor","coordinator", "social media assistant","management trainee",
        "cabin crew","journalist","operations","lecturer","paraplanner","producer","data officer","tutor","practitioner", "r&d","brand",
        "councel","criminal investigator","commercial advisor","intervention officer","workplace services","communications agent",
        "account management","communication support","analytics","attendance officer","support worker","company secretary","litigation",
        "wellbeing adviser","pa","banking analyst","data quailty","licensing inspector","nurse","pit boss","lawyer","solicitor","marketing executive",
        "paralegal", "investments facilitation officer","analyst (banking)","underwriting assistant","asssurance reviewer", "escalation specialist",
        "production assistant","private equity analyst","data quality analyst","ir analyst","legal advisor","examinations officer",
        "legal assistant","visiting officer", "assurance reviewer", "housing advisor","associate planner","student wellbeing officer"

    ])

    # ── Location filter ────────────────────────────────────────────────────────
    exclude_locations: List[str] = field(default_factory=lambda: [
        "brussels", "belgium", "amsterdam", "netherlands",
        "paris", "france", "berlin", "germany",
        "dublin", "ireland", "new york", "usa", "united states",
        "singapore", "hong kong", "sydney", "australia",
        "zurich", "zurich", "switzerland",
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

# Project Structure & Conventions

This file defines how Claude should structure, organise, and develop Python projects in this style. Follow these patterns when creating or extending any project in this codebase.

---

## Tech Stack

- **Language**: Python 3.10+
- **UI**: Tkinter (desktop apps) or Flask/FastAPI + HTML/CSS/JS (web apps) — choose based on project needs
- **Database**: SQLite3 via a dedicated Tracker class
- **AI Integration**: Anthropic Claude API (`anthropic` SDK)
- **Browser Automation**: Playwright
- **Web Scraping**: BeautifulSoup4 + requests
- **Document Generation**: python-docx, WeasyPrint / LibreOffice fallback
- **CLI Output**: Rich (tables, panels, colour)
- **Testing**: pytest with tmp_path fixtures
- **Config**: python-dotenv + dataclass-based Config

---

## Directory Structure

```
project_root/
├── src/
│   ├── main.py               # CLI orchestrator (argparse subcommands)
│   ├── config.py             # Central Config dataclass + .env loading
│   ├── conftest.py           # Pytest fixtures
│   ├── tracker.py            # SQLite wrapper (one class, one file)
│   ├── log_capture.py        # Stdout capture for live WebSocket log streaming
│   ├── <domain>.py           # Core domain modules (scanner, processor, etc.)
│   ├── api/
│   │   └── app.py            # FastAPI server — REST + WebSocket endpoints
│   └── templates/
│       └── index.html        # Single-page web UI (Bootstrap 5, ag-Grid, SheetJS)
├── tests/
│   ├── unit/
│   │   └── test_<module>.py
│   └── integration/
│       └── test_e2e_mock.py
├── output/                   # Generated files (gitignored)
├── .env                      # Secrets (gitignored)
├── .env.example              # Template showing all required env vars
├── .gitignore
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## Architecture Layers

Always keep these three layers cleanly separated:

### 1. Data Layer
- One `Tracker` class per domain entity, wrapping SQLite
- All DB access through the Tracker — no raw SQL elsewhere
- Schema created in `_init_db()` called from `__init__`
- Use context managers: `with self._connect() as conn`
- Include an `events` audit table for status transitions

### 2. Orchestration Layer (Business Logic)
- `main.py` coordinates phases; each phase is a standalone function
- `config.py` holds a single `Config` dataclass — all settings in one place
- Domain classes (`Scanner`, `Tailor`, etc.) receive `Config` in their constructor
- Free/cheap operations always run before expensive ones (e.g. API calls)

### 3. UI Layer (FastAPI + HTML)
- `api/app.py` is the FastAPI entry point
- Routes grouped by domain within `api/app.py`
- Templates in `templates/`, static assets in `static/`
- JSON API endpoints return consistent `{"data": ..., "error": null}` envelopes
- WebSocket at `/ws/logs` for live task output streaming
- **UI never talks to the DB directly — it calls Tracker/service methods.**

---

## Configuration

### Three-tier system (in order of precedence):
1. **User preferences file** — platform-specific path (e.g. `~/Library/Application Support/<App>/user.env` on macOS)
2. **`.env` file** — project root, gitignored, loaded with `override=True`
3. **Hardcoded defaults** in the `Config` dataclass

### Config dataclass conventions:
```python
@dataclass
class Config:
    # Candidate / user details
    candidate_name: str = ""

    # API keys
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))

    # Search / behaviour parameters
    search_keywords: list = field(default_factory=lambda: ["policy", "analyst"])
    min_match_score: int = 60

    # File paths
    db_path: str = field(default_factory=lambda: os.path.join(os.getcwd(), "data.db"))
    output_dir: str = field(default_factory=lambda: os.path.join(os.getcwd(), "output"))

    # Feature toggles
    enable_auto_apply: bool = False

    def validate(self) -> list[str]:
        """Return a list of warning strings for missing/invalid config."""
        ...
```

- Never hardcode secrets — always read from env vars
- `validate()` returns warnings, not exceptions
- Detect frozen (PyInstaller) vs dev environment: `getattr(sys, "frozen", False)`

---

## Naming Conventions

| Thing | Convention | Example |
|---|---|---|
| Files | `snake_case.py` | `job_scanner.py` |
| Classes | `PascalCase` | `JobScanner`, `CVTailor` |
| API route functions | `snake_case` verb | `get_jobs()`, `start_scan()` |
| Methods | `snake_case` | `scan_all()`, `get_jobs_by_status()` |
| Private methods | `_underscore_prefix` | `_is_too_senior()`, `_build_sidebar()` |
| Constants | `ALL_CAPS` | `BG`, `SCORE_PROMPT`, `STATUS_COLOURS` |
| UI vars | suffix with type | `_search_var` (StringVar), `_title_lbl` (Label) |
| Predicates | verb form | `has_activity()`, `job_exists()`, `is_easy_apply()` |

---

## Data Persistence Patterns

### SQLite Tracker class
```python
class ApplicationTracker:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS ...")
```

- `add_item(dict) -> int` — returns new row id
- `get_item(id) -> dict`
- `item_exists(unique_field) -> bool`
- `update_status(id, status, detail)`
- `get_items_by_status(status) -> list[dict]`
- Always include an `events` audit table with foreign key to main table

### Status state machine
Define status flow as an ordered list constant:
```python
STATUS_FLOW = ["discovered", "pending", "processed", "approved", "submitted", "done"]
STATUS_COLOURS = {"discovered": "cyan", "approved": "green", "submitted": "blue"}
```

---

## UI Patterns (Web)

### API conventions
- All endpoints return JSON; errors use `HTTPException` with a detail string
- Background tasks run via `asyncio.to_thread()` with a global `_task_running` flag
- Live log output is streamed over WebSocket (`/ws/logs`) using `_LogCapture`
- State (config, tracker, session) held in module-level globals set at startup

### Threading
Long-running operations (scans, API calls) run in a thread pool:
```python
asyncio.create_task(asyncio.to_thread(_do))   # fire-and-forget
await asyncio.to_thread(_do)                  # wait for result
```

---

## AI / Claude API Integration

### Prompt conventions
- Store prompts as module-level string constants in the relevant module
- Use `{format_field}` placeholders for dynamic content
- One prompt per task; keep prompts focused
- Specify output format explicitly in the prompt (e.g. "respond with valid JSON only")

```python
SCORE_PROMPT = """
You are evaluating a job posting against a candidate's CV.

Job description:
{job_text}

Candidate CV:
{cv_text}

Respond with valid JSON only:
{{"score": 0-100, "reason": "...", "strengths": [...], "gaps": [...]}}
"""
```

### API client
```python
client = anthropic.Anthropic(api_key=config.anthropic_api_key)
response = client.messages.create(
    model=config.claude_model,
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
```

### Error handling
- Catch `anthropic.AuthenticationError` and `anthropic.RateLimitError` — re-raise immediately
- Catch all other exceptions, log with Rich, and continue gracefully
- Parse JSON responses with a try/except; fall back to a default on parse failure

---

## CLI (main.py) Patterns

```python
parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="command")

sub.add_parser("scan")
sub.add_parser("score")
sub.add_parser("status")

args = parser.parse_args()

if args.command == "scan":
    run_scan(config, tracker)
```

- Each phase is a top-level function: `run_scan()`, `run_score()`, etc.
- Use Rich for all output: `Console()`, `Panel()`, `Table()`
- Progress markers: `[→]` for actions, `[✓]` for success, `[⊘]` for filtered/skipped

---

## Testing Conventions

```python
# tests/unit/test_tracker.py
import pytest
from src.tracker import ApplicationTracker

@pytest.fixture
def db(tmp_path) -> ApplicationTracker:
    return ApplicationTracker(tmp_path / "test.db")

def _item(url: str = "https://example.com/job/1") -> dict:
    return {"title": "Analyst", "url": url, "employer": "ACME"}

class TestAdd:
    def test_returns_id(self, db):
        id_ = db.add_item(_item())
        assert isinstance(id_, int)

    def test_deduplicates_url(self, db):
        db.add_item(_item())
        db.add_item(_item())
        assert len(db.get_all()) == 1
```

- `tmp_path` fixture for temporary DBs — never use a real file in tests
- Factory helper functions (`_item()`) for building test data
- Group tests in classes by feature: `TestAdd`, `TestStatus`, `TestFilter`
- Mock external APIs with `unittest.mock.patch`
- Integration tests in `tests/integration/` use real DB, mock network only

---

## Error Handling

- Distinguish recoverable errors (log + continue) from fatal errors (re-raise)
- Billing/auth errors are always fatal — re-raise immediately
- Provide graceful fallbacks for optional features (e.g. PDF export falls back to .docx)
- Never silently swallow exceptions — always log with Rich

---

## Document Generation

When generating documents from templates:
1. Extract style fingerprint from user's template into a serialisable dataclass
2. Generate content as Markdown via Claude API
3. Convert Markdown → .docx (apply fingerprint styles)
4. Attempt PDF conversion in order: WeasyPrint → LibreOffice → AppleScript
5. Save all outputs under `output/<entity_id>_<slug>/` with timestamps

---

## Environment & Secrets

`.gitignore` must always include:
```
.env
*.db
output/
logs/
__pycache__/
*.pyc
```

Always provide `.env.example` documenting every variable:
```
ANTHROPIC_API_KEY=
SMTP_HOST=
SMTP_PORT=587
NOTIFY_EMAIL=
```

---

## Key Principles

1. **Clean separation**: Data → Orchestration → UI. No layer skips another.
2. **Config-driven**: Behaviour controlled by `Config` dataclass; no magic values in logic code.
3. **Cheap before expensive**: Free/local operations run before any API call.
4. **Human in the loop**: Nothing is submitted or sent without explicit user approval.
5. **Audit trail**: Every status transition recorded in an events table.
6. **Graceful degradation**: Missing API keys disable features; no crashes.
7. **UI flexibility**: Use Tkinter for desktop tools, Flask/FastAPI + HTML for web apps — choose what fits the project, apply the same layering rules either way.
8. **Testable by design**: Dependency injection via Config; DB path injectable via constructor.
9. **No hidden costs**: Show users what will cost money before triggering it.
10. **Rich output**: All CLI output uses Rich for readable, colour-coded terminal display.

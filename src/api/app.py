"""
api/app.py
==========
FastAPI application — serves the Bootstrap/ag-Grid web UI and all REST + WebSocket
endpoints. Business logic stays in the existing modules (tracker, cv_tailor, etc.).

Run:
    cd src && uvicorn api.app:app --reload --port 5000
"""
import asyncio
import os
import sys
from collections import deque
from pathlib import Path
from typing import Optional

# ── path: make src/ importable ────────────────────────────────────────────────
_SRC = Path(__file__).parent.parent
sys.path.insert(0, str(_SRC))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.middleware.cors import CORSMiddleware

from config import Config, USER_PREFS_PATH
from tracker import ApplicationTracker
from ui.constants import _LogCapture

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Job Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
templates = Jinja2Templates(directory=str(_SRC / "templates"))

# ── Shared state ──────────────────────────────────────────────────────────────
_config:  Optional[Config]               = None
_tracker: Optional[ApplicationTracker]  = None
_log_lines: deque                        = deque(maxlen=500)
_ws_queues: list                         = []   # one asyncio.Queue per WS client
_loop:    Optional[asyncio.AbstractEventLoop] = None
_scan_running  = False
_task_running  = False


@app.on_event("startup")
async def _startup():
    global _config, _tracker, _loop
    _loop    = asyncio.get_event_loop()
    _config  = Config()
    _tracker = ApplicationTracker(_config.db_path)


# ── Log helpers ───────────────────────────────────────────────────────────────

def _append_log(line: str):
    """Thread-safe: add a log line and push to all WebSocket clients."""
    entry = {"text": line}
    _log_lines.append(entry)
    if _loop:
        for q in list(_ws_queues):
            _loop.call_soon_threadsafe(q.put_nowait, entry)


# ── WebSocket: live log stream ────────────────────────────────────────────────

@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue()
    _ws_queues.append(q)
    try:
        for entry in list(_log_lines)[-200:]:       # replay recent history
            await websocket.send_json(entry)
        while True:
            entry = await q.get()
            await websocket.send_json(entry)
    except WebSocketDisconnect:
        pass
    finally:
        if q in _ws_queues:
            _ws_queues.remove(q)


# ── Serve UI ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Config ────────────────────────────────────────────────────────────────────

def _config_to_dict(c: Config) -> dict:
    return {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(c).items()}


@app.get("/api/config")
async def get_config():
    if not _config:
        raise HTTPException(503, "Not ready")
    return _config_to_dict(_config)


@app.post("/api/config")
async def save_config(data: dict):
    """Write changed fields to user.env and reload config."""
    global _config

    # Map dataclass field → env var name (only env-backed scalar fields)
    _ENV = {
        "candidate_name":          "CANDIDATE_NAME",
        "candidate_email":         "CANDIDATE_EMAIL",
        "candidate_phone":         "CANDIDATE_PHONE",
        "candidate_linkedin":      "CANDIDATE_LINKEDIN",
        "candidate_location":      "CANDIDATE_LOCATION",
        "candidate_address":       "CANDIDATE_ADDRESS",
        "candidate_address2":      "CANDIDATE_ADDRESS2",
        "reed_email":              "REED_LOGIN_EMAIL",
        "reed_password":           "REED_LOGIN_PASSWORD",
        "linkedin_apply_email":    "LINKEDIN_APPLY_EMAIL",
        "linkedin_apply_password": "LINKEDIN_APPLY_PASSWORD",
        "notify_email":            "NOTIFY_EMAIL",
        "smtp_from":               "SMTP_FROM",
        "smtp_host":               "SMTP_HOST",
        "smtp_port":               "SMTP_PORT",
        "smtp_user":               "SMTP_USER",
        "smtp_password":           "SMTP_PASSWORD",
        "anthropic_api_key":       "ANTHROPIC_API_KEY",
        "claude_model":            "CLAUDE_MODEL",
        "reed_api_key":            "REED_API_KEY",
        "adzuna_app_id":           "ADZUNA_APP_ID",
        "adzuna_app_key":          "ADZUNA_APP_KEY",
        "output_dir":              "OUTPUT_DIR",
    }
    # Scalar fields stored as plain strings (not env-backed but persisted in user.env)
    _PLAIN = {
        "min_salary_gbp", "max_salary_gbp", "min_match_score", "max_job_age_days",
        "search_radius_miles", "max_tailored_per_scan", "include_remote", "ats_mode",
        "scan_civil_service", "scan_guardian", "scan_linkedin",
        "scan_w4mpjobs", "scan_charityjob", "search_location", "show_filtered_in_ui",
        "search_keywords", "seniority_filter_titles", "irrelevant_filter_titles",
        "seniority_filter_experience", "exclude_locations",
    }

    # Read existing user.env
    existing: dict[str, str] = {}
    if USER_PREFS_PATH.exists():
        for ln in USER_PREFS_PATH.read_text().splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, _, v = ln.partition("=")
                existing[k.strip()] = v.strip()

    for field, value in data.items():
        if field in _ENV:
            existing[_ENV[field]] = str(value)
        elif field in _PLAIN:
            key = field.upper()
            existing[key] = ("\n".join(value) if isinstance(value, list) else str(value))

    USER_PREFS_PATH.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n")
    for k, v in existing.items():
        os.environ[k] = v
    _config = Config()
    return {"status": "saved"}


# ── Jobs ──────────────────────────────────────────────────────────────────────

def _safe(j: dict) -> dict:
    return {k: (str(v) if isinstance(v, Path) else v) for k, v in j.items()}


@app.get("/api/jobs")
async def get_jobs(
    status: str = None,
    search: str = None,
    show_filtered: bool = False,
):
    if not _tracker:
        raise HTTPException(503, "Not ready")
    jobs = _tracker.get_all_jobs()

    if status:
        keep = set(status.split(","))
        jobs = [j for j in jobs if j["status"] in keep]
    elif not show_filtered:
        jobs = [j for j in jobs if j["status"] != "filtered"]

    if search:
        q = search.lower()
        jobs = [j for j in jobs if
                q in (j.get("title")       or "").lower() or
                q in (j.get("employer")    or "").lower() or
                q in (j.get("location")    or "").lower() or
                q in (j.get("description") or "").lower()]

    return [_safe(j) for j in jobs]


@app.get("/api/jobs/stats")
async def get_stats():
    if not _tracker:
        raise HTTPException(503, "Not ready")
    jobs = _tracker.get_all_jobs()
    counts: dict[str, int] = {}
    for j in jobs:
        counts[j["status"]] = counts.get(j["status"], 0) + 1
    return {"total": len(jobs), "by_status": counts,
            "scan_running": _scan_running, "task_running": _task_running}


@app.get("/api/jobs/pending-review")
async def get_pending_review():
    if not _tracker:
        raise HTTPException(503, "Not ready")
    jobs = [j for j in _tracker.get_all_jobs()
            if j["status"] in ("tailored", "pending_review")]
    return [_safe(j) for j in jobs]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: int):
    if not _tracker:
        raise HTTPException(503, "Not ready")
    job = _tracker.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _safe(job)


@app.patch("/api/jobs/{job_id}")
async def update_job(job_id: int, data: dict):
    if not _tracker:
        raise HTTPException(503, "Not ready")
    if not _tracker.get_job(job_id):
        raise HTTPException(404, "Job not found")
    if "status" in data:
        _tracker.update_status(job_id, data["status"],
                               data.get("detail", "Updated via web UI"))
    if "notes" in data:
        with _tracker._connect() as conn:
            conn.execute(
                "UPDATE jobs SET notes=?, date_updated=datetime('now') WHERE id=?",
                (data["notes"], job_id),
            )
    return _safe(_tracker.get_job(job_id))


# ── Task status ───────────────────────────────────────────────────────────────

@app.get("/api/task-status")
async def task_status():
    return {"scan_running": _scan_running, "task_running": _task_running}


@app.get("/api/logs")
async def get_logs():
    return list(_log_lines)


# ── Background task helpers ───────────────────────────────────────────────────

def _run_in_capture(fn, *args):
    """Run fn(*args) with stdout captured to the log stream."""
    capture   = _LogCapture(sys.__stdout__, on_line=_append_log)
    old_stdout = sys.stdout
    sys.stdout = capture
    try:
        fn(*args)
    finally:
        sys.stdout = old_stdout


# ── Scan ──────────────────────────────────────────────────────────────────────

@app.post("/api/scan")
async def start_scan():
    global _scan_running
    if _scan_running:
        raise HTTPException(409, "Scan already running")
    _scan_running = True

    def _do():
        global _scan_running
        try:
            _append_log("── Scan started ──")
            from main import run_scan
            _run_in_capture(run_scan, _config, _tracker)
            _append_log("── Scan complete ──")
        except Exception as e:
            _append_log(f"ERROR: {e}")
        finally:
            _scan_running = False

    asyncio.create_task(asyncio.to_thread(_do))
    return {"status": "started"}


# ── Score ─────────────────────────────────────────────────────────────────────

@app.post("/api/score")
async def score_jobs(data: dict):
    global _task_running
    if _task_running:
        raise HTTPException(409, "A task is already running")
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, "No job IDs provided")
    for jid in ids:
        _tracker.update_status(jid, "score_me", "Selected for scoring via web UI")
    _task_running = True

    def _do():
        global _task_running
        try:
            _append_log(f"── Scoring {len(ids)} job(s) ──")
            from main import run_score_selected
            _run_in_capture(run_score_selected, _config, _tracker)
            _append_log("── Scoring complete ──")
        except Exception as e:
            _append_log(f"ERROR: {e}")
        finally:
            _task_running = False

    asyncio.create_task(asyncio.to_thread(_do))
    return {"status": "started", "count": len(ids)}


# ── Tailor ────────────────────────────────────────────────────────────────────

@app.post("/api/tailor")
async def tailor_jobs(data: dict):
    global _task_running
    if _task_running:
        raise HTTPException(409, "A task is already running")
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, "No job IDs provided")
    for jid in ids:
        _tracker.update_status(jid, "tailoring", "Selected for tailoring via web UI")
    _task_running = True

    def _do():
        global _task_running
        try:
            _append_log(f"── Tailoring {len(ids)} application(s) ──")
            from main import run_tailor_approved
            _run_in_capture(run_tailor_approved, _config, _tracker)
            _append_log("── Tailoring complete ──")
        except Exception as e:
            _append_log(f"ERROR: {e}")
        finally:
            _task_running = False

    asyncio.create_task(asyncio.to_thread(_do))
    return {"status": "started", "count": len(ids)}


# ── Add job by URL ────────────────────────────────────────────────────────────

@app.post("/api/jobs/add-url")
async def add_job_by_url(data: dict):
    global _task_running
    url = (data.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "URL required")
    if _tracker.job_exists(url):
        raise HTTPException(409, "Job already tracked")

    _task_running = True
    result: dict = {}

    def _do():
        global _task_running
        try:
            from job_scanner import JobScanner
            scanner = JobScanner(_config)
            desc = scanner.fetch_job_description(url) or ""
            job = {
                "title":       data.get("title") or "Manual entry",
                "employer":    data.get("employer") or "",
                "url":         url,
                "description": desc,
                "source":      "manual",
                "location":    data.get("location") or "",
                "salary":      data.get("salary") or "",
            }
            jid = _tracker.add_job(job)
            result["job_id"] = jid
            if data.get("tailor"):
                _tracker.update_status(jid, "tailoring", "Auto-tailor on add")
                from main import run_tailor_approved
                _run_in_capture(run_tailor_approved, _config, _tracker)
        except Exception as e:
            _append_log(f"ERROR adding job: {e}")
            result["error"] = str(e)
        finally:
            _task_running = False

    await asyncio.to_thread(_do)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return {"status": "added", "job_id": result.get("job_id")}


# ── Export (returns JSON — SheetJS handles XLSX client-side) ──────────────────

@app.get("/api/jobs/export")
async def export_jobs(status: str = None, search: str = None):
    if not _tracker:
        raise HTTPException(503, "Not ready")
    jobs = _tracker.get_all_jobs()
    if status:
        keep = set(status.split(","))
        jobs = [j for j in jobs if j["status"] in keep]
    if search:
        q = search.lower()
        jobs = [j for j in jobs if
                q in (j.get("title") or "").lower() or
                q in (j.get("employer") or "").lower()]
    return [_safe(j) for j in jobs]

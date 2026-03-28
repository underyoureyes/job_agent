"""
tracker.py - SQLite Application Tracker
========================================
Stores all jobs found, their tailored documents, and application status.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

# Application status flow:
# discovered → [user reviews title] → score_me → scored → [user reviews score]
#           → tailoring → tailored → approved → submitted
STATUS_FLOW = [
    "discovered",    # Found by scanner, passed free filters — awaiting title review
    "score_me",      # User selected this in UI — queue for scoring (~$0.01)
    "scored",        # AI scored — user reviews score before committing to tailor
    "filtered",      # Auto-filtered (too senior / irrelevant / wrong location / low score)
    "dismissed",     # Manually hidden by user in Screen Jobs — won't reappear
    "tailoring",     # User approved — queue for CV + cover letter (~$0.05)
    "tailored",      # Docs ready — awaiting review
    "pending_review",# In the review queue
    "approved",      # Approved — ready to submit
    "skipped",       # Decided not to apply
    "submitted",     # Application sent
    "interview",     # Got an interview!
    "rejected",      # Rejected
    "offer",         # Offer received
]

STATUS_COLOURS = {
    "discovered":     "cyan",
    "score_me":       "yellow",
    "scored":         "green",
    "filtered":       "dim",
    "dismissed":      "dim",
    "tailoring":      "yellow",
    "tailored":       "cyan",
    "pending_review": "yellow",
    "approved":       "green",
    "skipped":        "red",
    "submitted":      "bold green",
    "interview":      "bold magenta",
    "rejected":       "red",
    "offer":          "bold yellow",
}


class ApplicationTracker:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    employer TEXT,
                    location TEXT,
                    salary TEXT,
                    url TEXT UNIQUE NOT NULL,
                    description TEXT,
                    source TEXT,
                    date_found TEXT NOT NULL,
                    date_closes TEXT,
                    status TEXT DEFAULT 'discovered',
                    match_score INTEGER,
                    match_reason TEXT,
                    tailored_cv_path TEXT,
                    cover_letter_path TEXT,
                    notes TEXT,
                    date_submitted TEXT,
                    date_updated TEXT,
                    raw_data TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER,
                    event TEXT,
                    detail TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (job_id) REFERENCES jobs(id)
                )
            """)

    def add_job(self, job: Dict[str, Any]) -> int:
        """Insert a newly discovered job, or reset a previously filtered one.
        Returns the job ID."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            # If it was previously filtered, reset it so filters re-apply
            existing = conn.execute(
                "SELECT id, status FROM jobs WHERE url = ?", (job["url"],)
            ).fetchone()
            if existing and existing[1] == "filtered":
                conn.execute(
                    "UPDATE jobs SET status = 'discovered', date_updated = ? WHERE id = ?",
                    (now, existing[0])
                )
                return existing[0]

            cursor = conn.execute("""
                INSERT INTO jobs (
                    title, employer, location, salary, url, description,
                    source, date_found, date_closes, status, match_score,
                    match_reason, raw_data, date_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'discovered', ?, ?, ?, ?)
            """, (
                job.get("title"),
                job.get("employer"),
                job.get("location"),
                job.get("salary"),
                job["url"],
                job.get("description"),
                job.get("source"),
                now,
                job.get("date_closes"),
                job.get("match_score"),
                job.get("match_reason"),
                json.dumps(job),
                now,
            ))
            job_id = cursor.lastrowid
            self._log_event(conn, job_id, "discovered", f"Found on {job.get('source', 'unknown')}")
            return job_id

    def get_job(self, job_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def job_exists(self, url: str) -> bool:
        """Returns True only for jobs that have progressed past filtering.
        Jobs stuck at 'filtered' are re-evaluated on each scan so that
        filter changes take effect on subsequent runs."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM jobs WHERE url = ?", (url,)
            ).fetchone()
            if row is None:
                return False
            return row[0] != "filtered"

    def update_status(self, job_id: int, status: str, detail: str = ""):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, date_updated = ? WHERE id = ?",
                (status, now, job_id)
            )
            self._log_event(conn, job_id, f"status → {status}", detail)

    def update_documents(self, job_id: int, cv_path: str, letter_path: str):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute("""
                UPDATE jobs SET tailored_cv_path = ?, cover_letter_path = ?,
                status = 'tailored', date_updated = ? WHERE id = ?
            """, (cv_path, letter_path, now, job_id))
            self._log_event(conn, job_id, "tailored", "CV and cover letter generated")

    def add_note(self, job_id: int, note: str):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET notes = ?, date_updated = ? WHERE id = ?",
                (note, now, job_id)
            )
            self._log_event(conn, job_id, "note", note)

    def get_jobs_by_status(self, status: str) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY date_found DESC",
                (status,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_jobs(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY date_found DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_pending_review(self) -> List[Dict]:
        """Returns jobs that are tailored but not yet reviewed."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM jobs
                WHERE status IN ('tailored', 'pending_review')
                ORDER BY match_score DESC, date_found DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_discovered_jobs(self) -> List[Dict]:
        """Returns jobs awaiting title review — status = discovered."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM jobs
                WHERE status = 'discovered'
                ORDER BY date_found DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_scored_jobs(self) -> List[Dict]:
        """Returns jobs scored but not yet tailored — awaiting human screening."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM jobs
                WHERE status = 'scored'
                ORDER BY match_score DESC, date_found DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_jobs_for_screening(self) -> List[Dict]:
        """Returns all jobs a human should screen — scored but not yet actioned."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM jobs
                WHERE status IN ('scored', 'discovered')
                AND (match_score IS NULL OR match_score >= 40)
                ORDER BY match_score DESC, date_found DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def _log_event(self, conn, job_id: int, event: str, detail: str = ""):
        conn.execute("""
            INSERT INTO events (job_id, event, detail, timestamp)
            VALUES (?, ?, ?, ?)
        """, (job_id, event, detail, datetime.now().isoformat()))

    def get_events(self, job_id: int) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE job_id = ? ORDER BY timestamp",
                (job_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def print_dashboard(self):
        """Print a rich summary dashboard."""
        jobs = self.get_all_jobs()
        if not jobs:
            console.print("[yellow]No jobs tracked yet. Run [bold]python main.py scan[/bold] to start.[/yellow]")
            return

        # Summary counts
        counts = {}
        for job in jobs:
            s = job["status"]
            counts[s] = counts.get(s, 0) + 1

        console.print("\n[bold cyan]═══ Application Dashboard ═══[/bold cyan]\n")

        summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        summary.add_column(style="dim")
        summary.add_column(justify="right")
        for status in STATUS_FLOW:
            if status in counts:
                colour = STATUS_COLOURS.get(status, "white")
                summary.add_row(
                    f"[{colour}]{status.replace('_', ' ').title()}[/{colour}]",
                    f"[bold]{counts[status]}[/bold]"
                )
        console.print(summary)

        # Recent jobs table
        table = Table(
            title="Recent Applications",
            box=box.ROUNDED,
            show_lines=False,
            header_style="bold cyan",
        )
        table.add_column("ID", style="dim", width=4)
        table.add_column("Role", max_width=35)
        table.add_column("Employer", max_width=25)
        table.add_column("Match", justify="center", width=6)
        table.add_column("Status", width=15)
        table.add_column("Found", width=11)

        for job in jobs[:20]:
            status = job["status"]
            colour = STATUS_COLOURS.get(status, "white")
            score = f"{job['match_score']}%" if job["match_score"] else "—"
            date = job["date_found"][:10] if job["date_found"] else "—"
            table.add_row(
                str(job["id"]),
                job["title"] or "—",
                job["employer"] or "—",
                score,
                f"[{colour}]{status.replace('_', ' ')}[/{colour}]",
                date,
            )

        console.print(table)
        if len(jobs) > 20:
            console.print(f"[dim]... and {len(jobs) - 20} more.[/dim]")

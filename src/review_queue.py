"""
review_queue.py - Interactive Application Review Queue
=======================================================
Presents each tailored application for human review before approval.
Your son (or you) can approve, skip, or add notes to each one.

Run: python main.py review
"""

import subprocess
import platform
from pathlib import Path
from typing import Dict
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box
from tracker import ApplicationTracker, STATUS_COLOURS
from config import Config

console = Console()


class ReviewQueue:
    def __init__(self, tracker: ApplicationTracker, config: Config):
        self.tracker = tracker
        self.config = config

    def run(self):
        pending = self.tracker.get_pending_review()

        if not pending:
            console.print("\n[green]✓ No applications pending review.[/green]")
            console.print("[dim]Run [bold]python main.py scan[/bold] to find new jobs.[/dim]")
            return

        console.print(f"\n[bold cyan]📋 Review Queue[/bold cyan] — {len(pending)} application(s) to review\n")
        console.print("[dim]For each job, review the CV and cover letter, then approve or skip.[/dim]\n")

        approved = 0
        skipped = 0

        for i, job in enumerate(pending, 1):
            console.print(f"[bold]── Application {i} of {len(pending)} ──[/bold]")
            action = self._review_one(job)
            if action == "approved":
                approved += 1
            elif action == "skipped":
                skipped += 1
            elif action == "quit":
                break
            console.print()

        console.print(f"\n[bold]Review complete:[/bold] {approved} approved, {skipped} skipped.")
        if approved:
            console.print(
                f"[green]{approved} application(s) marked as approved. "
                "Send them when ready and update status via [bold]python main.py status[/bold].[/green]"
            )

    def _review_one(self, job: Dict) -> str:
        """Display one job and prompt for action. Returns 'approved', 'skipped', or 'quit'."""

        # Job summary panel
        score = job.get("match_score")
        score_str = f"{score}%" if score else "N/A"
        score_colour = "green" if score and score >= 70 else "yellow" if score and score >= 50 else "red"

        details = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        details.add_column(style="dim", width=18)
        details.add_column()
        details.add_row("Role", f"[bold]{job.get('title', 'N/A')}[/bold]")
        details.add_row("Employer", job.get("employer") or "N/A")
        details.add_row("Location", job.get("location") or "N/A")
        details.add_row("Salary", job.get("salary") or "N/A")
        details.add_row("Match Score", f"[{score_colour}]{score_str}[/{score_colour}]")
        details.add_row("Match Reason", job.get("match_reason") or "N/A")
        details.add_row("Source", job.get("source") or "N/A")
        details.add_row("URL", f"[link={job.get('url')}]{job.get('url', 'N/A')}[/link]")

        closes = job.get("date_closes")
        if closes:
            details.add_row("Closes", f"[yellow]{closes}[/yellow]")

        console.print(Panel(details, title=f"Job #{job['id']}", border_style="cyan"))

        # Show file paths
        cv_path = job.get("tailored_cv_path")
        letter_path = job.get("cover_letter_path")

        if cv_path:
            console.print(f"  [cyan]CV:[/cyan]           {cv_path}")
        if letter_path:
            console.print(f"  [cyan]Cover Letter:[/cyan] {letter_path}")

        # Action menu
        console.print("\n  [bold]Actions:[/bold]")
        console.print("  [green]a[/green] Approve  [red]s[/red] Skip  [blue]o[/blue] Open files  [yellow]n[/yellow] Add note  [dim]q[/dim] Quit review")

        while True:
            choice = Prompt.ask("  Choice", choices=["a", "s", "o", "n", "q"], default="o")

            if choice == "o":
                self._open_files(cv_path, letter_path)

            elif choice == "n":
                note = Prompt.ask("  Add note")
                if note:
                    self.tracker.add_note(job["id"], note)
                    console.print("  [green]Note saved.[/green]")

            elif choice == "a":
                self.tracker.update_status(job["id"], "approved", "Approved via review queue")
                console.print(f"  [green]✓ Approved! Application #{job['id']} is ready to submit.[/green]")
                return "approved"

            elif choice == "s":
                reason = Prompt.ask("  Reason for skipping (optional)", default="")
                self.tracker.update_status(job["id"], "skipped", reason or "Skipped via review queue")
                console.print(f"  [yellow]Skipped.[/yellow]")
                return "skipped"

            elif choice == "q":
                if Confirm.ask("  Quit review queue? (remaining jobs will stay pending)"):
                    return "quit"

    def _open_files(self, cv_path: str, letter_path: str):
        """Open files in the default system application."""
        system = platform.system()
        for path_str in [cv_path, letter_path]:
            if not path_str:
                continue
            path = Path(path_str)
            if not path.exists():
                console.print(f"  [red]File not found: {path}[/red]")
                continue
            try:
                if system == "Darwin":
                    subprocess.run(["open", str(path)], check=True)
                elif system == "Linux":
                    subprocess.run(["xdg-open", str(path)], check=True)
                elif system == "Windows":
                    subprocess.run(["cmd", "/c", "start", "", str(path)], check=True)
            except Exception as e:
                console.print(f"  [yellow]Could not open {path.name}: {e}[/yellow]")
                console.print(f"  [dim]Path: {path}[/dim]")

"""
Job Application Agent - Main Orchestrator
==========================================
Flow:
  1. scan          — find jobs, apply free filters, save as 'discovered'
                     NO scoring happens here — zero API cost
  2. [UI Screen]   — user browses all titles, ticks what interests them
  3. score_selected — score only the ticked jobs (~$0.01 each)
  4. [UI Screen]   — user reviews scores, ticks which to tailor
  5. tailor_approved — tailor CV + cover letter (~$0.05 each)
  6. [UI Review]   — user reads docs, approves or skips
  7. Submit manually, update status

Usage:
    python main.py scan              # Scan + filter, no scoring
    python main.py score_selected    # Score jobs marked 'score_me'
    python main.py tailor_approved   # Tailor jobs marked 'tailoring'
    python main.py tailor <id>       # Tailor one specific job
    python main.py review            # CLI review queue
    python main.py status            # Dashboard
"""

import argparse
from job_scanner import JobScanner
from cv_tailor import CVTailor
from tracker import ApplicationTracker
from review_queue import ReviewQueue
from config import Config
from rich.console import Console
from rich.panel import Panel

console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="Job Application Agent for Public Policy roles"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("scan",             help="Scan job boards and apply free filters")
    subparsers.add_parser("score_selected",   help="Score jobs selected in screening UI")
    subparsers.add_parser("tailor_approved",  help="Tailor CVs for jobs approved in screening")
    subparsers.add_parser("review",           help="Review tailored applications")
    subparsers.add_parser("status",           help="Show application tracker dashboard")

    tailor_parser = subparsers.add_parser("tailor", help="Tailor CV for a specific job ID")
    tailor_parser.add_argument("job_id", type=int)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    config  = Config()
    tracker = ApplicationTracker(config.db_path)

    console.print(Panel.fit(
        f"[bold cyan]Job Application Agent[/bold cyan]\n"
        f"Candidate: [yellow]{config.candidate_name}[/yellow] | "
        f"Field: [yellow]{config.target_field}[/yellow]",
        border_style="cyan"
    ))

    if args.command == "scan":
        run_scan(config, tracker)
    elif args.command == "score_selected":
        run_score_selected(config, tracker)
    elif args.command == "tailor_approved":
        run_tailor_approved(config, tracker)
    elif args.command == "review":
        ReviewQueue(tracker, config).run()
    elif args.command == "status":
        tracker.print_dashboard()
    elif args.command == "tailor":
        job = tracker.get_job(args.job_id)
        if not job:
            console.print(f"[red]Job ID {args.job_id} not found.[/red]")
            return
        CVTailor(config).process_job(job, tracker)


def run_scan(config: Config, tracker: ApplicationTracker):
    """
    Phase 1 — Scan and filter only. Completely FREE.
    No API calls made. Jobs saved as 'discovered'.
    User reviews titles in the UI before any money is spent.
    """
    scanner = JobScanner(config)

    console.print("\n[bold]Scanning job boards...[/bold]")
    try:
        jobs = scanner.scan_all()
    except Exception as e:
        console.print(f"[red]Scanner failed: {e}[/red]")
        return

    console.print(f"\n[bold]{len(jobs)} jobs found.[/bold]")

    new_count = filtered_count = saved_count = skipped_count = 0

    console.print("\n[bold]Applying filters...[/bold]")

    for job in jobs:
        # Already tracked — skip
        if tracker.job_exists(job["url"]):
            skipped_count += 1
            continue

        new_count += 1

        # ── Seniority filter ──────────────────────────────────────────────
        if _is_too_senior(job, config):
            job_id = tracker.add_job(job)
            tracker.update_status(job_id, "filtered", "Auto-filtered: too senior")
            console.print(f"  [dim]⊘ Senior: {job.get('title','')} @ {job.get('employer','')}[/dim]")
            filtered_count += 1
            continue

        # ── Irrelevant title filter ───────────────────────────────────────
        if _is_irrelevant(job, config):
            job_id = tracker.add_job(job)
            tracker.update_status(job_id, "filtered", "Auto-filtered: irrelevant title")
            console.print(f"  [dim]⊘ Irrelevant: {job.get('title','')}[/dim]")
            filtered_count += 1
            continue

        # ── Relevance allowlist filter ─────────────────────────────────────
        if _is_not_relevant(job, config):
            job_id = tracker.add_job(job)
            tracker.update_status(job_id, "filtered", "Auto-filtered: not relevant to field")
            console.print(f"  [dim]⊘ Off-topic: {job.get('title', '')} @ {job.get('employer', '')}[/dim]")
            filtered_count += 1
            continue

        # ── Location filter ───────────────────────────────────────────────
        if _is_wrong_location(job, config):
            job_id = tracker.add_job(job)
            tracker.update_status(job_id, "filtered", "Auto-filtered: outside location")
            console.print(f"  [dim]⊘ Location: {job.get('title','')} [{job.get('location','')}][/dim]")
            filtered_count += 1
            continue

        # ── Salary range filter ───────────────────────────────────────────
        if _is_out_of_salary_range(job, config):
            job_id = tracker.add_job(job)
            tracker.update_status(job_id, "filtered", "Auto-filtered: salary out of range")
            console.print(f"  [dim]⊘ Salary: {job.get('title','')} [{job.get('salary','')}][/dim]")
            filtered_count += 1
            continue

        # ── Save as discovered — awaiting human review ────────────────────
        job_id = tracker.add_job(job)
        console.print(
            f"  [green]✓[/green] {job.get('title','')[:55]} @ {job.get('employer','')[:30]}"
        )
        saved_count += 1

    console.print(
        f"\n[bold]Scan complete:[/bold] "
        f"[green]{saved_count} jobs ready to review[/green] | "
        f"[dim]{filtered_count} filtered | {skipped_count} already known[/dim]"
    )

    if saved_count:
        console.print(
            "\n[yellow]Open the app → [bold]Screen jobs[/bold] to review titles "
            "and select which to score. No credits spent yet.[/yellow]"
        )


def run_score_selected(config: Config, tracker: ApplicationTracker):
    """
    Phase 3 — Score only the jobs the user selected in the UI.
    Called by the UI after ticking jobs and clicking 'Score selected'.
    Cost: ~$0.01 per job.
    """
    tailor = CVTailor(config)
    jobs   = tracker.get_jobs_by_status("score_me")

    if not jobs:
        console.print("[yellow]No jobs queued for scoring. Select some in the Screen jobs panel.[/yellow]")
        return

    console.print(f"\n[bold]Scoring {len(jobs)} selected job(s)...[/bold]")

    for job in jobs:
        title    = job.get("title", "")
        employer = job.get("employer", "")
        console.print(f"  [cyan]→[/cyan] {title} @ {employer}", end="")

        try:
            score, reason = tailor.score_only(job, tracker)
            if score < config.min_match_score:
                tracker.update_status(job["id"], "filtered", f"Low score ({score}%)")
                console.print(f" [dim]→ {score}% — filtered[/dim]")
            else:
                tracker.update_status(job["id"], "scored", f"Score: {score}% — {reason}")
                console.print(f" [green]→ {score}%[/green]")
        except Exception as e:
            console.print(f" [red]failed: {e}[/red]")
            tracker.update_status(job["id"], "discovered", f"Scoring failed: {e}")
            # Re-raise billing/auth errors immediately — no point trying remaining jobs
            _msg = str(e).lower()
            if any(k in _msg for k in ("credit", "billing", "insufficient", "balance",
                                        "payment", "quota", "401", "402", "authentication",
                                        "api key", "usage limit")):
                raise

    console.print(
        "\n[yellow]Go back to [bold]Screen jobs[/bold] to see scores "
        "and select which to tailor.[/yellow]"
    )


def run_tailor_approved(config: Config, tracker: ApplicationTracker):
    """
    Phase 5 — Tailor CVs for jobs the user approved after seeing scores.
    Cost: ~$0.05 per job.
    """
    tailor = CVTailor(config)
    jobs   = tracker.get_jobs_by_status("tailoring")

    if not jobs:
        console.print("[yellow]No jobs queued for tailoring.[/yellow]")
        return

    console.print(f"\n[bold]Tailoring {len(jobs)} application(s)...[/bold]")
    for job in jobs:
        console.print(f"\n  [cyan]→[/cyan] {job['title']} @ {job.get('employer','')}")
        tailor.process_job(job, tracker)

    console.print("\n[green]Done. Go to Review queue to approve applications.[/green]")


# ── Free filters ──────────────────────────────────────────────────────────────

def _matches_pattern(text: str, pattern: str) -> bool:
    """Word-boundary-aware match: pattern must appear as a whole word (or phrase) in text."""
    import re
    p = re.escape(pattern.lower().strip())
    return bool(re.search(rf"\b{p}\b", text))


def _is_too_senior(job: dict, config: Config) -> bool:
    """True if title or description signals this is too senior."""
    title = (job.get("title") or "").lower()
    desc  = (job.get("description") or "").lower()

    for pattern in config.seniority_filter_titles:
        if _matches_pattern(title, pattern):
            return True

    for pattern in config.seniority_filter_experience:
        if pattern.lower() in desc:
            return True

    return False


def _is_irrelevant(job: dict, config: Config) -> bool:
    """True if the job title contains clearly irrelevant keywords."""
    title = (job.get("title") or "").lower()
    for pattern in config.irrelevant_filter_titles:
        if _matches_pattern(title, pattern):
            return True
    return False

def _is_not_relevant(job: dict, config: Config) -> bool:
    """True if the job title contains none of the positive relevance keywords."""
    title = (job.get("title") or "").lower()
    positive_keywords = [kw.lower() for kw in config.search_keywords]
    # Also include a core allowlist of role-type words
    allowlist = [
        "policy", "research", "analyst", "advisor", "adviser", "affairs",
        "strategy", "governance", "regulatory", "regulation", "parliament",
        "parliamentary", "constituency", "government", "public sector",
        "stakeholder", "campaigns", "campaign", "advocacy", "communications",
        "intelligence", "programme", "program", "engagement", "insight",
        "scrutiny", "legislation", "consultations", "external affairs",
        "fundraising", "editorial", "westminster",
    ]
    all_terms = positive_keywords + allowlist
    return not any(term in title for term in all_terms)



def _is_wrong_location(job: dict, config: Config) -> bool:
    """True if the job location is outside the target area."""
    location = (job.get("location") or "").lower()
    for place in config.exclude_locations:
        if place.lower() in location:
            return True
    return False


def _is_out_of_salary_range(job: dict, config: Config) -> bool:
    """True if salary is above max_salary_gbp (when set) or below min_salary_gbp."""
    import re
    salary_str = (job.get("salary") or "").replace(",", "").replace("£", "")
    numbers = re.findall(r"\d+", salary_str)
    if not numbers:
        return False  # No salary info — let it through
    amounts = [int(n) for n in numbers if int(n) > 1000]  # ignore pence
    if not amounts:
        return False
    mid = sum(amounts) / len(amounts)
    if config.min_salary_gbp and mid < config.min_salary_gbp:
        return True
    if getattr(config, "max_salary_gbp", 0) and mid > config.max_salary_gbp:
        return True
    return False


if __name__ == "__main__":
    main()

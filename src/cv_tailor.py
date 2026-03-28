"""
cv_tailor.py - AI CV & Cover Letter Tailoring Agent
=====================================================
Uses Claude to:
  1. Score the job match (0-100%) with a reason
  2. Rewrite the CV to emphasise relevant experience
  3. Write a tailored, compelling cover letter

Outputs Markdown files saved to the output/ directory.
Nothing is sent anywhere — files are queued for human review.
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import anthropic
from rich.console import Console
from config import Config
from document_processor import StyleFingerprint
from doc_generator import DocGenerator

console = Console()


SCORE_PROMPT = """You are a job application expert specialising in public policy careers.

Given the following job posting and candidate CV, return a JSON object with:
- "score": integer 0-100 representing how well the candidate matches this role
- "reason": 1-2 sentence explanation of the match quality
- "key_requirements": list of 3-5 key requirements from the job
- "candidate_strengths": list of 3-5 matching strengths from the CV
- "gaps": list of any significant gaps (max 3)

Return ONLY valid JSON, no markdown, no preamble.

JOB POSTING:
{job_text}

CANDIDATE CV:
{cv_text}
"""

TAILOR_CV_PROMPT = """You are an expert CV writer specialising in public policy and government careers.

Rewrite the candidate's CV to be perfectly tailored for this specific role.

Core rules:
- Keep all facts true — do not invent experience
- Reorder and rephrase bullet points to lead with the most relevant achievements
- Use keywords from the job description naturally
- Keep the same overall structure but optimise content for this role
- Write in UK English
- Target length: 1–2 pages
- Output in clean Markdown with clear section headers

CRITICAL — write so this cannot be detected as AI-generated:
- Vary sentence and bullet point length — mix short punchy ones with longer ones, never uniform
- Use specific concrete details, numbers and named organisations — never vague generalities
- Avoid buzzwords entirely: no "leverage", "synergise", "dynamic", "passionate", "results-driven", "spearheaded", "utilise", "impactful", "proactive", "key", "robust"
- No filler transitions: never use "Furthermore", "Moreover", "Additionally", "In conclusion", "It is worth noting"
- Avoid perfect parallel structure — real CVs have slight variation in how bullets are phrased
- Use natural UK phrasing and occasional mild informality where it fits (e.g. "worked closely with" not "collaborated cross-functionally with")
- Do not start every bullet the same way — vary the opening word
- No em-dashes (—) in bullet points; use plain punctuation
- Avoid over-qualification ("highly", "extremely", "truly") — let the facts speak

JOB TITLE: {job_title}
EMPLOYER: {employer}

JOB DESCRIPTION:
{job_description}

ORIGINAL CV:
{cv_text}

Write the tailored CV now:
"""

COVER_LETTER_PROMPT = """You are an expert cover letter writer for public policy and government roles.

Write a compelling, personalised cover letter for this application.

FORMAT — output exactly this structure in Markdown.
Lines starting with >>> are positioned on the right side of the page (sender/candidate details).
Lines without >>> are left-aligned (recipient/employer address).
Do NOT add commas — each address part is already on its own line.

{sender_block}

{employer_block}

---

[Letter body here]

---

Rules for the letter body:
- 3–4 paragraphs, maximum 400 words
- Opening: specific reference to the role and why this candidate is drawn to it — one concrete reason, not a list
- Middle paragraphs: draw on the MOST RELEVANT experiences from across the candidate's full
  background — current role, previous work, volunteering, and academic work. Do not default
  to only the current role. Pick the 2–3 experiences that best match the specific job requirements.
  For each experience used, name the organisation and give a concrete achievement or example.
- Closing: confident, forward-looking, brief
- Tone: professional but natural — write as a real person would, not as a template
- Do NOT start with "I am writing to..."
- Write in UK English

CRITICAL — write so this cannot be detected as AI-generated:
- Vary paragraph and sentence length deliberately — include at least one short punchy sentence
- No transition words: never "Furthermore", "Moreover", "Additionally", "In conclusion", "It is worth noting", "I am passionate about"
- No buzzwords: never "leverage", "synergise", "dynamic", "spearheaded", "impactful", "proactive", "results-driven", "keen", "robust"
- Avoid sycophantic openers about the organisation — get to the point
- Do not use em-dashes (—) as a stylistic device
- Avoid over-formal constructions — "I have" is fine, "I possess" is not
- Let specific facts and named examples do the persuading, not adjectives
- The letter should read like a confident person wrote it quickly and well, not like a polished template
- Vary how sentences begin — do not start three sentences in a row with "I"

CANDIDATE NAME: {candidate_name}
DATE: {date}
JOB TITLE: {job_title}
EMPLOYER: {employer}
HIRING MANAGER (use if known, otherwise use "Hiring Manager"): {hiring_manager}

JOB DESCRIPTION:
{job_description}

CANDIDATE'S FULL EXPERIENCE (use all sections to find the best examples):
{full_experience}

TAILORED CV SUMMARY:
{tailored_cv}

Write the cover letter now:
"""


def _friendly_api_error(e: Exception) -> str:
    """Return a plain-English message for common Anthropic API errors."""
    msg = str(e).lower()
    if any(k in msg for k in ("credit", "billing", "insufficient", "balance", "payment",
                               "quota", "402", "usage limit")):
        return (
            "Your Anthropic account has run out of credits.\n\n"
            "To top up, go to:\n"
            "console.anthropic.com → Billing → Add credits\n\n"
            "A $10 top-up is enough for hundreds of applications."
        )
    if any(k in msg for k in ("401", "authentication", "invalid x-api-key", "api key")):
        return (
            "Your Anthropic API key was rejected.\n\n"
            "Check that ANTHROPIC_API_KEY is correct in Settings."
        )
    if any(k in msg for k in ("rate", "429", "overload")):
        return "The Anthropic API is busy — please wait a minute and try again."
    return f"Anthropic API error: {e}"


class CVTailor:
    def __init__(self, config: Config):
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self.base_cv = self._load_base_cv()
        self.cv_style = self._load_style("cv_style.json")
        self.letter_style = self._load_style("cover_letter_style.json")

    def _load_base_cv(self) -> str:
        path = self.config.base_cv_path
        if not path.exists():
            console.print(f"[yellow]Warning: base_cv.md not found at {path}[/yellow]")
            return ""
        return path.read_text(encoding="utf-8")

    def _load_style(self, filename: str) -> StyleFingerprint:
        path = self.config.base_dir / filename
        if path.exists():
            try:
                return StyleFingerprint.from_json(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return StyleFingerprint()


    def score_only(self, job: dict, tracker) -> tuple:
        """
        Score a job match without tailoring. Cheap — one small API call.
        Saves score + reason to tracker and sets status to 'scored'.
        Returns (score: int, reason: str).
        """
        job_id    = job["id"]
        title     = job.get("title", "Unknown Role")
        employer  = job.get("employer", "Unknown Employer")
        description = job.get("description") or ""

        # Fetch description if missing
        if not description and job.get("url"):
            from job_scanner import JobScanner
            scanner = JobScanner(self.config)
            description = scanner.fetch_job_description(job["url"])

        job_text = f"Title: {title}\nEmployer: {employer}\n\nDescription:\n{description}"

        score_data = self._score_match(job_text)
        score  = score_data.get("score", 0)
        reason = score_data.get("reason", "")

        with tracker._connect() as conn:
            conn.execute(
                "UPDATE jobs SET match_score = ?, match_reason = ?, description = ?, "
                "status = 'scored', date_updated = ? WHERE id = ?",
                (score, reason, description[:3000], datetime.now().isoformat(), job_id)
            )
            tracker._log_event(conn, job_id, "scored", f"{score}% — {reason}")

        return score, reason

    def process_job(self, job: Dict, tracker) -> bool:
        """Score, tailor CV, and write cover letter for a job. Returns True on success."""
        if not self.base_cv:
            console.print("[red]Cannot tailor — base_cv.md is missing.[/red]")
            return False

        job_id = job["id"]
        title = job.get("title", "Unknown Role")
        employer = job.get("employer", "Unknown Employer")

        # Fetch description if not already stored
        description = job.get("description") or ""
        if not description and job.get("url"):
            from job_scanner import JobScanner
            scanner = JobScanner(self.config)
            description = scanner.fetch_job_description(job["url"])

        job_text = f"Title: {title}\nEmployer: {employer}\n\nDescription:\n{description}"

        try:
            # Step 1: Score the match
            console.print(f"    [dim]Scoring match...[/dim]", end="")
            score_data = self._score_match(job_text)
            score = score_data.get("score", 0)
            reason = score_data.get("reason", "")
            console.print(f" [bold]{score}%[/bold]")

            # Skip very poor matches (configurable threshold)
            if score < self.config.min_match_score:
                console.print(f"    [yellow]Low match ({score}%) — skipping tailoring.[/yellow]")
                tracker.update_status(job_id, "skipped", f"Low match score: {score}%")
                # Still store the score
                with tracker._connect() as conn:
                    conn.execute(
                        "UPDATE jobs SET match_score = ?, match_reason = ?, description = ? WHERE id = ?",
                        (score, reason, description, job_id)
                    )
                return False

            # Update score + description in tracker
            with tracker._connect() as conn:
                conn.execute(
                    "UPDATE jobs SET match_score = ?, match_reason = ?, description = ? WHERE id = ?",
                    (score, reason, description, job_id)
                )

            # Step 2: Tailor the CV
            console.print(f"    [dim]Tailoring CV...[/dim]")
            tailored_cv = self._tailor_cv(title, employer, description)

            # Step 3: Write cover letter
            console.print(f"    [dim]Writing cover letter...[/dim]")
            cover_letter = self._write_cover_letter(title, employer, job.get("location", ""), description, tailored_cv)

            # Step 4: Save files
            slug = self._slug(f"{title}_{employer}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            out_dir = self.config.output_dir / f"job_{job_id:04d}_{slug}"
            out_dir.mkdir(exist_ok=True)

            # Save Markdown source (always — useful for editing)
            cv_md_path = out_dir / f"cv_{timestamp}.md"
            letter_md_path = out_dir / f"cover_letter_{timestamp}.md"
            cv_header = self._build_cv_header(title, employer, score, score_data)
            cv_md_path.write_text(cv_header + tailored_cv, encoding="utf-8")
            letter_md_path.write_text(cover_letter, encoding="utf-8")

            # Generate styled .docx files
            cv_docx_path = out_dir / f"cv_{timestamp}.docx"
            letter_docx_path = out_dir / f"cover_letter_{timestamp}.docx"
            try:
                cv_gen = DocGenerator(style=self.cv_style)
                cv_gen.generate_cv(tailored_cv, cv_docx_path)

                letter_gen = DocGenerator(style=self.letter_style)
                letter_gen.generate_cover_letter(
                    cover_letter, letter_docx_path,
                    candidate_name=self.config.candidate_name,
                    job_title=title, employer=employer
                )
                console.print(f"    [dim]→ .docx files created[/dim]")

                # Convert to PDF
                cv_pdf = cv_gen.convert_to_pdf(cv_docx_path)
                letter_pdf = letter_gen.convert_to_pdf(letter_docx_path)
                if cv_pdf or letter_pdf:
                    console.print(f"    [dim]→ PDF files created[/dim]")
                else:
                    console.print(f"    [yellow]→ PDF conversion unavailable (install LibreOffice or docx2pdf)[/yellow]")

                # Use docx as the primary tracked path
                primary_cv = str(cv_docx_path)
                primary_letter = str(letter_docx_path)

            except Exception as e:
                console.print(f"    [yellow]→ .docx generation failed ({e}), falling back to Markdown[/yellow]")
                primary_cv = str(cv_md_path)
                primary_letter = str(letter_md_path)

            # Save job description copy
            (out_dir / "job_description.txt").write_text(
                f"{title} @ {employer}\n{job.get('url', '')}\n\n{description}",
                encoding="utf-8"
            )

            # Update tracker
            tracker.update_documents(job_id, primary_cv, primary_letter)

            console.print(
                f"    [green]✓ Saved to {out_dir.name}/[/green]"
            )
            return True

        except anthropic.APIError as e:
            msg = _friendly_api_error(e)
            console.print(f"    [red]{msg}[/red]")
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = _friendly_api_error(e)
            console.print(f"    [red]{msg}[/red]")
            raise

    def _score_match(self, job_text: str) -> Dict:
        prompt = SCORE_PROMPT.format(job_text=job_text, cv_text=self.base_cv)
        try:
            message = self.client.messages.create(
                model=self.config.claude_model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
        except Exception as e:
            raise RuntimeError(_friendly_api_error(e)) from e
        raw = message.content[0].text.strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"score": 50, "reason": "Could not parse score response."}

    def _tailor_cv(self, title: str, employer: str, description: str) -> str:
        prompt = TAILOR_CV_PROMPT.format(
            job_title=title,
            employer=employer,
            job_description=description,
            cv_text=self.base_cv,
        )
        message = self.client.messages.create(
            model=self.config.claude_model,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()

    def _write_cover_letter(
        self, title: str, employer: str, location: str, description: str, tailored_cv: str
    ) -> str:
        from datetime import datetime as dt
        date_str = dt.now().strftime("%d %b %Y")  # e.g. 26 Mar 2026

        hiring_manager = "Hiring Manager"

        # Build sender block — layout:
        #   line 1: blank
        #   line 2: candidate name
        #   line 3: blank
        #   line 4+: address parts (one per line, no commas)
        #   blank, then date
        sender_lines = [
            "",                                  # line 1: blank
            self.config.candidate_name,          # line 2: name
            "",                                  # line 3: blank
        ]
        if getattr(self.config, "candidate_address", ""):
            sender_lines.append(self.config.candidate_address)   # line 4
        for part in (getattr(self.config, "candidate_address2", "") or "").split(","):
            part = part.strip()
            if part:
                sender_lines.append(part)
        sender_lines.append("")                  # blank before date
        sender_lines.append(date_str)
        sender_block = "\n".join(f">>> {p}" if p else ">>>" for p in sender_lines)

        # Build employer block — each part on its own line, no commas
        employer_parts = [employer] if employer else []
        for part in (location or "").split(","):
            part = part.strip()
            if part and part.lower() not in [p.lower() for p in employer_parts]:
                employer_parts.append(part)
        employer_block = "\n".join(employer_parts)

        prompt = COVER_LETTER_PROMPT.format(
            sender_block=sender_block,
            employer_block=employer_block,
            candidate_name=self.config.candidate_name,
            date=date_str,
            job_title=title,
            employer=employer,
            hiring_manager=hiring_manager,
            job_description=description,
            full_experience=self.base_cv,
            tailored_cv=tailored_cv[:2000],
        )
        message = self.client.messages.create(
            model=self.config.claude_model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()

    def _build_cv_header(self, title: str, employer: str, score: int, score_data: Dict) -> str:
        lines = [
            f"<!-- TAILORED FOR: {title} @ {employer} -->",
            f"<!-- MATCH SCORE: {score}% -->",
            f"<!-- REASON: {score_data.get('reason', '')} -->",
            f"<!-- GENERATED: {datetime.now().strftime('%Y-%m-%d %H:%M')} -->",
            "",
            "> **⚠️ REVIEW BEFORE SENDING** — This CV was AI-tailored. Please check for accuracy.",
            "",
        ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _slug(text: str) -> str:
        text = re.sub(r"[^\w\s-]", "", text.lower())
        text = re.sub(r"[\s_]+", "_", text)
        return text[:40].strip("_")

# Job Application Agent

An AI-powered job hunting system.
Scans job boards → scores matches → tailors CV + cover letter → queues for human review.

**Nothing is sent automatically.** Every application must be approved by a human first.

---

## First-Time Setup (fresh download)

Follow these steps in order. The project contains **no personal data or API keys** — you supply everything locally.

### Step 1 — Install Python dependencies

```bash
pip install -r requirements.txt
```

Requires Python 3.10+.

### Step 2 — Get your API keys

You need accounts and API keys from:

| Service | Purpose | Sign up |
|---------|---------|---------|
| Anthropic | AI scoring and CV tailoring | https://console.anthropic.com/ |
| Reed | UK job board | https://www.reed.co.uk/developers/ |
| Adzuna | UK job board | https://developer.adzuna.com/ |

Reed and Adzuna are free tiers. Anthropic costs roughly $0.01 per job scored, $0.05 per CV tailored.

### Step 3 — Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in every value:

```
ANTHROPIC_API_KEY=sk-ant-...
REED_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...

CANDIDATE_NAME=Your Full Name
CANDIDATE_EMAIL=you@example.com
CANDIDATE_PHONE=+44 7700 000000
CANDIDATE_LINKEDIN=https://www.linkedin.com/in/your-profile/
CANDIDATE_LOCATION=City, Country
CANDIDATE_ADDRESS=Your Street Address
CANDIDATE_ADDRESS2=City, Postcode

OUTPUT_DIR=/path/to/where/you/want/generated/files
```

**Never commit `.env`** — it is gitignored.

### Step 4 — Create your CV

```bash
cp base_cv.md.example base_cv.md
```

Edit `base_cv.md` with your real details — education, experience, skills.
This is the master CV that Claude uses as source material for every application.

Tips for best results:
- Use specific achievements with numbers ("reduced X by 20%") not just duties
- Include all roles, even if short — Claude picks what's relevant per job
- Keep it in Markdown — headings, bullet points, bold for job titles

**Never commit `base_cv.md`** — it is gitignored.

### Step 5 — Run

```bash
# Scan for new jobs
python src/main.py scan

# Review pending applications (approve or skip each one)
python src/main.py review

# View dashboard
python src/main.py status
```

---

## Architecture

```
src/main.py          ← Orchestrator / CLI entry point
src/config.py        ← All settings (loaded from .env)
base_cv.md           ← Your master CV (gitignored — create from base_cv.md.example)
src/job_scanner.py   ← Scans Reed, Adzuna, and other job boards
src/cv_tailor.py     ← Claude API: scores match, tailors CV, writes cover letter
src/tracker.py       ← SQLite database: tracks all jobs and applications
src/review_queue.py  ← Interactive CLI: approve / skip each application
output/              ← Generated CVs and cover letters (one folder per job, gitignored)
applications.db      ← SQLite database (auto-created, gitignored)
```

---

## How It Works

### Scanning
The scanner searches configured job boards using the keywords in `src/config.py`. New jobs are saved to the SQLite database at no API cost.

### Scoring & Tailoring
For each selected job, Claude:
1. **Scores** the match (0–100%) — jobs below the threshold are skipped automatically
2. **Rewrites** the CV, reordering and rephrasing to emphasise relevant experience
3. **Writes** a tailored cover letter (3–4 paragraphs, UK English, non-generic)

Output is saved to `output/job_NNNN_<role_slug>/`:
```
output/
  job_0001_policy_analyst_cabinet_office/
    cv_20250115_1430.md
    cover_letter_20250115_1430.md
    job_description.txt
```

### Review Queue
`python src/main.py review` walks through each pending application:
- Shows job details + match score
- Opens the CV and cover letter files in your editor
- You approve ✓ or skip ✗ each one
- Approved applications are flagged "ready to submit" — you copy/paste or upload manually

### Application Tracking

All jobs flow through these statuses:

```
discovered → tailored → pending_review → approved → submitted → interview / offer / rejected
```

---

## Tips

**Improving CV quality:**
The better your `base_cv.md`, the better the tailored output. Include specific achievements with numbers ("reduced processing time by 30%"), not just duties.

**Tuning the match threshold:**
Change the `if score < 30:` line in `src/cv_tailor.py` to raise or lower the minimum match score for tailoring.

**Adding job boards:**
Add a `_scan_<sourcename>()` method to `src/job_scanner.py` returning `List[Dict]` with keys:
`title, employer, location, salary, url, description, source, date_closes`
Then call it from `scan_all()`.

**Scheduling:**
Run `python src/main.py scan` daily via cron or Task Scheduler:
```bash
# Cron: run every weekday morning at 8am
0 8 * * 1-5 cd /path/to/job_agent && python src/main.py scan
```

---

## Application Status Reference

| Status | Meaning |
|--------|---------|
| `discovered` | Job found, not yet tailored |
| `tailored` | CV + letter generated, awaiting review |
| `approved` | Human approved — ready to submit |
| `skipped` | Decided not to apply |
| `submitted` | Application sent |
| `interview` | Interview secured |
| `rejected` | Unsuccessful |
| `offer` | Offer received |

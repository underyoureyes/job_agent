# Job Application Agent

An AI-powered job hunting system with a desktop GUI.
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

# Optional: session summary email
NOTIFY_EMAIL=you@example.com
SMTP_FROM=you@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password

# Optional: auto-apply credentials
REED_LOGIN_EMAIL=you@example.com
REED_LOGIN_PASSWORD=yourpassword
LINKEDIN_APPLY_EMAIL=you@example.com
LINKEDIN_APPLY_PASSWORD=yourpassword
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

### Step 5 — Run the GUI

```bash
python src/app.py
```

Or use the built `.app` on macOS.

---

## GUI Screens

The app is a Tkinter desktop GUI. All screens are accessible from the left sidebar.

| Screen | Purpose |
|--------|---------|
| **Dashboard** | Overview of all applications with status badges and counts |
| **Screen jobs** | Browse discovered jobs, score selected ones, tailor to CV |
| **Add by description** | Paste a job description from an email, generate CV + cover letter instantly |
| **Review queue** | Read each tailored CV and cover letter, approve or skip |
| **Settings** | Edit search keywords, salary range, match threshold, session email |
| **Setup** | Upload CV/cover letter templates, enter candidate details |
| **Scan log** | Live output from the last scan or tailoring run |
| **Database** | Browse and search all jobs in the SQLite database, export to Excel |
| **Info** | App version and help links |

The **Scan for jobs** button at the bottom of the sidebar runs a full scan across all configured job boards.

---

## Add Job by Description

Use this when you receive a job by email or find one outside the supported job boards:

1. Click **Add by description** in the sidebar
2. Enter the **Job title** and **Employer** (required)
3. Optionally enter Location and Salary
4. Paste the full job description into the text box
5. Click **Generate CV & Cover Letter**

The job bypasses scoring and goes straight to tailoring (~$0.05 in API credits).
When done you are prompted to go to the Review queue to check the output.

---

## Architecture

```
src/app.py                   ← GUI entry point (runs JobAgentShell)
src/ui/app_shell.py          ← Top-level window, sidebar, screen router
src/ui/screens/
  dashboard.py               ← Application overview + status badges
  scan.py                    ← Screen jobs: score and tailor from job board results
  add_job.py                 ← Add job by pasting a description
  review.py                  ← Review queue: approve or skip tailored applications
  settings.py                ← Search config, salary range, score threshold, email
  setup.py                   ← Candidate details, CV upload
  log.py                     ← Live scan/tailor log
  database.py                ← Browse all jobs, export to Excel
  info.py                    ← Help and version info
src/main.py                  ← Orchestrator (also usable as CLI)
src/config.py                ← All settings (loaded from .env + user prefs)
src/job_scanner.py           ← Scans Reed, Adzuna, Civil Service, Guardian, LinkedIn, W4MP, CharityJob
src/cv_tailor.py             ← Claude API: scores match, tailors CV, writes cover letter
src/tracker.py               ← SQLite database: tracks all jobs and applications
src/review_queue.py          ← CLI review queue (fallback if not using GUI)
src/session_log.py           ← Records session activity, sends summary email on close
src/doc_generator.py         ← Generates .docx CV and cover letter files
src/document_processor.py    ← Reads and processes base_cv.md
src/reed_apply.py            ← Auto-apply via Reed (Playwright)
src/linkedin_apply.py        ← Auto-apply via LinkedIn Easy Apply (Playwright)
base_cv.md                   ← Your master CV (gitignored — create from base_cv.md.example)
output/                      ← Generated CVs and cover letters (gitignored)
applications.db              ← SQLite database (auto-created, gitignored)
```

---

## How It Works

### Scanning
The scanner searches Reed, Adzuna, Civil Service Jobs, The Guardian, LinkedIn, W4MP Jobs, and CharityJob using the keywords in `src/config.py`. New jobs are saved to the SQLite database at no API cost. Free filters (seniority, irrelevant titles, location, salary) run automatically.

### Screening
Open **Screen jobs** to browse discovered job titles. Tick the ones you want to apply for, then click **Score selected** (~$0.01 per job). Claude scores each job against your CV and flags matches below the threshold automatically.

### Tailoring
After scoring, tick the jobs you want to tailor and click **Tailor scored jobs** (~$0.05 per job). Claude:
1. **Rewrites** the CV, reordering and rephrasing to emphasise relevant experience
2. **Writes** a tailored cover letter (3–4 paragraphs, UK English, non-generic)

Output is saved to `output/job_NNNN_<role_slug>/`:
```
output/
  job_0001_policy_analyst_cabinet_office/
    cv_20250115_1430.md
    cover_letter_20250115_1430.md
    job_description.txt
```

### Review Queue
**Review queue** walks through each pending application:
- Shows job details + match score
- Opens the CV and cover letter
- You approve or skip each one
- Approved applications are flagged "ready to submit"

### Session Summary Email
When you close the app, if any applications were scored or tailored during the session, a summary email is sent to `NOTIFY_EMAIL` (if configured in `.env`).

### Auto-Apply (experimental)
Reed and LinkedIn Easy Apply credentials can be stored in `.env`. The app can submit approved applications automatically via Playwright. **Use with caution** — always review before enabling.

### Application Tracking

All jobs flow through these statuses:

```
discovered → score_me → scored → tailoring → tailored → pending_review → approved → submitted → interview / offer / rejected
```

Manual jobs added via **Add by description** skip to `tailoring` directly.

---

## CLI Usage (alternative to GUI)

```bash
# Scan for new jobs
python src/main.py scan

# Score jobs selected in the UI
python src/main.py score_selected

# Tailor jobs approved for tailoring
python src/main.py tailor_approved

# Tailor one specific job by ID
python src/main.py tailor 42

# Review pending applications (CLI)
python src/main.py review

# View dashboard
python src/main.py status
```

---

## Tips

**Improving CV quality:**
The better your `base_cv.md`, the better the tailored output. Include specific achievements with numbers ("reduced processing time by 30%"), not just duties.

**Tuning the match threshold:**
Change `min_match_score` in `src/config.py` (or via the Settings screen) to raise or lower the minimum match score for tailoring.

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
| `discovered` | Job found, not yet scored |
| `score_me` | Selected by user for scoring |
| `scored` | AI scored — user reviews before tailoring |
| `filtered` | Auto-filtered (too senior / irrelevant / low score) |
| `dismissed` | Manually hidden by user |
| `tailoring` | Queued for CV + cover letter generation |
| `tailored` | Docs ready — awaiting review |
| `pending_review` | In the review queue |
| `approved` | Human approved — ready to submit |
| `skipped` | Decided not to apply |
| `submitted` | Application sent |
| `interview` | Interview secured |
| `rejected` | Unsuccessful |
| `offer` | Offer received |

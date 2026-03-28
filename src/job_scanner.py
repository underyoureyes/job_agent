"""
job_scanner.py - Multi-Source Job Board Scanner
================================================
Searches Reed API, Civil Service Jobs, and Guardian Jobs.
Each source returns a normalised job dict for the tracker.

To add a new source: create a method _scan_<sourcename>()
that returns List[Dict] and add it to scan_all().
"""

import time
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import urlencode, quote_plus
from bs4 import BeautifulSoup
from rich.console import Console
from config import Config

console = Console()


class JobScanner:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })

    def scan_all(self) -> List[Dict]:
        """Run all enabled scanners and return deduplicated job list."""
        all_jobs = []

        # Reed API
        if self.config.reed_api_key and self.config.reed_api_key != "YOUR_REED_API_KEY":
            console.print("  [cyan]→[/cyan] Scanning Reed.co.uk...")
            try:
                jobs = self._scan_reed()
                console.print(f"    [green]{len(jobs)} jobs found[/green]")
                all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"    [red]Reed scan failed: {e}[/red]")
        else:
            console.print("  [dim]→ Reed skipped (no API key)[/dim]")

        # Civil Service Jobs
        if self.config.scan_civil_service:
            console.print("  [cyan]→[/cyan] Scanning Civil Service Jobs...")
            try:
                jobs = self._scan_civil_service()
                console.print(f"    [green]{len(jobs)} jobs found[/green]")
                all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"    [red]Civil Service scan failed: {e}[/red]")

        # Guardian Jobs
        if self.config.scan_guardian:
            console.print("  [cyan]→[/cyan] Scanning Guardian Jobs...")
            try:
                jobs = self._scan_guardian()
                console.print(f"    [green]{len(jobs)} jobs found[/green]")
                all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"    [red]Guardian scan failed: {e}[/red]")

        # Adzuna API
        if hasattr(self.config, 'adzuna_app_id') and self.config.adzuna_app_id not in ("your_app_id_here", "", None):
            console.print("  [cyan]→[/cyan] Scanning Adzuna...")
            try:
                jobs = self._scan_adzuna()
                console.print(f"    [green]{len(jobs)} jobs found[/green]")
                all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"    [red]Adzuna scan failed: {e}[/red]")
        else:
            console.print("  [dim]→ Adzuna skipped (no API key)[/dim]")

        # LinkedIn RSS
        if self.config.scan_linkedin:
            console.print("  [cyan]→[/cyan] Scanning LinkedIn (RSS)...")
            try:
                jobs = self._scan_linkedin_rss()
                console.print(f"    [green]{len(jobs)} jobs found[/green]")
                all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"    [red]LinkedIn RSS scan failed: {e}[/red]")

        # Total Jobs
        if self.config.scan_totaljobs:
            console.print("  [cyan]→[/cyan] Scanning Total Jobs...")
            try:
                jobs = self._scan_totaljobs()
                console.print(f"    [green]{len(jobs)} jobs found[/green]")
                all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"    [red]Total Jobs scan failed: {e}[/red]")

        # W4MP Jobs
        if self.config.scan_w4mpjobs:
            console.print("  [cyan]→[/cyan] Scanning W4MP Jobs...")
            try:
                jobs = self._scan_w4mpjobs()
                console.print(f"    [green]{len(jobs)} jobs found[/green]")
                all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"    [red]W4MP Jobs scan failed: {e}[/red]")

        # Charity Job
        if self.config.scan_charityjob:
            console.print("  [cyan]→[/cyan] Scanning Charity Job...")
            try:
                jobs = self._scan_charityjob()
                console.print(f"    [green]{len(jobs)} jobs found[/green]")
                all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"    [red]Charity Job scan failed: {e}[/red]")

        # LinkedIn manual file (fallback for when RSS is throttled)
        if self.config.linkedin_manual_file:
            console.print("  [cyan]→[/cyan] Reading LinkedIn manual file...")
            try:
                jobs = self._scan_linkedin_manual()
                console.print(f"    [green]{len(jobs)} jobs found[/green]")
                all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"    [red]LinkedIn manual file failed: {e}[/red]")

        # Deduplicate by URL
        seen_urls = set()
        unique_jobs = []
        for job in all_jobs:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                unique_jobs.append(job)

        return unique_jobs

    # ── Reed API ──────────────────────────────────────────────────────────────

    def _scan_reed(self) -> List[Dict]:
        """Scan Reed.co.uk via their official API."""
        jobs = []

        for keyword in self.config.search_keywords[:5]:  # limit to avoid hammering API
            params = {
                "keywords": keyword,
                "locationName": self.config.search_location,
                "distancefromLocation": self.config.search_radius_miles,
                "minimumSalary": self.config.min_salary_gbp if self.config.min_salary_gbp > 0 else None,
                "postedByRecruitmentAgency": False,
                "resultsToTake": 25,
            }
            params = {k: v for k, v in params.items() if v is not None}

            resp = requests.get(
                "https://www.reed.co.uk/api/1.0/search",
                params=params,
                auth=(self.config.reed_api_key, ""),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            cutoff = datetime.now() - timedelta(days=self.config.max_job_age_days)

            for item in data.get("results", []):
                date_str = item.get("date", "")
                try:
                    posted = datetime.strptime(date_str, "%d/%m/%Y")
                    if posted < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

                jobs.append(self._normalise_reed(item))

            time.sleep(0.5)  # be polite to the API

        return jobs

    def _normalise_reed(self, item: Dict) -> Dict:
        job_id = item.get("jobId", "")
        url = item.get("jobUrl") or f"https://www.reed.co.uk/jobs/{job_id}"
        return {
            "title": item.get("jobTitle", ""),
            "employer": item.get("employerName", ""),
            "location": item.get("locationName", ""),
            "salary": self._format_salary(
                item.get("minimumSalary"), item.get("maximumSalary"), item.get("currency", "£")
            ),
            "url": url,
            "description": item.get("jobDescription", ""),
            "source": "reed",
            "date_closes": item.get("expirationDate"),
        }

    # ── Civil Service / Find a Job (DWP) ─────────────────────────────────────
    # civilservicejobs.service.gov.uk blocks scrapers with a JS bot check.
    # findajob.dwp.gov.uk is the official DWP job search — accessible, includes
    # Civil Service roles, and returns well-structured HTML.

    def _scan_civil_service(self) -> List[Dict]:
        """Search findajob.dwp.gov.uk — the official UK government job board."""
        jobs = []
        base_url = "https://findajob.dwp.gov.uk"

        for keyword in self.config.search_keywords[:6]:
            url = (
                f"{base_url}/search"
                f"?q={quote_plus(keyword)}"
                f"&w={quote_plus(self.config.search_location)}"
                f"&d={self.config.search_radius_miles}"
                f"&pp=25"
            )
            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for card in soup.select("div.search-result"):
                    try:
                        title_el = card.select_one("h3 a.govuk-link")
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        job_url = title_el.get("href", "")
                        if not job_url.startswith("http"):
                            job_url = base_url + job_url

                        details = card.select("ul.search-result-details li")
                        employer, location, salary = "", self.config.search_location, ""
                        if len(details) >= 2:
                            employer_loc = details[1].get_text(strip=True)
                            if " - " in employer_loc:
                                employer, location = employer_loc.split(" - ", 1)
                            else:
                                employer = employer_loc

                        salary_el = card.select_one(".search-result-salary, [class*='salary']")
                        if salary_el:
                            salary = salary_el.get_text(strip=True)

                        if not title or not job_url:
                            continue

                        jobs.append({
                            "title": title,
                            "employer": employer.strip(),
                            "location": location.strip(),
                            "salary": salary,
                            "url": job_url,
                            "description": "",
                            "source": "civil_service",
                            "date_closes": "",
                        })
                    except Exception:
                        continue

                time.sleep(1)

            except Exception as e:
                console.print(f"    [dim]Find a Job keyword '{keyword}' failed: {e}[/dim]")
                continue

        return jobs

    # ── Guardian Jobs ─────────────────────────────────────────────────────────

    def _scan_guardian(self) -> List[Dict]:
        """Scrape Guardian Jobs for policy/public affairs roles."""
        jobs = []
        base_url = "https://jobs.theguardian.com"

        for keyword in self.config.search_keywords[:6]:
            url = (
                f"{base_url}/jobs/"
                f"?keywords={quote_plus(keyword)}&location=London&radius=25"
            )
            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for card in soup.select("li.lister__item"):
                    try:
                        title_el = card.select_one("h3.lister__header a span")
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)

                        link_el = card.select_one("h3.lister__header a")
                        href = (link_el.get("href") or "").strip()
                        if not href:
                            continue
                        job_url = base_url + href if href.startswith("/") else href

                        location_el = card.select_one("li.lister__meta-item--location")
                        location = location_el.get_text(strip=True) if location_el else "London"

                        salary_el = card.select_one("li.lister__meta-item--salary")
                        salary = salary_el.get_text(strip=True) if salary_el else ""

                        employer_el = card.select_one("li.lister__meta-item--recruiter")
                        employer = employer_el.get_text(strip=True) if employer_el else ""

                        desc_el = card.select_one("p.lister__description")
                        description = desc_el.get_text(strip=True) if desc_el else ""

                        jobs.append({
                            "title": title,
                            "employer": employer,
                            "location": location,
                            "salary": salary,
                            "url": job_url,
                            "description": description,
                            "source": "guardian",
                            "date_closes": "",
                        })
                    except Exception:
                        continue

                time.sleep(1)

            except Exception as e:
                console.print(f"    [dim]Guardian keyword '{keyword}' failed: {e}[/dim]")
                continue

        return jobs



    def _scan_adzuna(self) -> List[Dict]:
        """
        Adzuna UK Jobs API — free, reliable, covers 1000s of UK sources
        including Civil Service, Guardian, Times, charity sector and more.
        Get keys at: developer.adzuna.com
        """
        jobs = []
        base = "https://api.adzuna.com/v1/api/jobs/gb/search/1"

        for keyword in self.config.search_keywords[:6]:
            params = {
                "app_id":           self.config.adzuna_app_id,
                "app_key":          self.config.adzuna_app_key,
                "what":             keyword,
                "where":            self.config.search_location,
                "distance":         self.config.search_radius_miles,
                "results_per_page": 20,
                "sort_by":          "date",
                "max_days_old":     self.config.max_job_age_days,
                "content-type":     "application/json",
            }
            if self.config.min_salary_gbp:
                params["salary_min"] = self.config.min_salary_gbp

            try:
                resp = self.session.get(base, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("results", []):
                    title    = item.get("title", "").strip()
                    url      = item.get("redirect_url", "").strip()
                    employer = item.get("company", {}).get("display_name", "")
                    location = item.get("location", {}).get("display_name", "")
                    desc     = item.get("description", "").strip()
                    sal_min  = item.get("salary_min")
                    sal_max  = item.get("salary_max")
                    salary   = self._format_salary(sal_min, sal_max)

                    if not title or not url:
                        continue

                    jobs.append({
                        "title":       title,
                        "employer":    employer,
                        "location":    location,
                        "salary":      salary,
                        "url":         url,
                        "description": desc[:2000],
                        "source":      "adzuna",
                        "date_closes": "",
                    })

                time.sleep(0.5)

            except Exception as e:
                console.print(f"    [dim]Adzuna '{keyword}' failed: {e}[/dim]")

        return jobs

    def _scan_linkedin_manual(self) -> List[Dict]:
        """
        Reads linkedin_manual.txt (one URL per line) and creates job entries
        for each URL not already in the tracker. The job description is fetched
        automatically. Use this when the RSS scraper is throttled.

        File format (one per line, lines starting with # are ignored):
            https://www.linkedin.com/jobs/view/1234567890/
            https://www.linkedin.com/jobs/view/9876543210/  # optional note
        """
        from pathlib import Path
        jobs = []
        manual_path = Path(self.config.linkedin_manual_file)
        if not manual_path.exists():
            console.print(f"    [yellow]Manual file not found: {manual_path}[/yellow]")
            return jobs

        lines = manual_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.split("#")[0].strip()
            if not line or not line.startswith("http"):
                continue
            url = line.split("?")[0].rstrip("/")
            jobs.append({
                "title": "LinkedIn job (manual)",
                "employer": "",
                "location": self.config.search_location,
                "salary": "",
                "url": url,
                "description": "",
                "source": "linkedin_manual",
                "date_closes": "",
            })
        return jobs

    # ── LinkedIn RSS ──────────────────────────────────────────────────────────

    def _scan_linkedin_rss(self) -> List[Dict]:
        """
        Scrape LinkedIn job search via their (unofficial) RSS/XML feed.

        LinkedIn surfaces RSS-compatible XML at their job search URL when
        called with the right parameters. No login required, but results
        are limited (~25 per keyword) and LinkedIn may throttle aggressive
        polling — respect the 2s sleep between keywords.

        Feed URL format:
          https://www.linkedin.com/jobs/search/?
            keywords=<kw>&location=<loc>&f_TPR=r86400&distance=25&f_WT=2

        f_TPR=r86400  → posted in last 24h (86400 seconds)
        f_WT=2        → remote jobs (omit to include all work types)
        """
        jobs = []
        cutoff = datetime.now() - timedelta(days=self.config.max_job_age_days)

        # LinkedIn RSS endpoint (returns Atom/RSS-flavoured HTML we parse with BS4)
        base = "https://www.linkedin.com/jobs/search/"

        for keyword in self.config.search_keywords[:6]:  # stay polite
            params = {
                "keywords": keyword,
                "location": self.config.search_location,
                "distance": self.config.search_radius_miles,
                "f_TPR": f"r{self.config.max_job_age_days * 86400}",
                "trk": "public_jobs_jobs-search-bar_search-submit",
                "position": 1,
                "pageNum": 0,
            }

            url = base + "?" + urlencode(params)

            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                # LinkedIn public job search page — scrape job cards
                for card in soup.select("li.jobs-search__results-list > div, "
                                        "li[class*='job-search-card'], "
                                        ".base-card, .job-search-card"):
                    try:
                        title_el = (
                            card.select_one("h3.base-search-card__title") or
                            card.select_one(".job-search-card__title") or
                            card.select_one("h3")
                        )
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)

                        link_el = card.select_one("a.base-card__full-link, a[href*='linkedin.com/jobs/view']")
                        job_url = link_el["href"].split("?")[0] if link_el else ""
                        if not job_url:
                            continue

                        employer_el = (
                            card.select_one("h4.base-search-card__subtitle") or
                            card.select_one(".job-search-card__company-name") or
                            card.select_one("h4")
                        )
                        employer = employer_el.get_text(strip=True) if employer_el else ""

                        location_el = (
                            card.select_one(".job-search-card__location") or
                            card.select_one("span.job-result-card__location")
                        )
                        location = location_el.get_text(strip=True) if location_el else self.config.search_location

                        # Date posted
                        date_el = card.select_one("time[datetime]")
                        if date_el:
                            date_str = date_el.get("datetime", "")
                            try:
                                posted = datetime.fromisoformat(date_str[:10])
                                if posted < cutoff:
                                    continue
                            except ValueError:
                                pass

                        jobs.append({
                            "title": title,
                            "employer": employer,
                            "location": location,
                            "salary": "",   # LinkedIn rarely shows salary publicly
                            "url": job_url,
                            "description": "",  # fetched on demand by cv_tailor
                            "source": "linkedin",
                            "date_closes": "",
                        })
                    except Exception:
                        continue

            except Exception as e:
                console.print(f"    [dim]LinkedIn keyword '{keyword}' failed: {e}[/dim]")

            time.sleep(2)  # LinkedIn is rate-sensitive — be respectful

        # Also try the structured RSS feed LinkedIn exposes (more reliable for some regions)
        jobs.extend(self._scan_linkedin_rss_feed())
        return jobs

    def _scan_linkedin_rss_feed(self) -> List[Dict]:
        """
        Secondary LinkedIn source: their RSS/Atom feed endpoint.
        Returns XML that we parse with ElementTree.
        Only covers a subset of roles but is more stable than scraping.
        """
        jobs = []
        rss_base = "https://www.linkedin.com/jobs/search.rss"

        # Use a smaller keyword set for the RSS — it's more limited
        rss_keywords = [kw for kw in self.config.search_keywords if "policy" in kw.lower()][:3]

        for keyword in rss_keywords:
            params = {
                "keywords": keyword,
                "location": self.config.search_location,
                "distance": self.config.search_radius_miles,
                "f_TPR": "r604800",  # last 7 days
            }
            url = rss_base + "?" + urlencode(params)

            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()

                # Parse as RSS XML
                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}

                # Try RSS 2.0 items first
                channel = root.find("channel")
                items = channel.findall("item") if channel is not None else []

                # Fall back to Atom entries
                if not items:
                    items = root.findall(".//atom:entry", ns)

                for item in items:
                    try:
                        title = (
                            (item.findtext("title") or
                             item.findtext("atom:title", namespaces=ns) or "").strip()
                        )
                        link = (
                            item.findtext("link") or
                            (item.find("atom:link", ns).get("href") if item.find("atom:link", ns) is not None else "") or ""
                        ).strip().split("?")[0]

                        if not title or not link:
                            continue

                        description = (item.findtext("description") or "").strip()
                        # Strip HTML from description if present
                        if "<" in description:
                            description = BeautifulSoup(description, "html.parser").get_text(separator=" ", strip=True)

                        jobs.append({
                            "title": title,
                            "employer": "",
                            "location": self.config.search_location,
                            "salary": "",
                            "url": link,
                            "description": description[:2000],
                            "source": "linkedin_rss",
                            "date_closes": "",
                        })
                    except Exception:
                        continue

            except Exception as e:
                console.print(f"    [dim]LinkedIn RSS feed '{keyword}' failed: {e}[/dim]")

            time.sleep(2)

        return jobs

    # ── Total Jobs ────────────────────────────────────────────────────────────

    def _scan_totaljobs(self) -> List[Dict]:
        """Total Jobs blocks automated requests (Cloudflare). Disabled by default."""
        console.print("    [dim]Total Jobs skipped — site blocks scrapers[/dim]")
        return []

    # ── W4MP Jobs ─────────────────────────────────────────────────────────────

    def _scan_w4mpjobs(self) -> List[Dict]:
        """Scrape W4MP Jobs — each job is a group of div.jobadvertdetailbox elements.
        Groups start with id='jobid' and are followed by id='location', 'salary', 'dates'."""
        jobs = []
        base_url = "https://www.w4mpjobs.org"
        url = f"{base_url}/SearchJobs.aspx?search=alljobs"

        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            all_boxes = soup.select("div.jobadvertdetailbox")

            # Walk the flat list of boxes, grouping by id="jobid" start markers
            current = {}
            for box in all_boxes:
                box_id = box.get("id", "")

                if box_id == "jobid":
                    # Save previous job if complete
                    if current.get("url"):
                        jobs.append(current)
                    # Start new job
                    link = box.select_one("a[href*='JobDetails.aspx']")
                    if not link:
                        current = {}
                        continue
                    href = link.get("href", "")
                    job_url = base_url + "/" + href.lstrip("/")
                    title_el = box.select_one("span[itemprop='title']")
                    employer_el = box.select_one("span[itemprop='hiringOrganization']")
                    current = {
                        "title":       title_el.get_text(strip=True) if title_el else "",
                        "employer":    employer_el.get_text(strip=True) if employer_el else "",
                        "url":         job_url,
                        "location":    "Westminster",
                        "salary":      "",
                        "date_closes": "",
                        "description": "",
                        "source":      "w4mpjobs",
                    }

                elif box_id == "location" and current:
                    text = box.get_text(strip=True).replace("Location:", "").strip()
                    current["location"] = text or "Westminster"

                elif box_id == "salary" and current:
                    current["salary"] = box.get_text(strip=True).replace("Salary:", "").strip()

                elif box_id == "dates" and current:
                    raw = box.get_text(strip=True)
                    if "closes on" in raw:
                        current["date_closes"] = raw.split("closes on")[-1].strip()

            # Don't forget the last job
            if current.get("url"):
                jobs.append(current)

        except Exception as e:
            console.print(f"    [dim]W4MP Jobs failed: {e}[/dim]")

        except Exception as e:
            console.print(f"    [dim]W4MP Jobs failed: {e}[/dim]")

        return jobs

    # ── Charity Job ───────────────────────────────────────────────────────────

    def _scan_charityjob(self) -> List[Dict]:
        """Scrape CharityJob.co.uk for policy and public affairs roles in the charity sector."""
        jobs = []
        base_url = "https://www.charityjob.co.uk"

        for keyword in self.config.search_keywords[:6]:
            url = (
                f"{base_url}/jobs"
                f"?keywords={quote_plus(keyword)}"
                f"&location={quote_plus(self.config.search_location)}"
                f"&radius={self.config.search_radius_miles}"
            )
            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for card in soup.select(".job-card, .search-result, article[class*='job']"):
                    try:
                        title_el = (
                            card.select_one("a[href*='/jobs/']") or
                            card.select_one("h2 a") or
                            card.select_one("h3 a")
                        )
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        href = title_el.get("href", "")
                        job_url = base_url + href if href.startswith("/") else href

                        employer_el = (
                            card.select_one("a[href*='/organisation/']") or
                            card.select_one(".employer, .organisation")
                        )
                        employer = employer_el.get_text(strip=True) if employer_el else ""

                        location_el = card.select_one(".location, .job-meta__location, [class*='location']")
                        location = location_el.get_text(strip=True) if location_el else self.config.search_location

                        salary_el = card.select_one(".salary, .salary-range, [class*='salary']")
                        salary = salary_el.get_text(strip=True) if salary_el else ""

                        closing_el = card.select_one(".closing-date, .date-closes, [class*='closing']")
                        closing = closing_el.get_text(strip=True) if closing_el else ""

                        if not title or not job_url:
                            continue

                        jobs.append({
                            "title": title,
                            "employer": employer,
                            "location": location,
                            "salary": salary,
                            "url": job_url,
                            "description": "",
                            "source": "charityjob",
                            "date_closes": closing,
                        })
                    except Exception:
                        continue

                time.sleep(1)

            except Exception as e:
                console.print(f"    [dim]Charity Job keyword '{keyword}' failed: {e}[/dim]")
                continue

        return jobs

    # ── Helpers ───────────────────────────────────────────────────────────────

    def fetch_job_description(self, url: str) -> str:
        """Attempt to fetch full job description from a job URL."""
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Try common selectors for job descriptions
            for selector in [
                ".job-description", "#job-description", "[data-job-description]",
                ".job-content", ".description", "article", "main"
            ]:
                el = soup.select_one(selector)
                if el:
                    text = el.get_text(separator="\n", strip=True)
                    if len(text) > 200:
                        return text[:5000]  # cap at 5k chars

        except Exception:
            pass
        return ""


    @staticmethod
    def _parse_feed(xml_text: str) -> list:
        """
        Tolerant RSS/Atom feed parser.
        Tries BeautifulSoup lxml-xml first (handles malformed feeds),
        falls back to strict ElementTree.
        Returns list of dicts with keys: title, link, description.
        """
        items = []

        # Primary: BeautifulSoup with lxml-xml — tolerant of malformed XML
        try:
            soup = BeautifulSoup(xml_text, "lxml-xml")
            tags = soup.find_all(["item", "entry"])
            for tag in tags:
                title = tag.find("title")
                link  = tag.find("link")
                desc  = tag.find(["description", "summary", "content"])
                link_text = ""
                if link:
                    link_text = link.get("href") or link.get_text(strip=True)
                items.append({
                    "title":       (title.get_text(strip=True) if title else ""),
                    "link":        link_text.strip(),
                    "description": (desc.get_text(strip=True) if desc else ""),
                })
            if items:
                return items
        except Exception:
            pass

        # Fallback: strict ElementTree
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for tag in root.findall(".//item") + root.findall(".//atom:entry", ns):
                title = tag.findtext("title") or tag.findtext("atom:title", namespaces=ns) or ""
                link  = tag.findtext("link") or ""
                desc  = tag.findtext("description") or tag.findtext("atom:summary", namespaces=ns) or ""
                items.append({
                    "title":       title.strip(),
                    "link":        link.strip(),
                    "description": desc.strip(),
                })
        except Exception:
            pass

        return items

    @staticmethod
    def _extract_label(text: str, label: str) -> str:
        """Extract the value after 'Label:' or 'label on' in a block of plain text."""
        import re
        pattern = re.compile(rf"{re.escape(label)}[:\s]+(.+)", re.IGNORECASE)
        m = pattern.search(text)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _format_salary(min_sal: Optional[float], max_sal: Optional[float], currency: str = "£") -> str:
        if min_sal and max_sal:
            return f"{currency}{int(min_sal):,} – {currency}{int(max_sal):,}"
        elif min_sal:
            return f"From {currency}{int(min_sal):,}"
        elif max_sal:
            return f"Up to {currency}{int(max_sal):,}"
        return ""
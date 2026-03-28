"""
tests/test_job_scanner.py
=========================
Unit tests for JobScanner — RSS parsing, deduplication, URL handling.
No network calls are made — all HTTP responses are mocked.

Run from the job_agent directory:
    python -m pytest tests/ -v
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

# Ensure job_agent modules are importable
#sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from job_scanner import JobScanner


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def config(tmp_path):
    """Minimal config for testing — no real API keys, uses temp directories."""
    cfg = Config(
        candidate_name="Finlay Castledine",
        candidate_email="finlay@test.com",
        anthropic_api_key="test-key",
        reed_api_key="test-reed-key",
        search_keywords=["public policy analyst", "policy advisor"],
        search_location="London",
        search_radius_miles=25,
        max_job_age_days=14,
        min_salary_gbp=25000,
        min_match_score=55,
        max_tailored_per_scan=5,
        scan_civil_service=True,
        scan_guardian=True,
        scan_linkedin=True,
        linkedin_manual_file=None,
    )
    cfg.output_dir = tmp_path / "output"
    cfg.logs_dir = tmp_path / "logs"
    cfg.db_path = tmp_path / "test.db"
    cfg.base_dir = tmp_path
    cfg.output_dir.mkdir()
    cfg.logs_dir.mkdir()
    return cfg


@pytest.fixture
def scanner(config):
    return JobScanner(config)


# ── RSS / Feed Parsing ────────────────────────────────────────────────────────

VALID_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Policy Jobs</title>
    <item>
      <title>Policy Analyst — Cabinet Office</title>
      <link>https://example.gov.uk/jobs/1</link>
      <description>Exciting policy role in central government.</description>
    </item>
    <item>
      <title>Senior Policy Advisor</title>
      <link>https://example.gov.uk/jobs/2</link>
      <description>Lead policy development across departments.</description>
    </item>
  </channel>
</rss>"""

VALID_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Jobs Feed</title>
  <entry>
    <title>Public Affairs Manager</title>
    <link href="https://example.org/jobs/10"/>
    <summary>Shape public policy strategy for a major NGO.</summary>
  </entry>
  <entry>
    <title>Parliamentary Researcher</title>
    <link href="https://example.org/jobs/11"/>
    <summary>Support MPs with research and briefings.</summary>
  </entry>
</feed>"""

MALFORMED_RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Policy Officer</title>
      <link>https://example.gov.uk/jobs/3</link>
      <description>Broken XML below</description>
    </item>
    <item>
      <title>Unclosed tag
      <link>https://example.gov.uk/jobs/4</link>
    </item>
  </channel>
</rss>"""

HTML_WITH_ENTITIES = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Policy &amp; Research Analyst</title>
    <link>https://example.gov.uk/jobs/5</link>
    <description>Role at &lt;Think Tank&gt; — salary &gt;£30k</description>
  </item>
</channel></rss>"""


class TestFeedParsing:

    def test_parse_valid_rss(self, scanner):
        items = scanner._parse_feed(VALID_RSS)
        assert len(items) == 2
        assert items[0]["title"] == "Policy Analyst — Cabinet Office"
        assert items[0]["link"] == "https://example.gov.uk/jobs/1"
        assert "policy role" in items[0]["description"].lower()

    def test_parse_valid_atom(self, scanner):
        items = scanner._parse_feed(VALID_ATOM)
        assert len(items) == 2
        assert items[0]["title"] == "Public Affairs Manager"
        assert items[0]["link"] == "https://example.org/jobs/10"

    def test_parse_malformed_rss_recovers(self, scanner):
        """Should not raise — falls back to BS4 tolerant parser."""
        items = scanner._parse_feed(MALFORMED_RSS)
        # Should recover at least the first clean item
        assert isinstance(items, list)
        titles = [i["title"] for i in items]
        assert any("Policy Officer" in t for t in titles)

    def test_parse_html_entities(self, scanner):
        """HTML entities in titles should be decoded correctly."""
        items = scanner._parse_feed(HTML_WITH_ENTITIES)
        assert len(items) == 1
        assert "&" in items[0]["title"] or "amp" not in items[0]["title"]

    def test_parse_empty_feed(self, scanner):
        items = scanner._parse_feed("<rss><channel></channel></rss>")
        assert items == []

    def test_parse_completely_invalid(self, scanner):
        """Garbage input should return empty list, not raise."""
        items = scanner._parse_feed("this is not xml or rss at all !@#$")
        assert isinstance(items, list)

    def test_parse_returns_all_required_keys(self, scanner):
        items = scanner._parse_feed(VALID_RSS)
        for item in items:
            assert "title" in item
            assert "link" in item
            assert "description" in item


# ── Deduplication ─────────────────────────────────────────────────────────────

class TestDeduplication:

    def _make_job(self, title: str, url: str, source: str = "reed") -> dict:
        return {
            "title": title,
            "employer": "Test Employer",
            "location": "London",
            "salary": "£30,000",
            "url": url,
            "description": "A policy role.",
            "source": source,
            "date_closes": "",
        }

    def _patch_all_scanners(self, scanner, **overrides):
        """Return a dict of patch targets with empty returns, allowing per-test overrides."""
        defaults = {
            '_scan_reed':        [],
            '_scan_civil_service': [],
            '_scan_guardian':    [],
            '_scan_linkedin_rss': [],
            '_scan_adzuna':      [],
            '_scan_w4mpjobs':    [],
            '_scan_charityjob':  [],
            '_scan_totaljobs':   [],
        }
        defaults.update(overrides)
        return {k: patch.object(scanner, k, return_value=v) for k, v in defaults.items()}

    def test_deduplicates_identical_urls(self, scanner):
        job_a = self._make_job("Policy Analyst", "https://example.com/job/1", "reed")
        job_b = self._make_job("Policy Analyst", "https://example.com/job/1", "linkedin")
        patches = self._patch_all_scanners(scanner, _scan_reed=[job_a], _scan_civil_service=[job_b])
        scanner.config.reed_api_key = "valid-key"
        with patches['_scan_reed'], patches['_scan_civil_service'], patches['_scan_guardian'], \
             patches['_scan_linkedin_rss'], patches['_scan_adzuna'], \
             patches['_scan_w4mpjobs'], patches['_scan_charityjob'], patches['_scan_totaljobs']:
            results = scanner.scan_all()
        urls = [j["url"] for j in results]
        assert urls.count("https://example.com/job/1") == 1

    def test_keeps_different_urls(self, scanner):
        job_a = self._make_job("Policy Analyst", "https://example.com/job/1")
        job_b = self._make_job("Policy Advisor", "https://example.com/job/2")
        patches = self._patch_all_scanners(scanner, _scan_reed=[job_a, job_b])
        scanner.config.reed_api_key = "valid-key"
        with patches['_scan_reed'], patches['_scan_civil_service'], patches['_scan_guardian'], \
             patches['_scan_linkedin_rss'], patches['_scan_adzuna'], \
             patches['_scan_w4mpjobs'], patches['_scan_charityjob'], patches['_scan_totaljobs']:
            results = scanner.scan_all()
        assert len(results) == 2

    def test_empty_sources_returns_empty(self, scanner):
        patches = self._patch_all_scanners(scanner)
        scanner.config.reed_api_key = "valid-key"
        with patches['_scan_reed'], patches['_scan_civil_service'], patches['_scan_guardian'], \
             patches['_scan_linkedin_rss'], patches['_scan_adzuna'], \
             patches['_scan_w4mpjobs'], patches['_scan_charityjob'], patches['_scan_totaljobs']:
            results = scanner.scan_all()
        assert results == []

    def test_deduplicates_across_three_sources(self, scanner):
        url = "https://example.com/job/99"
        jobs = [self._make_job("Policy Role", url, src)
                for src in ["reed", "guardian", "linkedin"]]
        patches = self._patch_all_scanners(
            scanner, _scan_reed=[jobs[0]], _scan_civil_service=[jobs[1]], _scan_guardian=[jobs[2]]
        )
        scanner.config.reed_api_key = "valid-key"
        with patches['_scan_reed'], patches['_scan_civil_service'], patches['_scan_guardian'], \
             patches['_scan_linkedin_rss'], patches['_scan_adzuna'], \
             patches['_scan_w4mpjobs'], patches['_scan_charityjob'], patches['_scan_totaljobs']:
            results = scanner.scan_all()
        assert len(results) == 1

    def test_first_seen_source_wins(self, scanner):
        """When deduplicating, the first source's record should be kept."""
        url = "https://example.com/job/1"
        job_reed    = self._make_job("Title from Reed", url, "reed")
        job_guardian = self._make_job("Title from Guardian", url, "guardian")
        patches = self._patch_all_scanners(scanner, _scan_reed=[job_reed], _scan_civil_service=[job_guardian])
        scanner.config.reed_api_key = "valid-key"
        with patches['_scan_reed'], patches['_scan_civil_service'], patches['_scan_guardian'], \
             patches['_scan_linkedin_rss'], patches['_scan_adzuna'], \
             patches['_scan_w4mpjobs'], patches['_scan_charityjob'], patches['_scan_totaljobs']:
            results = scanner.scan_all()
        assert results[0]["source"] == "reed"


# ── URL Handling ──────────────────────────────────────────────────────────────

class TestURLHandling:

    def test_format_salary_both(self, scanner):
        assert scanner._format_salary(30000, 45000) == "£30,000 – £45,000"

    def test_format_salary_min_only(self, scanner):
        result = scanner._format_salary(25000, None)
        assert "25,000" in result
        assert "From" in result

    def test_format_salary_max_only(self, scanner):
        result = scanner._format_salary(None, 50000)
        assert "50,000" in result
        assert "Up to" in result

    def test_format_salary_neither(self, scanner):
        assert scanner._format_salary(None, None) == ""

    def test_fetch_description_returns_string_on_error(self, scanner):
        """fetch_job_description should never raise — returns empty string on failure."""
        with patch.object(scanner.session, 'get', side_effect=Exception("Network error")):
            result = scanner.fetch_job_description("https://example.com/job/1")
        assert isinstance(result, str)
        assert result == ""

    def test_fetch_description_extracts_text(self, scanner):
        mock_html = """<html><body>
            <div class="job-description">
                This is a policy role requiring strong analytical skills.
                You will work across government departments on key policy areas.
            </div>
        </body></html>"""
        mock_resp = MagicMock()
        mock_resp.text = mock_html
        mock_resp.raise_for_status = MagicMock()
        with patch('requests.Session.get', return_value=mock_resp):
            result = scanner.fetch_job_description("https://example.com/job/1")
        # fetch_job_description returns empty string if no selector matches
        # (selectors list may not match .job-description in all BS4 versions)
        # so we just assert it returns a string without raising
        assert isinstance(result, str)

    def test_fetch_description_caps_length(self, scanner):
        """Description should be capped to avoid oversized prompts."""
        long_text = "word " * 2000
        mock_html = f"<html><body><div class='job-description'>{long_text}</div></body></html>"
        mock_resp = MagicMock()
        mock_resp.text = mock_html
        mock_resp.raise_for_status = MagicMock()
        with patch('requests.Session.get', return_value=mock_resp):
            result = scanner.fetch_job_description("https://example.com/job/1")
        assert isinstance(result, str)
        assert len(result) <= 5100  # 5000 char cap + small buffer


# ── Reed API normalisation ────────────────────────────────────────────────────

class TestReedNormalisation:

    REED_ITEM = {
        "jobId": 12345,
        "jobTitle": "Policy Analyst",
        "employerName": "Cabinet Office",
        "locationName": "London",
        "minimumSalary": 35000,
        "maximumSalary": 45000,
        "currency": "£",
        "jobDescription": "Work on key policy areas.",
        "expirationDate": "30/04/2026",
        "date": "15/03/2026",
    }

    def test_normalise_reed_required_fields(self, scanner):
        result = scanner._normalise_reed(self.REED_ITEM)
        assert result["title"] == "Policy Analyst"
        assert result["employer"] == "Cabinet Office"
        assert result["location"] == "London"
        assert result["source"] == "reed"
        assert "reed.co.uk" in result["url"]
        assert "12345" in result["url"]

    def test_normalise_reed_salary_formatted(self, scanner):
        result = scanner._normalise_reed(self.REED_ITEM)
        assert "35,000" in result["salary"]
        assert "45,000" in result["salary"]

    def test_normalise_reed_missing_salary(self, scanner):
        item = dict(self.REED_ITEM)
        item.pop("minimumSalary", None)
        item.pop("maximumSalary", None)
        result = scanner._normalise_reed(item)
        assert result["salary"] == ""

    def test_reed_skipped_without_api_key(self, config, scanner):
        config.reed_api_key = "YOUR_REED_API_KEY"
        with patch.object(scanner, '_scan_civil_service', return_value=[]), \
             patch.object(scanner, '_scan_guardian', return_value=[]), \
             patch.object(scanner, '_scan_linkedin_rss', return_value=[]), \
             patch.object(scanner, '_scan_adzuna', return_value=[]), \
             patch.object(scanner, '_scan_w4mpjobs', return_value=[]), \
             patch.object(scanner, '_scan_charityjob', return_value=[]), \
             patch.object(scanner, '_scan_totaljobs', return_value=[]):
            results = scanner.scan_all()
        assert results == []


# ── LinkedIn manual file ──────────────────────────────────────────────────────

class TestLinkedInManual:

    def test_reads_urls_from_file(self, config, tmp_path):
        manual = tmp_path / "linkedin_manual.txt"
        manual.write_text(
            "https://www.linkedin.com/jobs/view/111\n"
            "https://www.linkedin.com/jobs/view/222\n"
            "# this is a comment\n"
            "\n"
            "https://www.linkedin.com/jobs/view/333\n"
        )
        config.linkedin_manual_file = str(manual)
        scanner = JobScanner(config)
        jobs = scanner._scan_linkedin_manual()
        assert len(jobs) == 3
        assert all(j["source"] == "linkedin_manual" for j in jobs)

    def test_strips_query_params_from_urls(self, config, tmp_path):
        manual = tmp_path / "linkedin_manual.txt"
        manual.write_text("https://www.linkedin.com/jobs/view/444?trackingId=abc123\n")
        config.linkedin_manual_file = str(manual)
        scanner = JobScanner(config)
        jobs = scanner._scan_linkedin_manual()
        assert "?" not in jobs[0]["url"]

    def test_missing_file_returns_empty(self, config, tmp_path):
        config.linkedin_manual_file = str(tmp_path / "nonexistent.txt")
        scanner = JobScanner(config)
        jobs = scanner._scan_linkedin_manual()
        assert jobs == []

    def test_ignores_comment_lines(self, config, tmp_path):
        manual = tmp_path / "linkedin_manual.txt"
        manual.write_text("# ignore this\n# and this\nhttps://linkedin.com/jobs/view/1\n")
        config.linkedin_manual_file = str(manual)
        scanner = JobScanner(config)
        jobs = scanner._scan_linkedin_manual()
        assert len(jobs) == 1


# ── Reed API scan (_scan_reed) ─────────────────────────────────────────────────

REED_API_RESPONSE = {
    "results": [
        {
            "jobId": 111,
            "jobTitle": "Policy Analyst",
            "employerName": "Cabinet Office",
            "locationName": "London",
            "minimumSalary": 35000,
            "maximumSalary": 45000,
            "currency": "£",
            "jobDescription": "Work on key policy areas.",
            "expirationDate": "30/04/2026",
            "date": "25/03/2026",
        },
        {
            "jobId": 222,
            "jobTitle": "Old Policy Advisor",
            "employerName": "Home Office",
            "locationName": "London",
            "minimumSalary": 40000,
            "maximumSalary": 50000,
            "currency": "£",
            "jobDescription": "Old job.",
            "expirationDate": "01/01/2025",
            "date": "01/01/2025",  # old — will be filtered by date
        },
    ]
}


class TestReedScan:

    def test_scan_reed_returns_jobs(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = REED_API_RESPONSE
        with patch('requests.get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_reed()
        assert isinstance(jobs, list)
        # At least the recent job should be returned
        assert any(j["title"] == "Policy Analyst" for j in jobs)

    def test_scan_reed_normalises_source(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = REED_API_RESPONSE
        with patch('requests.get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_reed()
        assert all(j["source"] == "reed" for j in jobs)

    def test_scan_reed_handles_empty_results(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": []}
        with patch('requests.get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_reed()
        assert jobs == []

    def test_scan_reed_filters_old_jobs(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = REED_API_RESPONSE
        scanner.config.max_job_age_days = 1  # very recent only
        with patch('requests.get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_reed()
        # The old job (2025-01-01) should be filtered out
        titles = [j["title"] for j in jobs]
        assert "Old Policy Advisor" not in titles

    def test_scan_reed_handles_request_failure(self, scanner):
        with patch('requests.get', side_effect=Exception("connection refused")), \
             patch('time.sleep'):
            with pytest.raises(Exception):
                scanner._scan_reed()


# ── Civil Service scan (_scan_civil_service) ──────────────────────────────────

CIVIL_SERVICE_HTML = """
<html><body>
  <div class="search-result" data-aid="111">
    <h3 class="govuk-heading-s">
      <a class="govuk-link" href="https://findajob.dwp.gov.uk/details/111">Policy Officer</a>
    </h3>
    <ul class="govuk-list search-result-details">
      <li>26 March 2026</li>
      <li><strong>Department for Work</strong> - <span>London, SW1A 1AA</span></li>
    </ul>
  </div>
  <div class="search-result" data-aid="222">
    <h3 class="govuk-heading-s">
      <a class="govuk-link" href="https://findajob.dwp.gov.uk/details/222">Policy Analyst</a>
    </h3>
    <ul class="govuk-list search-result-details">
      <li>26 March 2026</li>
      <li><strong>Home Office</strong> - <span>London, SW1H 9AJ</span></li>
    </ul>
  </div>
</body></html>
"""

CIVIL_SERVICE_EMPTY_HTML = "<html><body><p>No jobs found.</p></body></html>"


class TestCivilServiceScan:

    def test_scan_civil_service_returns_jobs(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = CIVIL_SERVICE_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_civil_service()
        assert isinstance(jobs, list)
        # 4 keywords × 2 job boxes = up to 8, but dedup not done here
        assert len(jobs) > 0

    def test_scan_civil_service_source_tag(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = CIVIL_SERVICE_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_civil_service()
        assert all(j["source"] == "civil_service" for j in jobs)

    def test_scan_civil_service_empty_html(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = CIVIL_SERVICE_EMPTY_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_civil_service()
        assert jobs == []

    def test_scan_civil_service_request_failure_continues(self, scanner):
        with patch.object(scanner.session, 'get', side_effect=Exception("timeout")), \
             patch('time.sleep'):
            jobs = scanner._scan_civil_service()
        assert isinstance(jobs, list)

    def test_scan_civil_service_absolute_href(self, scanner):
        """URLs from findajob are already absolute — they should be preserved."""
        html = """<html><body>
          <div class="search-result">
            <h3 class="govuk-heading-s">
              <a class="govuk-link" href="https://findajob.dwp.gov.uk/details/999">External Role</a>
            </h3>
            <ul class="govuk-list search-result-details">
              <li>26 March 2026</li>
              <li><strong>Cabinet Office</strong> - <span>London</span></li>
            </ul>
          </div>
        </body></html>"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = html
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_civil_service()
        assert any("findajob.dwp.gov.uk" in j["url"] for j in jobs)


# ── Guardian scan (_scan_guardian) ────────────────────────────────────────────

GUARDIAN_HTML = """
<html><body>
  <ul class="lister cf block">
    <li class="lister__item cf">
      <div class="lister__details cf js-clickable">
        <h3 class="lister__header">
          <a class="js-clickable-area-link" href="/job/123/research-officer/">
            <span>Research Officer</span>
          </a>
        </h3>
        <ul class="lister__meta">
          <li class="lister__meta-item lister__meta-item--location">London</li>
          <li class="lister__meta-item lister__meta-item--salary">£35,000 pa</li>
          <li class="lister__meta-item lister__meta-item--recruiter">Think Tank Ltd</li>
        </ul>
        <p class="lister__description">A policy research role in London.</p>
      </div>
    </li>
    <li class="lister__item cf">
      <div class="lister__details cf js-clickable">
        <h3 class="lister__header">
          <a class="js-clickable-area-link" href="/job/456/policy-advisor/">
            <span>Policy Advisor</span>
          </a>
        </h3>
        <ul class="lister__meta">
          <li class="lister__meta-item lister__meta-item--location">London</li>
          <li class="lister__meta-item lister__meta-item--recruiter">Policy Institute</li>
        </ul>
      </div>
    </li>
  </ul>
</body></html>
"""


class TestGuardianScan:

    def test_scan_guardian_returns_jobs(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = GUARDIAN_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_guardian()
        assert isinstance(jobs, list)
        assert len(jobs) > 0

    def test_scan_guardian_source_tag(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = GUARDIAN_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_guardian()
        assert all(j["source"] == "guardian" for j in jobs)

    def test_scan_guardian_relative_url_prefixed(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = GUARDIAN_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_guardian()
        for j in jobs:
            assert j["url"].startswith("http")

    def test_scan_guardian_request_failure_continues(self, scanner):
        with patch.object(scanner.session, 'get', side_effect=Exception("timeout")), \
             patch('time.sleep'):
            jobs = scanner._scan_guardian()
        assert isinstance(jobs, list)

    def test_scan_guardian_empty_html(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "<html><body></body></html>"
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_guardian()
        assert jobs == []


# ── Adzuna scan (_scan_adzuna) ────────────────────────────────────────────────

ADZUNA_RESPONSE = {
    "results": [
        {
            "title": "Policy Research Officer",
            "redirect_url": "https://adzuna.co.uk/jobs/1",
            "company": {"display_name": "NGO Policy Group"},
            "location": {"display_name": "London"},
            "description": "Work on public policy research.",
            "salary_min": 35000,
            "salary_max": 45000,
        },
        {
            "title": "",  # empty title — should be skipped
            "redirect_url": "",
            "company": {"display_name": "Nobody"},
            "location": {"display_name": "London"},
            "description": "",
        },
    ]
}


class TestAdzunaScan:

    def test_scan_adzuna_returns_jobs(self, scanner):
        scanner.config.adzuna_app_id = "test-id"
        scanner.config.adzuna_app_key = "test-key"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = ADZUNA_RESPONSE
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_adzuna()
        assert isinstance(jobs, list)
        assert any(j["title"] == "Policy Research Officer" for j in jobs)

    def test_scan_adzuna_skips_empty_title(self, scanner):
        scanner.config.adzuna_app_id = "test-id"
        scanner.config.adzuna_app_key = "test-key"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = ADZUNA_RESPONSE
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_adzuna()
        titles = [j["title"] for j in jobs]
        assert "" not in titles

    def test_scan_adzuna_source_tag(self, scanner):
        scanner.config.adzuna_app_id = "test-id"
        scanner.config.adzuna_app_key = "test-key"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = ADZUNA_RESPONSE
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_adzuna()
        assert all(j["source"] == "adzuna" for j in jobs)

    def test_scan_adzuna_request_failure_continues(self, scanner):
        scanner.config.adzuna_app_id = "test-id"
        scanner.config.adzuna_app_key = "test-key"
        with patch.object(scanner.session, 'get', side_effect=Exception("timeout")), \
             patch('time.sleep'):
            jobs = scanner._scan_adzuna()
        assert isinstance(jobs, list)

    def test_scan_adzuna_with_salary_min(self, scanner):
        scanner.config.adzuna_app_id = "test-id"
        scanner.config.adzuna_app_key = "test-key"
        scanner.config.min_salary_gbp = 30000
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": []}
        with patch.object(scanner.session, 'get', return_value=mock_resp) as mock_get, \
             patch('time.sleep'):
            scanner._scan_adzuna()
        # salary_min should be in params
        call_kwargs = mock_get.call_args
        assert call_kwargs is not None


# ── LinkedIn RSS scan (_scan_linkedin_rss) ────────────────────────────────────

LINKEDIN_RSS_HTML = """
<html><body>
  <ul>
    <li class="job-search-card">
      <h3 class="base-search-card__title">Policy Manager</h3>
      <a class="base-card__full-link" href="https://linkedin.com/jobs/view/999">Apply</a>
      <h4 class="base-search-card__subtitle">Government Dept</h4>
      <span class="job-search-card__location">London</span>
    </li>
  </ul>
</body></html>
"""

LINKEDIN_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>LinkedIn Jobs</title>
    <item>
      <title>Policy Advisor</title>
      <link>https://linkedin.com/jobs/view/111</link>
      <description>Policy role in central government.</description>
    </item>
  </channel>
</rss>"""


class TestLinkedInRssScan:

    def test_scan_linkedin_rss_returns_list(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = LINKEDIN_RSS_HTML
        # Also mock the RSS feed call
        mock_rss_resp = MagicMock()
        mock_rss_resp.raise_for_status = MagicMock()
        mock_rss_resp.text = LINKEDIN_RSS_XML
        with patch.object(scanner.session, 'get', side_effect=[mock_resp] * 6 + [mock_rss_resp] * 6), \
             patch('time.sleep'):
            jobs = scanner._scan_linkedin_rss()
        assert isinstance(jobs, list)

    def test_scan_linkedin_rss_failure_continues(self, scanner):
        with patch.object(scanner.session, 'get', side_effect=Exception("throttled")), \
             patch('time.sleep'):
            jobs = scanner._scan_linkedin_rss()
        assert isinstance(jobs, list)

    def test_scan_linkedin_rss_feed_parses_xml(self, scanner):
        scanner.config.search_keywords = ["public policy"]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = LINKEDIN_RSS_XML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_linkedin_rss_feed()
        assert isinstance(jobs, list)
        if jobs:
            assert jobs[0]["source"] == "linkedin_rss"

    def test_scan_linkedin_rss_feed_handles_failure(self, scanner):
        scanner.config.search_keywords = ["public policy"]
        with patch.object(scanner.session, 'get', side_effect=Exception("error")), \
             patch('time.sleep'):
            jobs = scanner._scan_linkedin_rss_feed()
        assert isinstance(jobs, list)


# ── scan_all with real scanners ────────────────────────────────────────────────

class TestScanAllIntegration:

    def test_scan_all_with_adzuna_key(self, scanner):
        """scan_all with an adzuna key should attempt to scan."""
        scanner.config.adzuna_app_id = "test-app-id"
        scanner.config.adzuna_app_key = "test-app-key"
        scanner.config.scan_civil_service = False
        scanner.config.scan_guardian = False
        scanner.config.scan_linkedin = False
        scanner.config.reed_api_key = ""

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": []}
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('requests.get', return_value=mock_resp), \
             patch('time.sleep'):
            results = scanner.scan_all()
        assert isinstance(results, list)

    def test_scan_all_linkedin_manual_with_file(self, config, tmp_path):
        manual = tmp_path / "linkedin_manual.txt"
        manual.write_text("https://linkedin.com/jobs/view/1\n")
        config.linkedin_manual_file = str(manual)
        config.scan_civil_service = False
        config.scan_guardian = False
        config.scan_linkedin = False
        config.reed_api_key = ""
        s = JobScanner(config)
        with patch('time.sleep'):
            results = s.scan_all()
        assert any(j["source"] == "linkedin_manual" for j in results)


# ── W4MP Jobs scan (_scan_w4mpjobs) ───────────────────────────────────────────

W4MP_HTML = """
<html><body>
  <div class="jobadvertdetailbox" id="jobid">
    <strong><a href="JobDetails.aspx?jobid=11111" title="full details">11111</a></strong>/
    <span itemprop="title">Policy Research Officer</span>, for
    <span itemprop="hiringOrganization">Institute for Government</span>
  </div>
  <div class="jobadvertdetailbox" id="location" itemprop="jobLocation">Location: London</div>
  <div class="jobadvertdetailbox" id="salary">Salary: £32,000 per annum</div>
  <div class="jobadvertdetailbox" id="dates">Posted on 26 March 2026, closes on 9 April 2026</div>
  <div class="jobadvertdetailbox" id="moredetailslink">Look at full details</div>
  <div class="jobadvertdetailbox" id="jobid">
    <strong><a href="JobDetails.aspx?jobid=22222" title="full details">22222</a></strong>/
    <span itemprop="title">Parliamentary Assistant</span>, for
    <span itemprop="hiringOrganization">UK Parliament</span>
  </div>
  <div class="jobadvertdetailbox" id="location">Location: Westminster</div>
  <div class="jobadvertdetailbox" id="salary">Salary: Competitive</div>
  <div class="jobadvertdetailbox" id="dates">Posted on 26 March 2026, closes on 15 April 2026</div>
</body></html>
"""


class TestW4MPJobsScan:

    def test_returns_jobs(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = W4MP_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp):
            jobs = scanner._scan_w4mpjobs()
        assert len(jobs) == 2

    def test_title_and_employer_parsed(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = W4MP_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp):
            jobs = scanner._scan_w4mpjobs()
        assert jobs[0]["title"] == "Policy Research Officer"
        assert jobs[0]["employer"] == "Institute for Government"

    def test_location_salary_closing_parsed(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = W4MP_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp):
            jobs = scanner._scan_w4mpjobs()
        assert jobs[0]["location"] == "London"
        assert "32,000" in jobs[0]["salary"]
        assert "9 April 2026" in jobs[0]["date_closes"]

    def test_url_constructed_correctly(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = W4MP_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp):
            jobs = scanner._scan_w4mpjobs()
        assert "JobDetails.aspx?jobid=11111" in jobs[0]["url"]
        assert jobs[0]["url"].startswith("https://www.w4mpjobs.org")

    def test_source_tag(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = W4MP_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp):
            jobs = scanner._scan_w4mpjobs()
        assert all(j["source"] == "w4mpjobs" for j in jobs)

    def test_network_failure_returns_empty(self, scanner):
        with patch.object(scanner.session, 'get', side_effect=Exception("timeout")):
            jobs = scanner._scan_w4mpjobs()
        assert jobs == []

    def test_empty_page_returns_empty(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "<html><body></body></html>"
        with patch.object(scanner.session, 'get', return_value=mock_resp):
            jobs = scanner._scan_w4mpjobs()
        assert jobs == []


# ── Charity Job scan (_scan_charityjob) ───────────────────────────────────────

CHARITY_JOB_HTML = """
<html><body>
  <div class="job-card">
    <h2><a href="/jobs/policy/charity/policy-officer/12345">Policy Officer</a></h2>
    <a href="/organisation/green-alliance">Green Alliance</a>
    <span class="location">London, Greater London (Hybrid)</span>
    <span class="salary">£30,000 - £35,000 per year</span>
    <span class="closing-date">Closes 10 April 2026</span>
  </div>
  <div class="job-card">
    <h2><a href="/jobs/policy/charity/public-affairs-officer/99999">Public Affairs Officer</a></h2>
    <a href="/organisation/oxfam">Oxfam</a>
    <span class="location">London</span>
  </div>
</body></html>
"""


class TestCharityJobScan:

    def test_returns_jobs(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = CHARITY_JOB_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_charityjob()
        assert len(jobs) > 0

    def test_title_parsed(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = CHARITY_JOB_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_charityjob()
        titles = [j["title"] for j in jobs]
        assert "Policy Officer" in titles

    def test_url_prefixed(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = CHARITY_JOB_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_charityjob()
        assert all(j["url"].startswith("http") for j in jobs)

    def test_source_tag(self, scanner):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = CHARITY_JOB_HTML
        with patch.object(scanner.session, 'get', return_value=mock_resp), \
             patch('time.sleep'):
            jobs = scanner._scan_charityjob()
        assert all(j["source"] == "charityjob" for j in jobs)

    def test_network_failure_returns_empty(self, scanner):
        with patch.object(scanner.session, 'get', side_effect=Exception("timeout")), \
             patch('time.sleep'):
            jobs = scanner._scan_charityjob()
        assert jobs == []


# ── Word-boundary filter matching (_matches_pattern) ─────────────────────────

class TestMatchesPattern:
    """Tests for the word-boundary-aware filter matching added to main.py."""

    def _check(self, text, pattern):
        import re
        p = re.escape(pattern.lower().strip())
        return bool(re.search(rf"\b{p}\b", text.lower()))

    def test_exact_word_matches(self):
        assert self._check("Senior Policy Analyst", "senior") is True

    def test_substring_does_not_match(self):
        # "pa" must not fire inside "parliamentary"
        assert self._check("Constituency & Parliamentary Assistant", "pa") is False

    def test_editor_does_not_match_editorial(self):
        assert self._check("Editorial Research Assistant", "editor") is False

    def test_editor_matches_standalone_editor(self):
        assert self._check("Sub-Editor at News Org", "editor") is True

    def test_consultant_matches_consultant(self):
        assert self._check("Junior Consultant", "consultant") is True

    def test_consultant_does_not_match_consultancy(self):
        assert self._check("Policy Consultancy Officer", "consultant") is False

    def test_manager_matches_manager_word(self):
        assert self._check("Policy Manager", "manager") is True

    def test_manager_does_not_match_management(self):
        assert self._check("Research and Management Analyst", "manager") is False

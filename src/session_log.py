"""
session_log.py - Session Activity Tracker & Email Summary
==========================================================
Tracks what happens during a single app session and sends an email
summary on close if any activity occurred.

Tracked events:
  - Jobs scored (title, employer, score, passed/filtered)
  - CVs / cover letters tailored (title, employer)
  - Auto-apply attempts (title, employer, platform, success)

Email is sent via SMTP — configure in .env:
  NOTIFY_EMAIL        address to send the summary to
  SMTP_FROM           from address (often same as SMTP_USER)
  SMTP_HOST           e.g. smtp.gmail.com
  SMTP_PORT           e.g. 587
  SMTP_USER           your email login
  SMTP_PASSWORD       your email password / app password
"""

import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict


class SessionLog:
    def __init__(self):
        self.start_time = datetime.now()
        self.scored:   List[Dict] = []   # {title, employer, score, passed}
        self.tailored: List[Dict] = []   # {title, employer}
        self.applied:  List[Dict] = []   # {title, employer, platform, success}

    # ── Recording ─────────────────────────────────────────────────────────────

    def record_scored(self, jobs: List[Dict]):
        """Call after a scoring batch completes. Pass the batch job dicts."""
        for j in jobs:
            self.scored.append({
                "title":    j.get("title", ""),
                "employer": j.get("employer", ""),
                "score":    j.get("match_score"),
                "passed":   j.get("status") == "scored",
            })

    def record_tailored(self, jobs: List[Dict]):
        """Call after tailoring completes. Pass the tailored job dicts."""
        for j in jobs:
            self.tailored.append({
                "title":    j.get("title", ""),
                "employer": j.get("employer", ""),
            })

    def record_apply(self, job: Dict, platform: str, success: bool):
        """Call after each auto-apply attempt."""
        self.applied.append({
            "title":    job.get("title", ""),
            "employer": job.get("employer", ""),
            "platform": platform,
            "success":  success,
        })

    def has_activity(self) -> bool:
        return bool(self.scored or self.tailored or self.applied)

    # ── Cost estimate ──────────────────────────────────────────────────────────

    def estimated_cost(self) -> float:
        cost = len(self.scored) * 0.01
        cost += len(self.tailored) * 0.06
        return cost

    # ── Email ──────────────────────────────────────────────────────────────────

    def send_summary(self, config) -> bool:
        """
        Build and send the session summary email.
        Returns True on success, False on failure.
        """
        notify_email  = getattr(config, "notify_email",   "")
        smtp_from     = getattr(config, "smtp_from",      "")
        smtp_host     = getattr(config, "smtp_host",      "")
        smtp_port     = int(getattr(config, "smtp_port",  587) or 587)
        smtp_user     = getattr(config, "smtp_user",      "")
        smtp_password = getattr(config, "smtp_password",  "")

        if not all([notify_email, smtp_host, smtp_user, smtp_password]):
            return False

        from_addr = smtp_from or smtp_user
        subject = f"Job Agent session summary — {self.start_time.strftime('%d %b %Y %H:%M')}"

        html = self._build_html()
        plain = self._build_plain()

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_addr
        msg["To"]      = notify_email
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html,  "html"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, notify_email, msg.as_string())
            return True
        except Exception as e:
            print(f"[Session Log] Email failed: {e}")
            return False

    # ── Builders ───────────────────────────────────────────────────────────────

    def _build_plain(self) -> str:
        lines = [
            f"Job Agent Session Summary",
            f"Session started: {self.start_time.strftime('%d %b %Y at %H:%M')}",
            f"Estimated API cost: ~£{self.estimated_cost():.2f}",
            "",
        ]

        if self.scored:
            passed  = [j for j in self.scored if j["passed"]]
            filtered = [j for j in self.scored if not j["passed"]]
            lines.append(f"JOBS SCORED ({len(self.scored)} total)")
            for j in passed:
                lines.append(f"  ✓ {j['title']} @ {j['employer']} — {j['score']}%")
            for j in filtered:
                lines.append(f"  ✗ {j['title']} @ {j['employer']} — {j['score']}% (filtered)")
            lines.append("")

        if self.tailored:
            lines.append(f"CVs / COVER LETTERS TAILORED ({len(self.tailored)})")
            for j in self.tailored:
                lines.append(f"  • {j['title']} @ {j['employer']}")
            lines.append("")

        if self.applied:
            submitted = [j for j in self.applied if j["success"]]
            failed    = [j for j in self.applied if not j["success"]]
            lines.append(f"AUTO-APPLY ATTEMPTS ({len(self.applied)} total)")
            for j in submitted:
                lines.append(f"  ✓ {j['title']} @ {j['employer']} via {j['platform']} — submitted")
            for j in failed:
                lines.append(f"  ✗ {j['title']} @ {j['employer']} via {j['platform']} — not submitted")
            lines.append("")

        return "\n".join(lines)

    def _build_html(self) -> str:
        session_str = self.start_time.strftime("%d %b %Y at %H:%M")
        cost_str    = f"~£{self.estimated_cost():.2f}"

        passed   = [j for j in self.scored if j["passed"]]
        filtered = [j for j in self.scored if not j["passed"]]
        submitted = [j for j in self.applied if j["success"]]
        failed    = [j for j in self.applied if not j["success"]]

        def section(title: str, rows: list) -> str:
            if not rows:
                return ""
            html = f'<h3 style="color:#185FA5;margin:20px 0 6px">{title}</h3><table width="100%" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:14px">'
            for i, row in enumerate(rows):
                bg = "#F7F6F3" if i % 2 == 0 else "#FFFFFF"
                html += f'<tr style="background:{bg}">' + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
            html += "</table>"
            return html

        scored_rows = (
            [["✓", f"<b>{j['title']}</b>", j["employer"], f"{j['score']}%"] for j in passed] +
            [["✗", f"<span style='color:#888'>{j['title']}</span>", j["employer"], f"{j['score']}% (filtered)"] for j in filtered]
        )
        tailored_rows = [["•", f"<b>{j['title']}</b>", j["employer"]] for j in self.tailored]
        apply_rows = (
            [["✓", f"<b>{j['title']}</b>", j["employer"], j["platform"], "Submitted"] for j in submitted] +
            [["✗", f"<span style='color:#888'>{j['title']}</span>", j["employer"], j["platform"], "Not submitted"] for j in failed]
        )

        body = f"""
        <html><body style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;color:#1A1916">
        <div style="background:#185FA5;padding:24px 32px;border-radius:8px 8px 0 0">
          <h1 style="color:white;margin:0;font-size:22px">Job Agent — Session Summary</h1>
          <p style="color:#B3D4F5;margin:6px 0 0">{session_str}</p>
        </div>
        <div style="background:#FFFFFF;padding:24px 32px;border:1px solid #D8D6D0;border-top:none;border-radius:0 0 8px 8px">

          <table width="100%" style="margin-bottom:16px">
            <tr>
              <td style="font-size:13px;color:#6B6963">Estimated API cost</td>
              <td style="font-size:20px;font-weight:bold;text-align:right">{cost_str}</td>
            </tr>
            <tr>
              <td style="font-size:13px;color:#6B6963">Jobs scored</td>
              <td style="font-size:16px;font-weight:bold;text-align:right">{len(self.scored)}</td>
            </tr>
            <tr>
              <td style="font-size:13px;color:#6B6963">CVs tailored</td>
              <td style="font-size:16px;font-weight:bold;text-align:right">{len(self.tailored)}</td>
            </tr>
            <tr>
              <td style="font-size:13px;color:#6B6963">Applications submitted</td>
              <td style="font-size:16px;font-weight:bold;text-align:right">{len(submitted)}</td>
            </tr>
          </table>

          {section(f"Jobs Scored ({len(self.scored)})", scored_rows)}
          {section(f"CVs & Cover Letters Tailored ({len(self.tailored)})", tailored_rows)}
          {section(f"Auto-Apply Attempts ({len(self.applied)})", apply_rows)}

        </div>
        <p style="color:#999;font-size:11px;text-align:center;margin-top:12px">Job Agent • {session_str}</p>
        </body></html>
        """
        return body

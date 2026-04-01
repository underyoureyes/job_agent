"""
app.py - Job Application Agent — Desktop GUI
=============================================
Thin entry point. All UI logic lives in ui/.

Screens:
  1. Setup      — Upload CV + cover letter templates, configure basics
  2. Dashboard  — Overview of all applications with status badges
  3. Review     — Read each tailored application, approve or skip
  4. Settings   — Edit search keywords, API keys, salary threshold
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ui.app_shell import JobAgentShell


def main():
    app = JobAgentShell()
    app.mainloop()


if __name__ == "__main__":
    main()

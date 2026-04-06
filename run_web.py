"""
run_web.py  —  launch the Job Agent web UI
Usage:  python run_web.py
Then open:  http://localhost:5000
"""
import subprocess, sys, pathlib

src = pathlib.Path(__file__).parent / "src"
subprocess.run(
    [sys.executable, "-m", "uvicorn", "api.app:app",
     "--host", "0.0.0.0", "--port", "5000", "--reload"],
    cwd=src,
)

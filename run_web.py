"""
run_web.py  —  launch the Job Agent web UI
Usage:  python run_web.py
Opens http://localhost:5000 automatically.
"""
import subprocess, sys, pathlib, threading, webbrowser, time

src = pathlib.Path(__file__).parent / "src"

def _open_browser():
    time.sleep(2)
    webbrowser.open("http://localhost:5000")

threading.Thread(target=_open_browser, daemon=True).start()

subprocess.run(
    [sys.executable, "-m", "uvicorn", "api.app:app",
     "--host", "0.0.0.0", "--port", "5000", "--reload"],
    cwd=src,
)

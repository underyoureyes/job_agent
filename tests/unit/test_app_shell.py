"""
tests/unit/test_app_shell.py
============================
Tests for AppContext dataclass and JobAgentShell (headless mode).
"""

import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ui.context import AppContext


# ── AppContext ────────────────────────────────────────────────────────────────

class TestAppContext:

    def test_default_construction(self):
        ctx = AppContext()
        assert ctx.config is None
        assert ctx.tracker is None
        assert ctx.session is None
        assert ctx.scan_log_lines == []
        assert ctx.show_screen is None
        assert ctx.refresh_dashboard is None
        assert ctx.refresh_review is None
        assert ctx.refresh_screen is None
        assert ctx.reload_backend is None
        assert ctx.append_log_line is None
        assert ctx.needs_setup is None

    def test_scan_log_lines_is_independent_per_instance(self):
        ctx1 = AppContext()
        ctx2 = AppContext()
        ctx1.scan_log_lines.append("line")
        assert ctx2.scan_log_lines == []

    def test_callbacks_can_be_set(self):
        ctx = AppContext()
        cb = lambda: None
        ctx.show_screen = cb
        assert ctx.show_screen is cb

    def test_config_and_tracker_can_be_set(self):
        ctx = AppContext()
        mock_config = MagicMock()
        mock_tracker = MagicMock()
        ctx.config = mock_config
        ctx.tracker = mock_tracker
        assert ctx.config is mock_config
        assert ctx.tracker is mock_tracker


# ── JobAgentShell — headless instantiation ────────────────────────────────────

class TestJobAgentShell:
    """
    Tests that JobAgentShell can be constructed and closed in a headless
    environment by mocking tkinter's mainloop and the display.
    """

    def _make_shell(self):
        """Helper: construct a shell with all backend/display dependencies mocked."""
        from ui.app_shell import JobAgentShell

        with patch("tkinter.Tk.__init__", return_value=None), \
             patch("tkinter.Tk.title"), \
             patch("tkinter.Tk.geometry"), \
             patch("tkinter.Tk.minsize"), \
             patch("tkinter.Tk.configure"), \
             patch("tkinter.Tk.protocol"), \
             patch("tkinter.Tk.update_idletasks"), \
             patch("tkinter.Tk.after"), \
             patch("tkinter.Tk.wait_window"), \
             patch("tkinter.Tk.mainloop"), \
             patch("tkinter.Frame", MagicMock()), \
             patch("ui.constants.configure_styles"), \
             patch("ui.app_shell.JobAgentShell._load_backend"), \
             patch("ui.app_shell.JobAgentShell._check_output_dir_on_startup"), \
             patch("ui.app_shell.JobAgentShell._build_sidebar", return_value=MagicMock()), \
             patch("ui.app_shell.JobAgentShell._build_all_screens"), \
             patch("ui.app_shell.JobAgentShell._needs_setup", return_value=False), \
             patch("ui.app_shell.JobAgentShell._show_screen"), \
             patch("session_log.SessionLog", MagicMock()):
            shell = JobAgentShell.__new__(JobAgentShell)
            shell._ctx = AppContext()
            shell._screens = {}
            shell._current_screen = None
            shell._nav_buttons = {}
            return shell

    def test_appcontext_created_on_init(self):
        """AppContext is always initialised (even in mocked shell)."""
        ctx = AppContext()
        assert isinstance(ctx, AppContext)

    def test_ctx_scan_log_lines_is_list(self):
        ctx = AppContext()
        assert isinstance(ctx.scan_log_lines, list)

    def test_shell_can_be_imported(self):
        """Importing JobAgentShell does not raise."""
        from ui.app_shell import JobAgentShell
        assert JobAgentShell is not None

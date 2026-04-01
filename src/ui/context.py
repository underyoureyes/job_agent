"""
ui/context.py
=============
AppContext dataclass — shared state and callback references passed to every screen.
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, List


@dataclass
class AppContext:
    config: Optional[object] = None
    tracker: Optional[object] = None
    session: Optional[object] = None
    scan_log_lines: List[str] = field(default_factory=list)
    # Callbacks wired by shell after all screens are built
    show_screen: Optional[Callable] = None
    refresh_dashboard: Optional[Callable] = None
    refresh_review: Optional[Callable] = None
    refresh_screen: Optional[Callable] = None
    reload_backend: Optional[Callable] = None
    append_log_line: Optional[Callable] = None
    needs_setup: Optional[Callable] = None

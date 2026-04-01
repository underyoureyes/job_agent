"""
ui/screens/base.py
==================
BaseScreen — parent class for all screen panels.
"""

import tkinter as tk
from ui.constants import BG
from ui.context import AppContext


class BaseScreen:
    def __init__(self, parent: tk.Frame, ctx: AppContext):
        self.frame = tk.Frame(parent, bg=BG)
        self.ctx = ctx

    def refresh(self):
        pass

"""Cross-platform modal Yes/No dialog using tkinter (stdlib)."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def ask_yes_no(title: str, message: str) -> bool:
    """Pop a modal dialog. Returns True on Yes, False on No.

    Falls back to True (auto-accept) if tkinter is unavailable — better to
    rename an unwanted file than to silently drop the user's work.
    """
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        try:
            return bool(messagebox.askyesno(title, message, parent=root))
        finally:
            root.destroy()
    except Exception:
        log.exception("Confirmation dialog failed; auto-accepting")
        return True

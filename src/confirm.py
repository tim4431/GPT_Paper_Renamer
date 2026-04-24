"""Cross-platform Yes/No confirmation for the 'ask before rename' flow.

On Windows we fire a native Windows 10/11 toast notification with Yes/No
action buttons (via ``win11toast``) so the prompt matches the look of the
other tray notifications. On macOS / any platform where the toast backend
isn't available, we fall back to a stdlib ``tkinter.messagebox`` modal.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

log = logging.getLogger(__name__)


def _ask_via_toast(title: str, message: str) -> Optional[bool]:
    """Windows-only toast with action buttons. Returns None if unavailable."""
    try:
        from win11toast import toast
        from .winapp import APP_ID
    except ImportError:
        return None
    try:
        # ``toast`` blocks the calling thread until the user clicks a button
        # or the notification dismisses. ``app_id`` ties the toast to our
        # registered AUMID so the sender line reads "GPT Paper Renamer".
        result = toast(
            title,
            message,
            buttons=["Yes", "No"],
            duration="long",
            app_id=APP_ID,
        )
    except Exception:
        log.exception("win11toast failed; falling back to Tk dialog")
        return None
    # result is a dict like {'arguments': 'Yes'} on click, or None on dismiss.
    if isinstance(result, dict):
        arg = str(result.get("arguments", ""))
        # Older win11toast versions prefix the argument with "http:".
        return arg in ("Yes", "http:Yes")
    # No interaction before timeout -> treat as 'No' (skip rename).
    return False


def _ask_via_tk(title: str, message: str) -> bool:
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
        log.exception("Tk fallback failed; auto-accepting")
        return True


def ask_yes_no(title: str, message: str) -> bool:
    """Prompt the user for Yes/No. Returns True on Yes."""
    if sys.platform == "win32":
        result = _ask_via_toast(title, message)
        if result is not None:
            return result
    return _ask_via_tk(title, message)

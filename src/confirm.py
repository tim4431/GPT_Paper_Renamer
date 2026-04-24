"""Cross-platform Rename/Cancel confirmation for the 'ask before rename' flow.

On Windows we fire a native Windows 10/11 toast notification with
**Rename** / **Cancel** action buttons (via ``win11toast``) so the prompt
matches the look of the other tray notifications. On macOS / any platform
where the toast backend isn't available, we fall back to a small stdlib
tkinter dialog with the same two buttons.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

log = logging.getLogger(__name__)

_YES_LABEL = "Rename"
_NO_LABEL = "Cancel"


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
            buttons=[_YES_LABEL, _NO_LABEL],
            duration="long",
            app_id=APP_ID,
        )
    except Exception:
        log.exception("win11toast failed; falling back to Tk dialog")
        return None
    # result: {'arguments': 'Rename'} on click, or None on dismiss/timeout.
    if isinstance(result, dict):
        arg = str(result.get("arguments", ""))
        # Older win11toast versions prefix the argument with "http:".
        return arg in (_YES_LABEL, f"http:{_YES_LABEL}")
    # No interaction before timeout -> treat as Cancel (skip rename).
    return False


def _ask_via_tk(title: str, message: str) -> bool:
    """Tiny custom Tk dialog with Rename/Cancel buttons."""
    try:
        import tkinter as tk
        from tkinter import ttk

        result = {"value": False}

        root = tk.Tk()
        root.title(title)
        root.resizable(False, False)
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        frame = ttk.Frame(root, padding=18)
        frame.pack()
        ttk.Label(frame, text=message, wraplength=360, justify="left").pack(
            anchor="w", pady=(0, 14)
        )

        def _choose(value: bool) -> None:
            result["value"] = value
            root.destroy()

        btns = ttk.Frame(frame)
        btns.pack(fill="x")
        ttk.Button(btns, text=_NO_LABEL, command=lambda: _choose(False)).pack(side="right")
        rename_btn = ttk.Button(btns, text=_YES_LABEL, command=lambda: _choose(True))
        rename_btn.pack(side="right", padx=(0, 6))
        rename_btn.focus_set()
        root.bind("<Return>", lambda _e: _choose(True))
        root.bind("<Escape>", lambda _e: _choose(False))

        # Center on screen.
        root.update_idletasks()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

        root.mainloop()
        return result["value"]
    except Exception:
        log.exception("Tk fallback failed; auto-accepting")
        return True


def ask_yes_no(title: str, message: str) -> bool:
    """Prompt the user with Rename/Cancel. Returns True on Rename."""
    if sys.platform == "win32":
        result = _ask_via_toast(title, message)
        if result is not None:
            return result
    return _ask_via_tk(title, message)

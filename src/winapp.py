"""Windows-only: register an AppUserModelID so toast notifications show
"GPT Paper Renamer" as the sender instead of "Python".

No-ops on non-Windows platforms.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

log = logging.getLogger(__name__)

# AUMID — must match between the process-level call and the registry entry.
APP_ID = "GPTPaperRenamer"
DISPLAY_NAME = "GPT Paper Renamer"


def configure() -> Optional[str]:
    """Register the AUMID (HKCU) and set it on this process.

    Returns the AUMID on success, or None if not applicable / failed.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import winreg

        key_path = rf"Software\Classes\AppUserModelId\{APP_ID}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, DISPLAY_NAME)

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        log.info("AppUserModelID set to %s (%s)", APP_ID, DISPLAY_NAME)
        return APP_ID
    except Exception:
        log.exception("Failed to set AppUserModelID")
        return None

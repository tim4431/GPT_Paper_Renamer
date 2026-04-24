"""Cross-platform autostart: register the tray app to launch at user login.

Windows: writes ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``.
macOS: drops a LaunchAgent plist in ``~/Library/LaunchAgents``.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

APP_NAME = "GPTPaperRenamer"
APP_LABEL = "com.user.gptpaperrenamer"


def _project_root() -> Path:
    """Absolute path to the directory containing ``app.py``."""
    return Path(__file__).resolve().parent.parent


def _launch_argv() -> list[str]:
    """Return the argv used for silent boot-time launch."""
    root = _project_root()
    if sys.platform == "win32":
        python = root / ".venv" / "Scripts" / "pythonw.exe"
    else:
        python = root / ".venv" / "bin" / "python3"
    return [str(python), str(root / "app.py")]


def is_supported() -> bool:
    return sys.platform in ("win32", "darwin")


# --- Windows (HKCU\...\Run) -------------------------------------------------

def _win_open(write: bool):  # pragma: no cover — Windows only
    import winreg

    access = winreg.KEY_ALL_ACCESS if write else winreg.KEY_READ
    return winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        access,
    )


def _win_current_command() -> str | None:
    import winreg

    try:
        with _win_open(write=False) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return str(value)
    except FileNotFoundError:
        return None


def _win_enable() -> None:
    import winreg

    cmd = subprocess.list2cmdline(_launch_argv())
    with _win_open(write=True) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
    log.info("Autostart enabled (Windows): %s", cmd)


def _win_disable() -> None:
    import winreg

    try:
        with _win_open(write=True) as key:
            winreg.DeleteValue(key, APP_NAME)
        log.info("Autostart disabled (Windows)")
    except FileNotFoundError:
        pass


# --- macOS (LaunchAgent) ----------------------------------------------------

def _mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{APP_LABEL}.plist"


def _mac_render_plist() -> str:
    argv = _launch_argv()
    args_xml = "\n".join(f"        <string>{a}</string>" for a in argv)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{APP_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>WorkingDirectory</key>
    <string>{_project_root()}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""


def _mac_enable() -> None:
    path = _mac_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_mac_render_plist(), encoding="utf-8")
    # Best-effort activation for the current session; the plist takes effect
    # on next login regardless.
    try:
        subprocess.run(["launchctl", "load", str(path)], check=False, capture_output=True)
    except Exception:
        pass
    log.info("Autostart enabled (macOS): %s", path)


def _mac_disable() -> None:
    path = _mac_plist_path()
    if path.exists():
        try:
            subprocess.run(["launchctl", "unload", str(path)], check=False, capture_output=True)
        except Exception:
            pass
        path.unlink()
        log.info("Autostart disabled (macOS)")


# --- Public API -------------------------------------------------------------

def is_enabled() -> bool:
    if sys.platform == "win32":
        return _win_current_command() is not None
    if sys.platform == "darwin":
        return _mac_plist_path().exists()
    return False


def set_enabled(enabled: bool) -> None:
    if not is_supported():
        raise NotImplementedError(f"Autostart not implemented for {sys.platform}")
    if sys.platform == "win32":
        _win_enable() if enabled else _win_disable()
    elif sys.platform == "darwin":
        _mac_enable() if enabled else _mac_disable()


def refresh_if_enabled() -> None:
    """Self-heal: if autostart is on but points at the wrong path (because the
    user moved the project folder), rewrite it with the current path."""
    if not is_supported() or not is_enabled():
        return
    try:
        if sys.platform == "win32":
            expected = subprocess.list2cmdline(_launch_argv())
            if _win_current_command() != expected:
                _win_enable()
                log.info("Autostart path was stale; refreshed.")
        elif sys.platform == "darwin":
            expected = _mac_render_plist()
            current = _mac_plist_path().read_text(encoding="utf-8")
            if current != expected:
                _mac_enable()
                log.info("Autostart plist was stale; refreshed.")
    except Exception:
        log.exception("Failed to refresh autostart entry")

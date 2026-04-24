"""OS-level integration: app identity (for toast notifications) and autostart.

Two concerns live together here because both are "register this app with the
operating system so it behaves like a real desktop app":

1. **App identity** (``configure_app_id``) — on Windows, sets an
   AppUserModelID so toast notifications show "GPT Paper Renamer" rather
   than "Python". No-op on macOS.

2. **Autostart** (``autostart_enabled`` / ``set_autostart`` / ``refresh_autostart``)
   — Windows: ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``;
   macOS: a LaunchAgent plist in ``~/Library/LaunchAgents``.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Identifier used for both the Windows AUMID and the Run-key value name.
APP_ID = "GPTPaperRenamer"
DISPLAY_NAME = "GPT Paper Renamer"
# Reverse-DNS label used for the macOS LaunchAgent plist.
LAUNCH_AGENT_LABEL = "com.user.gptpaperrenamer"


def _project_root() -> Path:
    """Absolute path to the directory containing ``app.py``."""
    return Path(__file__).resolve().parent.parent


def _launch_argv() -> list[str]:
    """argv used for boot-time launch (pythonw/python3 + app.py, absolute)."""
    root = _project_root()
    if sys.platform == "win32":
        python = root / ".venv" / "Scripts" / "pythonw.exe"
    else:
        python = root / ".venv" / "bin" / "python3"
    return [str(python), str(root / "app.py")]


# === Single-instance lock ===================================================

_LOCK_NAME = ".app.lock"


def _lock_path() -> Path:
    return _project_root() / _LOCK_NAME


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return bool(ok) and exit_code.value == STILL_ACTIVE
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def acquire_lock() -> bool:
    """Try to acquire a single-instance lock. Returns True if acquired."""
    lock = _lock_path()
    if lock.exists():
        try:
            old_pid = int(lock.read_text(encoding="utf-8").strip())
            if _is_pid_alive(old_pid):
                log.info("Lock held by running pid %d; not starting.", old_pid)
                return False
            log.info("Stale lock from dead pid %d; replacing.", old_pid)
        except (ValueError, OSError):
            log.warning("Unreadable lock file; replacing.")
        try:
            lock.unlink()
        except OSError:
            log.exception("Could not remove stale lock file")
            return False
    try:
        lock.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except OSError:
        log.exception("Could not write lock file %s", lock)
        return False


def release_lock() -> None:
    """Remove the lock file if it still belongs to this process."""
    lock = _lock_path()
    try:
        if lock.exists() and lock.read_text(encoding="utf-8").strip() == str(os.getpid()):
            lock.unlink()
    except OSError:
        log.exception("Failed to release lock %s", lock)


def notify_already_running() -> None:
    """Tell the user the app is already running (toast on Windows, Tk otherwise)."""
    message = "GPT Paper Renamer is already running.\nCheck your system tray / menu bar."
    log.info(message.replace("\n", " "))
    if sys.platform == "win32":
        try:
            from win11toast import toast

            toast(
                "GPT Paper Renamer",
                message,
                app_id=APP_ID,
                duration="short",
            )
            return
        except Exception:
            log.exception("win11toast failed; falling back to Tk")
    # Cross-platform fallback.
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        messagebox.showinfo("GPT Paper Renamer", message)
        root.destroy()
    except Exception:
        log.exception("Tk fallback failed; printing to stderr")
        print(message, file=sys.stderr)


# === App identity (Windows AUMID) ==========================================

def configure_app_id() -> Optional[str]:
    """Register the Windows AUMID so notifications show the app name.

    Returns the AUMID on success, or None if not applicable / failed.
    No-op on non-Windows platforms.
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


# === Settings wizard launcher ==============================================

def open_settings() -> None:
    """Spawn the CLI wizard in a new terminal window (detached from the tray)."""
    root = _project_root()
    try:
        if sys.platform == "win32":
            python = root / ".venv" / "Scripts" / "python.exe"
            subprocess.Popen(
                [str(python), "-m", "src.wizard"],
                cwd=str(root),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        elif sys.platform == "darwin":
            python = root / ".venv" / "bin" / "python3"
            script = f"cd {shlex.quote(str(root))} && {shlex.quote(str(python))} -m src.wizard"
            subprocess.Popen(
                ["osascript", "-e",
                 f'tell application "Terminal" to do script {shlex.quote(script)}'],
            )
        else:
            log.warning("open_settings not implemented for %s", sys.platform)
    except Exception:
        log.exception("Failed to launch settings wizard")


# === Autostart ==============================================================

def autostart_supported() -> bool:
    return sys.platform in ("win32", "darwin")


# --- Windows (HKCU\...\Run) -------------------------------------------------

def _win_open_run_key(write: bool):  # pragma: no cover - Windows only
    import winreg

    access = winreg.KEY_ALL_ACCESS if write else winreg.KEY_READ
    return winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        access,
    )


def _win_current_command() -> Optional[str]:
    import winreg

    try:
        with _win_open_run_key(write=False) as key:
            value, _ = winreg.QueryValueEx(key, APP_ID)
            return str(value)
    except FileNotFoundError:
        return None


def _win_enable() -> None:
    import winreg

    cmd = subprocess.list2cmdline(_launch_argv())
    with _win_open_run_key(write=True) as key:
        winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, cmd)
    log.info("Autostart enabled (Windows): %s", cmd)


def _win_disable() -> None:
    import winreg

    try:
        with _win_open_run_key(write=True) as key:
            winreg.DeleteValue(key, APP_ID)
        log.info("Autostart disabled (Windows)")
    except FileNotFoundError:
        pass


# --- macOS (LaunchAgent) ----------------------------------------------------

def _mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def _mac_render_plist() -> str:
    argv = _launch_argv()
    args_xml = "\n".join(f"        <string>{a}</string>" for a in argv)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCH_AGENT_LABEL}</string>
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


# --- Public autostart API ---------------------------------------------------

def autostart_enabled() -> bool:
    if sys.platform == "win32":
        return _win_current_command() is not None
    if sys.platform == "darwin":
        return _mac_plist_path().exists()
    return False


def set_autostart(enabled: bool) -> None:
    if not autostart_supported():
        raise NotImplementedError(f"Autostart not implemented for {sys.platform}")
    if sys.platform == "win32":
        _win_enable() if enabled else _win_disable()
    elif sys.platform == "darwin":
        _mac_enable() if enabled else _mac_disable()


def refresh_autostart() -> None:
    """Self-heal: if autostart is on but the stored path is stale (user moved
    the project folder), rewrite it with the current path."""
    if not autostart_supported() or not autostart_enabled():
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

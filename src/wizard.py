"""Cross-platform CLI setup wizard.

Two modes:

* **Guided** (runs automatically on first launch): prompts for every setting in
  order, like a fresh installer.
* **Menu** (runs when ``config.yaml`` already exists): shows current values
  and lets the user edit one thing at a time, re-run the guided setup, or
  request a .venv re-install.

Invoke directly:  ``python -m src.wizard``
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

from .config import DEFAULT_PROMPT, write_config

FORMAT_PRESETS: list[tuple[str, str]] = [
    ("Title (original) Author", "{title}_({original})_{author}"),
    ("Title only",               "{title}"),
    ("Title - Author",           "{title} - {author}"),
    ("Author - Title",           "{author} - {title}"),
    ("Original + Title",         "{original}_{title}"),
]

EXAMPLE = {
    "title": "Quantum Entanglement of Black Holes",
    "author": "S. Hawking",
    "original": "1234.56789",
}

DEFAULT_MODEL = "gpt-5-mini"
REINSTALL_SENTINEL = "_project_root/.reinstall_venv"  # resolved in _request_reinstall


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def _input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def _ask(label: str, default: Optional[str] = None, *, required: bool = True) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = _input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print("  (a value is required)")


def _ask_yn(question: str, *, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        raw = _input(f"{question}{suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  (please type y or n)")


def _preview(template: str) -> str:
    try:
        return template.format(**EXAMPLE) + ".pdf"
    except Exception as e:
        return f"<invalid template: {e}>"


def _redact_key(key: Optional[str]) -> str:
    if not key:
        return "(not set; OPENAI_API_KEY env var will be used)"
    if len(key) <= 10:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


def _load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Individual settings
# ---------------------------------------------------------------------------

def _change_api_key(data: dict) -> bool:
    """Returns True if the caller should save (something was changed)."""
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    print()
    print(f"Current API key: {_redact_key(data.get('api_key'))}")
    if env_key and not data.get("api_key"):
        print("(OPENAI_API_KEY is set in your environment and will be used.)")
    if not _ask_yn("Change it?"):
        return False
    new = _input("  New key (blank to clear / use env var): ").strip()
    if new:
        data["api_key"] = new
        print(f"  Saved new key: {_redact_key(new)}")
    else:
        if "api_key" in data:
            data.pop("api_key")
            print("  Cleared; will use OPENAI_API_KEY env var.")
    return True


def _change_folder(data: dict) -> bool:
    current = data.get("watch_folder") or "~/Downloads"
    print()
    print(f"Current watch folder: {current}")
    if not _ask_yn("Change it?"):
        return False
    while True:
        raw = _ask("  New folder", current)
        path = Path(os.path.expandvars(raw)).expanduser()
        if path.is_dir():
            data["watch_folder"] = str(path)
            print(f"  Saved: {path}")
            return True
        print(f"  '{path}' is not a folder. Try again.")


def _change_format(data: dict) -> bool:
    current = data.get("filename_format", FORMAT_PRESETS[0][1])
    print()
    print(f"Current filename format: {current}")
    print(f"  Preview: {_preview(current)}")
    if not _ask_yn("Change it?"):
        return False
    print()
    print("Presets:")
    for i, (label, tpl) in enumerate(FORMAT_PRESETS, 1):
        print(f"  {i}. {label:<28s}  ->  {_preview(tpl)}")
    print("  c. Custom template")
    while True:
        choice = _ask("Pick 1-5 or 'c'", "1").lower()
        if choice == "c":
            tpl = _ask("Custom template (fields: {title} {author} {original})")
            try:
                tpl.format(**EXAMPLE)
            except Exception as e:
                print(f"  Invalid template: {e}")
                continue
            data["filename_format"] = tpl
            print(f"  Saved: {tpl}")
            return True
        if choice.isdigit() and 1 <= int(choice) <= len(FORMAT_PRESETS):
            data["filename_format"] = FORMAT_PRESETS[int(choice) - 1][1]
            print(f"  Saved: {data['filename_format']}")
            return True
        print("  Please choose 1-5 or 'c'.")


def _toggle_confirmation(data: dict) -> bool:
    current = bool(data.get("require_confirmation", False))
    print()
    print(f"'Ask before rename' is currently: {'ON' if current else 'OFF'}")
    if not _ask_yn(f"Turn it {'OFF' if current else 'ON'}?"):
        return False
    data["require_confirmation"] = not current
    print(f"  Saved: {'ON' if not current else 'OFF'}")
    return True


def _request_reinstall(config_path: Path) -> None:
    root = config_path.resolve().parent
    sentinel = root / ".reinstall_venv"
    print()
    print("This will delete .venv/ and reinstall all dependencies on the next")
    print("launch. You'll need to quit the tray app for the reinstall to run.")
    if not _ask_yn("Continue?"):
        return
    sentinel.write_text("requested by wizard\n", encoding="utf-8")
    print()
    print(f"  Sentinel written: {sentinel}")
    print("  Next steps:")
    print("    1. Right-click the tray icon and choose Quit.")
    print("    2. Double-click run_app.bat (Windows) / run_app.command (macOS).")
    print("       The launcher will detect the sentinel, wipe .venv/, and")
    print("       reinstall everything before starting the app.")


# ---------------------------------------------------------------------------
# Menu + guided flows
# ---------------------------------------------------------------------------

def _print_header() -> None:
    print("=" * 52)
    print(" GPT Paper Renamer - Settings")
    print("=" * 52)


def _print_status(data: dict) -> None:
    print()
    print("Current settings:")
    print(f"  1. API key:           {_redact_key(data.get('api_key'))}")
    print(f"  2. Watch folder:      {data.get('watch_folder', '(unset)')}")
    fmt = data.get("filename_format", FORMAT_PRESETS[0][1])
    print(f"  3. Filename format:   {fmt}")
    on = bool(data.get("require_confirmation", False))
    print(f"  4. Ask before rename: {'ON' if on else 'OFF'}")


def _menu_loop(config_path: Path) -> bool:
    """Interactive menu. Returns True after any successful exit."""
    data = _load_existing(config_path)
    data.setdefault("prompt", DEFAULT_PROMPT)
    data.setdefault("model", DEFAULT_MODEL)

    _print_header()
    print(f"Config file: {config_path.resolve()}")

    dirty = False
    while True:
        _print_status(data)
        print()
        print("Actions:")
        print("  [1] Change API key")
        print("  [2] Change watch folder")
        print("  [3] Change filename format")
        print("  [4] Toggle ask-before-rename")
        print("  [5] Full guided re-setup")
        print("  [6] Re-install .venv (wipe and reinstall dependencies)")
        print("  [q] Quit")
        choice = _input("\nChoice: ").strip().lower()

        changed = False
        if choice == "1":
            changed = _change_api_key(data)
        elif choice == "2":
            changed = _change_folder(data)
        elif choice == "3":
            changed = _change_format(data)
        elif choice == "4":
            changed = _toggle_confirmation(data)
        elif choice == "5":
            if _ask_yn("This will walk through every setting again. Continue?"):
                return _guided_setup(config_path)
        elif choice == "6":
            _request_reinstall(config_path)
        elif choice == "q":
            break
        else:
            print("  Please choose 1-6 or q.")
            continue

        if changed:
            write_config(config_path, data)
            dirty = True
            print("  (saved to config.yaml)")

    if dirty:
        print()
        print("Restart the tray (right-click > Quit, then relaunch) for changes")
        print("to take effect.")
    return True


def _guided_setup(config_path: Path, *, first_run: bool = False) -> bool:
    """The original sequential flow, used on first run and via menu option 5.

    When *first_run* is True, shows a 3-second closing countdown after
    saving so the user sees "setup done" before the launcher starts the app.
    """
    existing = _load_existing(config_path)
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()

    _print_header()
    print(f"Answers will be saved to: {config_path.resolve()}")
    print()

    # API key
    if env_key:
        print("OPENAI_API_KEY detected in your environment; using it.")
        print("(Press Enter to accept, or paste a different key to override.)")
        typed = _ask("API key (optional)", default="", required=False)
        api_key = typed or None
    else:
        print("OpenAI API key (https://platform.openai.com/api-keys):")
        api_key = _ask("API key")

    # Folder
    print()
    default_folder = existing.get("watch_folder") or str(Path.home() / "Downloads")
    data = {"watch_folder": default_folder}
    _change_folder_forced(data, default_folder)

    # Format
    template = _pick_format(existing.get("filename_format", FORMAT_PRESETS[0][1]))

    # Ask-before-rename
    print()
    default_confirm = bool(existing.get("require_confirmation", False))
    require_confirmation = _ask_yn("Ask before renaming each PDF?", default=default_confirm)

    # Merge + save
    out = dict(existing)
    out["watch_folder"] = data["watch_folder"]
    out["filename_format"] = template
    out["require_confirmation"] = require_confirmation
    out.setdefault("recursive", False)
    out.setdefault("model", DEFAULT_MODEL)
    out.setdefault("debounce_seconds", 1.0)
    out.setdefault("request_timeout", 60.0)
    out.setdefault("max_retries", 2)
    out.setdefault("log_level", "INFO")
    out.setdefault("prompt", DEFAULT_PROMPT)
    if api_key is not None:
        out["api_key"] = api_key
    else:
        out.pop("api_key", None)

    write_config(config_path, out)
    print()
    print(f"Saved {config_path}")
    print(f"Preview filename: {_preview(template)}")

    if first_run:
        print()
        print("Setup complete! The app will start in a moment.")
        for i in range(3, 0, -1):
            print(f"  Closing in {i}... ", end="\r", flush=True)
            time.sleep(1)
        print("  Starting GPT Paper Renamer...")
    return True


def _change_folder_forced(data: dict, default_folder: str) -> None:
    """Folder prompt without the 'change it?' gate (used in guided setup)."""
    while True:
        raw = _ask("Folder to watch for new PDFs", default_folder)
        path = Path(os.path.expandvars(raw)).expanduser()
        if path.is_dir():
            data["watch_folder"] = str(path)
            return
        print(f"  '{path}' is not a folder. Try again.")


def _pick_format(default_tpl: str) -> str:
    print()
    print("Filename format:")
    for i, (label, tpl) in enumerate(FORMAT_PRESETS, 1):
        print(f"  {i}. {label:<28s}  ->  {_preview(tpl)}")
    print("  c. Custom template")
    # Preselect current preset index if it matches one.
    default_choice = next(
        (str(i) for i, (_, tpl) in enumerate(FORMAT_PRESETS, 1) if tpl == default_tpl),
        "1",
    )
    while True:
        choice = _ask("Choice 1-5 or 'c'", default_choice).lower()
        if choice == "c":
            tpl = _ask("Custom template (fields: {title} {author} {original})")
            try:
                tpl.format(**EXAMPLE)
                return tpl
            except Exception as e:
                print(f"  Invalid template: {e}")
                continue
        if choice.isdigit() and 1 <= int(choice) <= len(FORMAT_PRESETS):
            return FORMAT_PRESETS[int(choice) - 1][1]
        print("  Please choose 1-5 or 'c'.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(config_path: Path) -> bool:
    _force_utf8()
    if not config_path.exists():
        print("No config.yaml yet - running first-time setup.\n")
        return _guided_setup(config_path, first_run=True)
    return _menu_loop(config_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="src.wizard")
    parser.add_argument("-c", "--config", type=Path, default=Path("config.yaml"))
    args = parser.parse_args(argv)
    try:
        return 0 if run(args.config) else 1
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

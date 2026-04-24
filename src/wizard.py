"""Cross-platform CLI first-run wizard.

Invokable directly:  python -m src.wizard
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import yaml

from .config import DEFAULT_PROMPT

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


def _preview(template: str) -> str:
    try:
        return template.format(**EXAMPLE) + ".pdf"
    except Exception as e:
        return f"<invalid template: {e}>"


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


def _ask_folder(default: str) -> Path:
    while True:
        raw = _ask("Folder to watch for new PDFs", default)
        path = Path(os.path.expandvars(raw)).expanduser()
        if path.is_dir():
            return path
        print(f"  '{path}' is not a folder. Try again.")


def _ask_format() -> str:
    print()
    print("Filename format — pick a preset:")
    for i, (label, tpl) in enumerate(FORMAT_PRESETS, 1):
        print(f"  {i}. {label:<28s}  ->  {_preview(tpl)}")
    print("  c. Custom template")
    while True:
        choice = _ask("Choice 1-5 or 'c'", "1").lower()
        if choice == "c":
            while True:
                tpl = _ask("Custom template (fields: {title} {author} {original})")
                try:
                    tpl.format(**EXAMPLE)
                    return tpl
                except Exception as e:
                    print(f"  Invalid template: {e}")
        if choice.isdigit() and 1 <= int(choice) <= len(FORMAT_PRESETS):
            return FORMAT_PRESETS[int(choice) - 1][1]
        print("  Please choose 1-5 or 'c'.")


def _load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def run(config_path: Path) -> bool:
    """Interactive wizard. Writes *config_path* and returns True on success."""
    # Force UTF-8 on stdio so the Chinese-locale Windows terminal doesn't mojibake.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

    print("=" * 52)
    print(" GPT Paper Renamer - first-run setup")
    print("=" * 52)
    print(f"Answers will be saved to: {config_path.resolve()}")
    print()

    existing = _load_existing(config_path)
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()

    # --- API key -----------------------------------------------------------
    if env_key:
        print("OPENAI_API_KEY detected in your environment; using it.")
        print("(Press Enter to accept, or paste a different key to override.)")
        typed = _ask("API key (optional)", default="", required=False)
        api_key = typed or None  # None => rely on env var, don't write to file
    else:
        print("OpenAI API key (get one at https://platform.openai.com/api-keys):")
        api_key = _ask("API key")

    # --- Folder ------------------------------------------------------------
    print()
    default_folder = existing.get("watch_folder") or str(Path.home() / "Downloads")
    folder = _ask_folder(default_folder)

    # --- Filename format ---------------------------------------------------
    template = _ask_format()

    # --- Confirm before rename --------------------------------------------
    print()
    existing_confirm = bool(existing.get("require_confirmation", False))
    confirm_default = "y" if existing_confirm else "n"
    raw = _ask("Ask before renaming each PDF? [y/N]", confirm_default).lower()
    require_confirmation = raw.startswith("y")

    # --- Save --------------------------------------------------------------
    data = dict(existing)
    data["watch_folder"] = str(folder)
    data["filename_format"] = template
    data["require_confirmation"] = require_confirmation
    data.setdefault("recursive", False)
    data.setdefault("model", DEFAULT_MODEL)
    data.setdefault("debounce_seconds", 1.0)
    data.setdefault("request_timeout", 60.0)
    data.setdefault("max_retries", 2)
    data.setdefault("log_level", "INFO")
    data.setdefault("prompt", DEFAULT_PROMPT)
    if api_key is not None:
        data["api_key"] = api_key
    else:
        data.pop("api_key", None)  # keep file clean; env var will be used

    with config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

    print()
    print(f"Saved {config_path}")
    print(f"Preview: {_preview(template)}")
    return True


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

"""Runtime configuration loaded from YAML and environment variables."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger(__name__)

DEFAULT_PROMPT = """\
You are a PDF classification and metadata extraction assistant.
Given the image of the first page of an academic paper, extract:
  - title: the paper's title
  - author: the corresponding author's full name (or the first author if none is marked)
Return strict JSON matching the schema you are given. If a field cannot be
determined with high confidence, return the string "Unknown".
"""

CONFIG_TEMPLATE = """\
# ============================================================================
# GPT Paper Renamer -- configuration
# ============================================================================
# This file is written by the setup wizard and by the tray-menu toggles.
# Edit it by hand or re-run the wizard any time:
#     python -m src.wizard            (macOS)
#     .venv\\Scripts\\python.exe -m src.wizard   (Windows)
#
# Fields tagged "(tray)" below are also toggleable from the system-tray menu;
# the tray writes changes back into this file.
# ----------------------------------------------------------------------------

# --- What to watch ----------------------------------------------------------

# Folder to monitor. "~" expands to your home dir (works on Windows and macOS).
watch_folder: {watch_folder}

# Watch subfolders recursively?
recursive: {recursive}

# --- OpenAI -----------------------------------------------------------------

# Model used to extract title/author. Must support structured outputs + images.
# Good choices: gpt-5-mini (cheap, default), gpt-4.1-mini, gpt-4o.
model: {model}

# OpenAI API key. You can also set the OPENAI_API_KEY environment variable --
# it takes precedence over this field. See https://platform.openai.com/api-keys
{api_key_line}

# Seconds to wait before giving up on a single OpenAI call.
request_timeout: {request_timeout}

# Retries for transient OpenAI errors (handled by the SDK).
max_retries: {max_retries}

# --- Renaming ---------------------------------------------------------------

# Filename template. Available fields: {{title}} {{author}} {{original}}
# Wizard presets:
#   "{{title}}_({{original}})_{{author}}"  # title with arXiv id + author
#   "{{title}}"                             # title only
#   "{{title}} - {{author}}"
#   "{{author}} - {{title}}"
#   "{{original}}_{{title}}"
filename_format: {filename_format}

# Pop a Yes/No dialog before renaming each PDF. (tray)
require_confirmation: {require_confirmation}

# --- Tuning -----------------------------------------------------------------

# Seconds to wait after a filesystem event before touching the file, to let
# the browser finish flushing the download.
debounce_seconds: {debounce_seconds}

# Logging verbosity: DEBUG / INFO / WARNING / ERROR
log_level: {log_level}

# --- LLM prompt -------------------------------------------------------------

# System prompt. Tweak if you want different extraction behavior.
prompt: |
{prompt_block}
"""


class Config(BaseModel):
    """Validated configuration for the renamer."""

    watch_folder: Path
    api_key: str = Field(..., repr=False)
    model: str = "gpt-5-mini"
    prompt: str = DEFAULT_PROMPT
    recursive: bool = False
    filename_format: str = "{title}_({original})_{author}"
    debounce_seconds: float = 1.0
    request_timeout: float = 60.0
    max_retries: int = 2
    log_level: str = "INFO"
    # Pop a Yes/No dialog before renaming each PDF.
    require_confirmation: bool = False

    @field_validator("watch_folder")
    @classmethod
    def _expand_folder(cls, value: Path) -> Path:
        value = Path(os.path.expandvars(str(value))).expanduser()
        if not value.exists() or not value.is_dir():
            raise ValueError(f"watch_folder does not exist or is not a directory: {value}")
        return value

    @field_validator("api_key")
    @classmethod
    def _non_empty_key(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("OpenAI API key is missing. Set OPENAI_API_KEY or put api_key in config.yaml.")
        return value.strip()


def load_config(path: Optional[Path] = None) -> Config:
    """Load config.yaml, layering OPENAI_API_KEY from the environment."""
    path = Path(path) if path else Path("config.yaml")
    data: dict = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key:
        data["api_key"] = env_key

    return Config(**data)


# --- Writing config.yaml (wizard + tray toggles) ----------------------------

def _scalar(value: Any) -> str:
    """Format a single value as a YAML scalar suitable for string.format."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # JSON strings are valid YAML strings; always quoted, never ambiguous.
    return json.dumps(str(value))


def write_config(path: Path, data: dict) -> None:
    """Write *data* to *path* in the standard, documented YAML format.

    Used by both the wizard (on first run) and the tray toggles (on change)
    so the file is always in a consistent, commented form.
    """
    api_key = data.get("api_key")
    if api_key:
        api_key_line = f"api_key: {_scalar(api_key)}"
    else:
        api_key_line = '# api_key: "sk-..."   # not set here; using OPENAI_API_KEY env var'

    prompt = str(data.get("prompt") or DEFAULT_PROMPT).rstrip()
    prompt_block = "\n".join("  " + line for line in prompt.splitlines())

    rendered = CONFIG_TEMPLATE.format(
        watch_folder=_scalar(data.get("watch_folder", "~/Downloads")),
        recursive=_scalar(bool(data.get("recursive", False))),
        model=_scalar(data.get("model", "gpt-5-mini")),
        api_key_line=api_key_line,
        filename_format=_scalar(data.get("filename_format", "{title}_({original})_{author}")),
        require_confirmation=_scalar(bool(data.get("require_confirmation", False))),
        debounce_seconds=_scalar(float(data.get("debounce_seconds", 1.0))),
        request_timeout=_scalar(float(data.get("request_timeout", 60.0))),
        max_retries=_scalar(int(data.get("max_retries", 2))),
        log_level=_scalar(data.get("log_level", "INFO")),
        prompt_block=prompt_block,
    )
    path.write_text(rendered, encoding="utf-8")


def update_yaml(path: Path, **changes: Any) -> None:
    """Merge *changes* into path's YAML and rewrite through write_config.

    The documented comment structure is always preserved because we re-render
    from the same template the wizard uses. No-op if the file doesn't exist.
    """
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data.update(changes)
        write_config(path, data)
    except Exception:
        log.exception("Failed to update %s", path)

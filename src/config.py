"""Runtime configuration loaded from YAML and environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

DEFAULT_PROMPT = """\
You are a PDF classification and metadata extraction assistant.
Given the image of the first page of an academic paper, extract:
  - title: the paper's title
  - author: the corresponding author's full name (or the first author if none is marked)
Return strict JSON matching the schema you are given. If a field cannot be
determined with high confidence, return the string "Unknown".
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
    # When True, pop a Yes/No dialog for each new PDF before running the LLM.
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
    """Load config.yaml, layering in env vars for anything sensitive."""

    path = Path(path) if path else Path("config.yaml")
    data: dict = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # Environment overrides (preferred for secrets).
    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key:
        data["api_key"] = env_key
    env_watch = os.environ.get("PAPER_RENAMER_WATCH_FOLDER")
    if env_watch:
        data["watch_folder"] = env_watch
    env_model = os.environ.get("PAPER_RENAMER_MODEL")
    if env_model:
        data["model"] = env_model

    return Config(**data)

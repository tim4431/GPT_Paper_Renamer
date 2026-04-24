"""Pure-function helpers for producing safe, unique target filenames."""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_COLLAPSE_WHITESPACE = re.compile(r"\s+")
# Browsers append " (1)", " (2)", ... when a filename already exists on disk.
# We strip any number of trailing markers so "paper (1) (2)" -> "paper".
_DUPLICATE_MARKER = re.compile(r"(?:\s*\(\d+\))+$")
MAX_NAME_LENGTH = 180


def sanitize(name: str) -> str:
    """Strip characters illegal on NTFS/most filesystems and collapse whitespace."""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name).strip(" ._")
    cleaned = _COLLAPSE_WHITESPACE.sub(" ", cleaned)
    return cleaned[:MAX_NAME_LENGTH]


def strip_duplicate_marker(name: str) -> str:
    """Remove trailing ' (1)', ' (2)' etc. appended by browsers on name collision."""
    return _DUPLICATE_MARKER.sub("", name).rstrip()


def format_filename(template: str, *, title: str, author: str, original: str) -> str:
    """Apply the user-configured filename template with safe fields."""
    fields = {
        "title": sanitize(title) or "Unknown",
        "author": sanitize(author) or "Unknown",
        "original": sanitize(strip_duplicate_marker(original)),
    }
    return template.format(**fields)


def unique_path(directory: Path, base: str, ext: str) -> Path:
    """Return a path inside *directory* that does not yet exist."""
    candidate = directory / f"{base}{ext}"
    if not candidate.exists():
        return candidate
    for i in range(2, 1000):
        candidate = directory / f"{base} ({i}){ext}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find a unique name for {base}{ext} in {directory}")


def rename(old_path: Path, new_name: str, *, overwrite: bool = False) -> Path:
    """Rename *old_path* to *new_name* in the same directory and return the new path."""
    directory = old_path.parent
    target = directory / new_name
    if target.exists() and not overwrite:
        log.warning("Target already exists, skipping rename: %s", target)
        return old_path
    old_path.rename(target)
    log.info("Renamed: %s -> %s", old_path.name, target.name)
    return target

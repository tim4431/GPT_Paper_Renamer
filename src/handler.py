"""Filesystem event handler that feeds new PDFs to a background worker."""

from __future__ import annotations

import logging
import queue
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler

from .config import Config
from .extractor import MetadataExtractor, Paper
from .pdf import is_valid_pdf, render_first_page
from .renamer import format_filename, rename, unique_path

log = logging.getLogger(__name__)

Notify = Callable[[str, str], None]
Confirm = Callable[[str, str], bool]


def _noop(_title: str, _message: str) -> None:
    pass


def _always_yes(_title: str, _message: str) -> bool:
    return True


class PDFRenameWorker(threading.Thread):
    """Serializes LLM calls on a single background thread."""

    _STOP = object()

    def __init__(self, config: Config, extractor: MetadataExtractor) -> None:
        super().__init__(name="pdf-rename-worker", daemon=True)
        self._config = config
        self._extractor = extractor
        self._queue: "queue.Queue[object]" = queue.Queue()
        self._seen: set[Path] = set()
        self._seen_lock = threading.Lock()
        self._notify: Notify = _noop
        self._confirm: Confirm = _always_yes
        self.paused = False
        self.require_confirmation = config.require_confirmation

    # --- wiring --------------------------------------------------------------
    def set_notifier(self, notify: Notify) -> None:
        self._notify = notify

    def set_confirm(self, confirm: Confirm) -> None:
        self._confirm = confirm

    # --- producer ------------------------------------------------------------
    def submit(self, path: Path) -> None:
        if self.paused:
            log.debug("Paused — ignoring %s", path)
            return
        resolved = path.resolve()
        with self._seen_lock:
            if resolved in self._seen:
                return
            self._seen.add(resolved)
        self._queue.put(resolved)

    def stop(self) -> None:
        self._queue.put(self._STOP)

    # --- consumer ------------------------------------------------------------
    def run(self) -> None:
        while True:
            item = self._queue.get()
            if item is self._STOP:
                return
            assert isinstance(item, Path)
            try:
                self._handle(item)
            except Exception:
                log.exception("Failed to process %s", item)

    def _handle(self, path: Path) -> None:
        if not is_valid_pdf(path):
            log.debug("Skipping non-PDF or incomplete file: %s", path)
            return

        if self.require_confirmation:
            if not self._confirm(
                "GPT Paper Renamer",
                f"New PDF detected:\n\n{path.name}\n\nRename it?",
            ):
                log.info("User declined rename for %s", path.name)
                self._notify("Skipped", path.name)
                return

        log.info("Analyzing %s", path.name)
        try:
            paper = self._extract_metadata(path)
        except Exception:
            log.exception("Extraction failed for %s", path)
            self._notify("Extraction failed", path.name)
            return

        new_name = (
            format_filename(
                self._config.filename_format,
                title=paper.title,
                author=paper.author,
                original=path.stem,
            )
            + path.suffix
        )
        target = unique_path(path.parent, Path(new_name).stem, path.suffix)
        renamed = rename(path, target.name)

        if renamed == path:
            self._notify("Duplicate name", path.name)
        else:
            with self._seen_lock:
                self._seen.add(renamed.resolve())
            self._notify("Renamed", f"{path.name}\n→ {renamed.name}")

    def _extract_metadata(self, path: Path) -> Paper:
        with tempfile.TemporaryDirectory() as tmp:
            image_path = render_first_page(path, Path(tmp) / "frontpage.png")
            return self._extractor.extract(image_path)


class PDFEventHandler(FileSystemEventHandler):
    """Watchdog handler; reacts to both `on_created` and `on_moved`."""

    def __init__(self, worker: PDFRenameWorker, *, debounce: float = 1.0) -> None:
        super().__init__()
        self._worker = worker
        self._debounce = debounce

    def on_created(self, event: FileSystemEvent) -> None:
        self._maybe_enqueue(event.src_path, event.is_directory)

    def on_moved(self, event: FileSystemEvent) -> None:
        # Browsers download to `.crdownload` / `.part` / `.tmp` and rename to
        # `.pdf` on completion — react to the destination path.
        self._maybe_enqueue(getattr(event, "dest_path", event.src_path), event.is_directory)

    def _maybe_enqueue(self, raw_path: Optional[str], is_directory: bool) -> None:
        if is_directory or not raw_path:
            return
        path = Path(raw_path)
        if path.suffix.lower() != ".pdf":
            return
        log.debug("Detected PDF event: %s", path)
        # Wait briefly for the OS to finish flushing the rename/write.
        time.sleep(self._debounce)
        self._worker.submit(path)

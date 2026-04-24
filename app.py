"""Entry point for the GPT Paper Renamer tray app (Windows + macOS)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from pathlib import Path

log = logging.getLogger("gpt_paper_renamer")

APP_DIR = Path(__file__).resolve().parent
LOG_FILE = APP_DIR / "app.log"


def _configure_logging(level: str = "INFO") -> None:
    """Always log to app.log (works even under pythonw.exe where stderr is None)."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    for h in list(root.handlers):
        root.removeHandler(h)
    fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr is not None:
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(fmt)
        root.addHandler(ch)


def _show_error_dialog(title: str, message: str) -> None:
    """Best-effort GUI error for pythonw.exe where console output is invisible."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    # Anchor cwd to the app folder so relative paths (config.yaml) and
    # autostart-launched invocations always resolve correctly.
    os.chdir(APP_DIR)

    parser = argparse.ArgumentParser(prog="paper-renamer")
    parser.add_argument("-c", "--config", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without the tray icon (useful for debugging or servers).",
    )
    args = parser.parse_args(argv)

    _configure_logging("INFO")
    log.info("--- startup ---")

    from src import autostart
    from src.config import load_config, update_yaml
    from src.confirm import ask_yes_no
    from src.extractor import MetadataExtractor
    from src.handler import PDFEventHandler, PDFRenameWorker
    from src.tray import Tray
    from watchdog.observers import Observer

    # Self-heal a stale autostart entry after the user moves the project.
    autostart.refresh_if_enabled()

    try:
        config = load_config(args.config)
    except Exception as e:
        log.exception("Failed to load config from %s", args.config)
        _show_error_dialog(
            "GPT Paper Renamer — config error",
            f"Could not load {args.config}:\n\n{e}\n\nSee app.log for details.",
        )
        return 1

    logging.getLogger().setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    extractor = MetadataExtractor(
        api_key=config.api_key,
        model=config.model,
        prompt=config.prompt,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
    )
    worker = PDFRenameWorker(config, extractor)
    worker.set_confirm(ask_yes_no)
    worker.start()

    observer = Observer()
    observer.schedule(
        PDFEventHandler(worker, debounce=config.debounce_seconds),
        path=str(config.watch_folder),
        recursive=config.recursive,
    )
    observer.start()

    log.info("Watching %s (model=%s)", config.watch_folder, config.model)

    def shutdown() -> None:
        log.info("Shutting down...")
        observer.stop()
        observer.join()
        worker.stop()
        worker.join(timeout=5)

    if args.headless:
        _run_headless(shutdown)
        return 0

    # Persist tray toggles back into config.yaml so they survive restarts.
    def _set_confirmation(value: bool) -> None:
        worker.require_confirmation = value
        update_yaml(args.config, require_confirmation=value)

    # Autostart is a system-level setting, not a config.yaml setting — it
    # lives in the registry / LaunchAgent. But expose it the same way.
    autostart_supported = autostart.is_supported()
    startup_message = (
        f"Watching {config.watch_folder.name}"
        + (" • ask-before-rename ON" if config.require_confirmation else "")
    )

    tray = Tray(
        watch_folder=config.watch_folder,
        on_pause_changed=lambda paused: setattr(worker, "paused", paused),
        on_quit=shutdown,
        is_paused=lambda: worker.paused,
        on_confirm_changed=_set_confirmation,
        is_confirm=lambda: worker.require_confirmation,
        on_autostart_changed=(autostart.set_enabled if autostart_supported else None),
        is_autostart=(autostart.is_enabled if autostart_supported else None),
        log_path=LOG_FILE,
        startup_message=startup_message,
    )
    worker.set_notifier(tray.notify)

    # pystray must run on the main thread (required on macOS).
    try:
        tray.run()
    except KeyboardInterrupt:
        shutdown()
    return 0


def _run_headless(shutdown) -> None:
    import signal
    import threading

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: stop.set())
        except (ValueError, AttributeError):
            pass
    try:
        stop.wait()
    finally:
        shutdown()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        tb = traceback.format_exc()
        try:
            _configure_logging("INFO")
            log.critical("Unhandled exception:\n%s", tb)
        except Exception:
            pass
        _show_error_dialog(
            "GPT Paper Renamer — crash",
            f"{type(e).__name__}: {e}\n\nFull traceback in app.log.",
        )
        sys.exit(1)

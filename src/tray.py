"""Cross-platform system tray icon using pystray."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFont
from pystray import Icon, Menu, MenuItem

log = logging.getLogger(__name__)

_ICON_SIZE = 64
_ACTIVE = (46, 160, 67, 255)
_PAUSED = (140, 140, 140, 255)


def _build_icon_image(paused: bool) -> Image.Image:
    img = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [4, 4, _ICON_SIZE - 4, _ICON_SIZE - 4],
        radius=12,
        fill=_PAUSED if paused else _ACTIVE,
    )
    font = _load_font(34)
    text = "P"
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((_ICON_SIZE - w) / 2 - bbox[0], (_ICON_SIZE - h) / 2 - bbox[1]),
        text,
        fill=(255, 255, 255, 255),
        font=font,
    )
    return img


def _load_font(size: int) -> ImageFont.ImageFont:
    for candidate in ("arial.ttf", "Helvetica.ttc", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _open_path(path: Path) -> None:
    """Open *path* (file or folder) with the OS default handler."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        log.exception("Failed to open %s", path)


class Tray:
    """Thin wrapper around pystray.Icon with Pause/Open/Quit menu."""

    def __init__(
        self,
        *,
        watch_folder: Path,
        on_pause_changed: Callable[[bool], None],
        on_quit: Callable[[], None],
        is_paused: Callable[[], bool],
        on_confirm_changed: Optional[Callable[[bool], None]] = None,
        is_confirm: Optional[Callable[[], bool]] = None,
        on_autostart_changed: Optional[Callable[[bool], None]] = None,
        is_autostart: Optional[Callable[[], bool]] = None,
        log_path: Optional[Path] = None,
        startup_message: Optional[str] = None,
    ) -> None:
        self._watch_folder = watch_folder
        self._on_pause_changed = on_pause_changed
        self._on_quit = on_quit
        self._is_paused = is_paused
        self._on_confirm_changed = on_confirm_changed
        self._is_confirm = is_confirm
        self._on_autostart_changed = on_autostart_changed
        self._is_autostart = is_autostart
        self._log_path = log_path
        self._startup_message = startup_message
        self._icon = Icon(
            "GPTPaperRenamer",
            _build_icon_image(paused=False),
            f"GPT Paper Renamer — {watch_folder}",
            menu=self._build_menu(),
        )

    # --- menu ----------------------------------------------------------------
    def _build_menu(self) -> Menu:
        items = [
            MenuItem(lambda _: f"Watching: {self._watch_folder.name}", None, enabled=False),
            MenuItem(
                lambda _: "Resume" if self._is_paused() else "Pause",
                self._toggle_pause,
            ),
        ]
        if self._is_confirm is not None and self._on_confirm_changed is not None:
            items.append(
                MenuItem(
                    "Ask before rename",
                    self._toggle_confirm,
                    checked=lambda _: bool(self._is_confirm()),
                )
            )
        if self._is_autostart is not None and self._on_autostart_changed is not None:
            items.append(
                MenuItem(
                    "Start at login",
                    self._toggle_autostart,
                    checked=lambda _: bool(self._is_autostart()),
                )
            )
        items += [
            Menu.SEPARATOR,
            MenuItem("Open watch folder", lambda _: _open_path(self._watch_folder)),
            MenuItem(
                "View log",
                lambda _: _open_path(self._log_path) if self._log_path else None,
                enabled=self._log_path is not None,
            ),
            Menu.SEPARATOR,
            MenuItem("Quit", self._quit),
        ]
        return Menu(*items)

    def _toggle_confirm(self, icon: Icon, _item: MenuItem) -> None:
        if self._on_confirm_changed is None or self._is_confirm is None:
            return
        self._on_confirm_changed(not self._is_confirm())
        icon.update_menu()

    def _toggle_autostart(self, icon: Icon, _item: MenuItem) -> None:
        if self._on_autostart_changed is None or self._is_autostart is None:
            return
        new_state = not self._is_autostart()
        try:
            self._on_autostart_changed(new_state)
        except Exception as e:
            log.exception("Failed to toggle autostart")
            self.notify("Autostart error", str(e))
            return
        self.notify(
            "Start at login",
            "Enabled — GPT Paper Renamer will launch automatically."
            if new_state
            else "Disabled — app will no longer launch at login.",
        )
        icon.update_menu()

    def _toggle_pause(self, icon: Icon, _item: MenuItem) -> None:
        new_state = not self._is_paused()
        self._on_pause_changed(new_state)
        icon.icon = _build_icon_image(paused=new_state)
        icon.title = (
            f"GPT Paper Renamer — {self._watch_folder} (paused)"
            if new_state
            else f"GPT Paper Renamer — {self._watch_folder}"
        )
        icon.update_menu()

    def _quit(self, icon: Icon, _item: MenuItem) -> None:
        log.info("Tray: quit requested")
        icon.stop()
        try:
            self._on_quit()
        except Exception:
            log.exception("on_quit handler failed")

    # --- public API ----------------------------------------------------------
    def notify(self, title: str, message: str) -> None:
        """Fire a desktop notification via the tray icon."""
        try:
            self._icon.notify(message, title=title)
        except Exception:
            log.exception("Tray notify failed")

    def run(self) -> None:
        """Block the main thread and run the tray event loop."""
        def _on_ready(icon: Icon) -> None:
            icon.visible = True
            if self._startup_message:
                self.notify("GPT Paper Renamer", self._startup_message)
        self._icon.run(setup=_on_ready)

    def run_detached(self) -> threading.Thread:
        """Run the tray in a background thread (not recommended on macOS)."""
        t = threading.Thread(target=self._icon.run, daemon=True, name="tray")
        t.start()
        return t

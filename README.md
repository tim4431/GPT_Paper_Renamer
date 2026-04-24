# GPT Paper Renamer

A small cross-platform (Windows + macOS) tray app that watches a folder (e.g. your browser downloads) and renames newly arriving academic PDFs based on the title and author extracted from the first page by an OpenAI model.

## Features

- **System tray app** via `pystray` — Pause/Resume, Open watch folder, Quit.
- **Cross-platform** — Windows 10/11 and macOS 12+.
- **First-run CLI wizard** (no manual config editing). Prompts for API key, watch folder, and filename format.
- Self-bootstrapping launchers: a single double-click creates a local `.venv/`, installs deps, runs the wizard, and starts the tray app.
- Watchdog-based folder monitoring (handles `.crdownload` → `.pdf` renames).
- OpenAI **structured outputs** via `client.chat.completions.parse`.
- First-page rendering via **PyMuPDF** (no Poppler install).
- Desktop notifications for every rename.

## Requirements

- **Python 3.10–3.13** on your `PATH` (the launchers also auto-detect Anaconda/Miniconda at the usual locations).
  - Windows: [python.org installer](https://www.python.org/downloads/windows/) — tick "Add python.exe to PATH".
  - macOS: `brew install python` or python.org.
- An OpenAI API key ([create one](https://platform.openai.com/api-keys)).

## First run (click-and-use)

### Windows

Double-click **`run_app.bat`**. On first run it:

1. Creates `.venv/` and `pip install`s dependencies.
2. Launches the CLI wizard — paste your API key, pick your watch folder, choose a filename format.
3. Starts the tray app (via `pythonw.exe`, so no console window stays open).

For auto-start at login, drop a shortcut to `run_app.bat` into `shell:startup`.

### macOS

```bash
chmod +x run_app.command     # one-time
```

Then double-click **`run_app.command`**. Same flow: `.venv/` + install + wizard + menu-bar icon.

> macOS icons from non-bundled Python sometimes don't show until the terminal is focused once. For a proper `.app`, bundle with `pyinstaller --windowed app.py` or `py2app`.

## Filename format presets

The wizard offers these presets (or type a custom template):

| # | Preset                 | Example                                                   |
|---|------------------------|-----------------------------------------------------------|
| 1 | Title (original) Author| `Quantum Entanglement_(1234.56789)_S. Hawking.pdf`        |
| 2 | Title only             | `Quantum Entanglement.pdf`                                |
| 3 | Title - Author         | `Quantum Entanglement - S. Hawking.pdf`                   |
| 4 | Author - Title         | `S. Hawking - Quantum Entanglement.pdf`                   |
| 5 | Original + Title       | `1234.56789_Quantum Entanglement.pdf`                     |
| c | Custom                 | any Python format string with `{title}`, `{author}`, `{original}` |

## Tray menu

| Item                | Effect                                                       |
|---------------------|--------------------------------------------------------------|
| Watching: *folder*  | (info only)                                                  |
| Pause / Resume      | Stop/start reacting to new files                             |
| Ask before rename   | Toggle the Yes/No confirmation dialog for each new PDF       |
| Open watch folder   | Reveal the folder in Explorer/Finder                         |
| View log            | Open `app.log` in the default text editor                    |
| Quit                | Clean shutdown                                               |

Icon is **green** when active, **grey** when paused.

## Re-initializing

Three levels of reset, from soft to hard:

1. **Change a single answer (API key, folder, format, ask-before-rename)** — re-run the wizard without touching anything else. The wizard loads `config.yaml`, pre-fills existing answers, and rewrites it:
   ```bash
   # Windows
   .venv\Scripts\python.exe -m src.wizard
   # macOS
   .venv/bin/python3 -m src.wizard
   ```
   Then quit the tray and double-click the launcher again.

2. **Start config fresh** — quit the tray, delete `config.yaml`, double-click the launcher. The venv is kept (fast) and the wizard reruns from scratch.

3. **Full clean install** (use if dependencies got wedged) — quit the tray, delete both `config.yaml` and the `.venv/` folder, then double-click the launcher. Recreates the venv, reinstalls everything, and reruns the wizard.

The `.venv/` folder is self-contained; deleting it touches nothing outside the project.

## Headless mode

```bash
python app.py --headless
```

No tray; useful for servers or debugging. Ctrl-C to stop.

## Project layout

```
app.py             # tray entry point (main thread)
src/
  __init__.py
  config.py        # pydantic config + YAML/env loader
  extractor.py     # OpenAI structured-output client
  handler.py       # watchdog handler + background worker
  tray.py          # pystray icon, menu, notifications
  wizard.py        # CLI first-run setup wizard
  pdf.py           # PyMuPDF helpers
  renamer.py       # filename sanitization + rename
config.yaml        # your config, written by the wizard (git-ignored)
run_app.bat        # Windows launcher
run_app.command    # macOS launcher
```

## Upgrading from v1

- `api_key` now lives either in the `OPENAI_API_KEY` env var or in `config.yaml` (written by the wizard). No more hardcoded keys in source.
- `pdf2image` + Poppler replaced with `pymupdf` (pip-only).
- `win11toast` Windows-only flow replaced with cross-platform `pystray`.
- Legacy `client.beta.chat.completions.parse` is now GA `client.chat.completions.parse`.

# GPT Paper Renamer

Watches a folder and renames new academic PDFs based on the title/author that an OpenAI model extracts from the first page. Cross-platform tray app (Windows + macOS).

## Install & run

Requires Python 3.10+ on your `PATH`.

| OS | Step |
|---|---|
| **Windows** | Double-click `run_app.bat` |
| **macOS** | `chmod +x run_app.command` once, then double-click it |

On first launch the script creates a local `.venv/`, installs dependencies, runs a short CLI wizard (API key · watch folder · filename format · ask-before-rename), and starts the tray icon.

Terminal usage (macOS):

```bash
cd /path/to/GPT_Paper_Renamer-main
./run_app.command
./run_app.command --headless
./run_app.command --help
```

## Tray menu

| Item | Effect |
|---|---|
| Watching: *folder* | info only |
| **Pause / Resume** | stop/start reacting to new files |
| **Ask before rename** | toggle the Yes/No dialog before each rename (persisted to `config.yaml`) |
| **Start at login** | toggle autostart (Windows registry / macOS LaunchAgent) |
| Open watch folder | reveal in Explorer/Finder |
| View log | open `app.log` |
| Quit | clean shutdown |

Green icon = active · grey = paused.

## Config

All settings live in [config.yaml](config.yaml) (written by the wizard, re-written by tray toggles — both preserve the documented format). Every field has an inline explanation. Common ones:

- `watch_folder` — `"~/Downloads"` by default
- `model` — `gpt-5-mini`, `gpt-4.1-mini`, `gpt-4o`…
- `api_key` — or set `OPENAI_API_KEY` in your env (env wins)
- `filename_format` — `{title}` `{author}` `{original}` tokens
- `require_confirmation` — toggle per rename

## Re-initialize

| Need | Do |
|---|---|
| Change an answer | `python -m src.wizard` (pre-fills current values) |
| Fresh config | delete `config.yaml`, relaunch |
| Full clean install | delete `.venv/` and `config.yaml`, relaunch |

## Headless

```bash
python app.py --headless
```

No tray; Ctrl-C to stop.

## Layout

```
app.py                # entry point (runs tray on main thread)
src/
  config.py           # pydantic config + YAML writer
  wizard.py           # first-run CLI wizard
  extractor.py        # OpenAI structured-output client
  handler.py          # watchdog + background worker
  tray.py             # pystray icon + menu
  confirm.py          # cross-platform Yes/No dialog
  autostart.py        # Windows registry / macOS LaunchAgent
  pdf.py              # PyMuPDF helpers
  renamer.py          # filename sanitizer + rename
config.yaml           # your config (git-ignored, fully documented)
run_app.bat           # Windows launcher (bootstraps .venv + wizard)
run_app.command       # macOS launcher
```

## Troubleshooting

- **Tray doesn't appear after first setup** → check `app.log` in the project folder; a Tk error dialog should also pop up with the traceback.
- **`.venv` creation fails with "path not found"** → your `python` is MSYS2 or the Windows Store stub. Install real Python from [python.org](https://www.python.org/downloads/) and tick *Add to PATH*. The launcher auto-detects Anaconda/Miniconda if present.
- **macOS menu bar icon missing** → focus Terminal once, or bundle with `pyinstaller --windowed app.py`.

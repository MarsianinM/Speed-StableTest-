# SpetTestMy

Portable Windows utility: a separate **speed** test and a separate channel **stability** check (latency / jitter / loss). Runs from a USB flash drive without Python installed on the target PC.

Includes a dark **CustomTkinter GUI** with simple progress, public IP detection, and local SQLite history (`spettest.db` next to the app — no cloud sync).

Local docs (if present on your machine): `docs/TZ.md`, `docs/TODO.md` (not published to git).

## Features

| Mode | What it does |
|------|----------------|
| **Speed** | Download / Upload / Ping via Cloudflare (multi-stream, warmup window) |
| **Stability** | HTTPS latency series, RFC 3550 jitter, loss %, verdict |
| **GUI** | Dark theme, stage + progress bar, live Mbps, history with date/IP filter |
| **CLI** | `speed` and `stable [seconds]` still available |

## Development

Requires Python 3.11+.

```powershell
cd SpetTestMy
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

### CLI

```powershell
python -m spettest speed
python -m spettest stable
python -m spettest stable 120
```

Or without an editable install:

```powershell
$env:PYTHONPATH = "src"
python -m spettest speed
```

### GUI

```powershell
$env:PYTHONPATH = "src"
python -m spettest
```

### Progress gap diagnostic (optional)

Checks how long the UI/callback stays silent between updates (useful if the window feels “frozen” during ping/stability):

```powershell
$env:PYTHONPATH = "src"
python scripts/check_progress_gaps.py stable 10
python scripts/check_progress_gaps.py
```

## Portable launchers

Templates in [`portable/`](portable/):

- `Інтерфейс.cmd` — GUI (`SpetTest.exe` with no args)
- `Швидкість.cmd` — CLI speed
- `Стабільність.cmd` — CLI stability (~60 s)
- `README.txt` — end-user notes (Ukrainian)

After build they are copied into `dist/SpetTest/` next to `SpetTest.exe`.

## Build for USB

```powershell
.\scripts\build.ps1
```

Output: `dist/SpetTest/` with `SpetTest.exe`, `_internal/`, all `.cmd` launchers, and `README.txt`.  
Copy the **entire** folder to the flash drive. `--onefile` mode is not allowed.

## Dependencies (dev/build only)

- `requests`
- `customtkinter`
- `pyinstaller` (for packaging)

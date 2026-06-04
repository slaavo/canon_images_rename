# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A single-file CLI tool (`rename_and_move_files.py`) that renames and moves camera
photos into date-based folder trees using EXIF capture dates read via `exiftool`,
falling back to the file modification time when EXIF is absent. All logic lives in
that one module; `tests/` holds the pytest suite.

## Commands

```bash
# Dev dependencies (pytest, pytest-cov) — installs the project editable
pip install -e ".[dev]"

# Full test suite (with coverage)
pytest
pytest --cov --cov-report=term-missing

# A single file / class / test
pytest tests/test_plan_moves.py
pytest tests/test_plan_moves.py::TestPlanMoves::test_jpeg_routed_to_orig

# Run the tool (needs exiftool on PATH)
./rename_and_move_files.py -d /path/to/photos   # dry-run preview
```

`exiftool` is a runtime dependency (not a pip package):
`sudo apt install libimage-exiftool-perl` or `brew install exiftool`. Fresh web
containers have neither exiftool nor pytest — `.claude/hooks/session-start.sh` (a
SessionStart hook) installs both automatically. The test suite mocks
`subprocess.run`, so tests pass even without a real exiftool.

## Architecture

`process_files()` orchestrates a pipeline, each stage a separately testable
function:

1. `find_files()` — `os.scandir()` for supported extensions (no recursion),
   sorted case-insensitively.
2. `get_exif_dates()` — one `exiftool` call per batch of `EXIFTOOL_BATCH_SIZE`
   files (batching keeps argv under the OS `ARG_MAX`); `_run_exiftool_batch()`
   parses the tab-separated output and prefers DateTimeOriginal over CreateDate.
3. `plan_moves()` — **pure** routing function (no I/O except the mtime fallback).
   Decides each file's destination folder and new name. Keep it pure so routing
   stays unit-testable without mocks.
4. `ensure_folders_exist()` — pre-creates all date folders and their subfolders.
5. `UniqueFilenameGenerator` — resolves name collisions (`_2`, `_3`, …) against
   both on-disk files and names already allocated this run. Runs sequentially
   before the parallel moves.
6. `move_single_file()` via `ThreadPoolExecutor` — `os.rename` with a
   `shutil.move` fallback for cross-device moves. Stateless and thread-safe.

`InterruptHandler` (context manager) installs a SIGINT handler that only sets a
flag; the move loop checks it and cancels not-yet-started tasks. Output naming is
`YYYY_MM_DD_HHMMSS_<original-name>.<ext>` inside `YYYY_MM_DD/` date folders.

## Conventions & gotchas

- **The `!jpg` / `!orig` folder layout is intentional — do not "fix" it.** JPEGs
  always go to `<date>/!orig/`; RAW stays in the date-folder root (or `!orig/`
  with `-r`). `<date>/!jpg/` is created on purpose and left **empty** — it is
  reserved for an external JPEG-processing tool. Don't reroute JPEGs or drop the
  `!jpg/` creation.
- `DEFAULT_WORKERS` (currently 12) is mirrored in prose: the module docstring,
  `README.md`, and the comment beside the constant. Change all of them together.
- `__version__` in `rename_and_move_files.py` is hand-synced with the version in
  `pyproject.toml`.
- `--dry-run` must stay fully side-effect-free: no folders created, no moves.
- No linter is configured; the bar is a green `pytest` run.
- `REVIEW.md` is a running log of review rounds — append a new section rather
  than rewriting past ones.

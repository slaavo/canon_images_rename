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

1. `find_files()` — `os.scandir()` for supported extensions (no recursion,
   symlinks skipped), sorted case-insensitively. Returns plain `Path`s and
   does **no** per-file `stat`: on POSIX `is_file()`/`is_symlink()` come from
   `d_type`, whereas `DirEntry.stat()` is a real syscall. Raises `ScanError`
   (→ exit 1) if the folder cannot be read.
2. `get_exif_dates()` — groups files by the exiftool `-fast` level their
   container allows (`-fast2` for JPEG/TIFF-based RAW, `-fast` for the
   QuickTime-backed formats in `QUICKTIME_EXTENSIONS`, i.e. CR3), then runs one
   exiftool call per batch of `EXIFTOOL_BATCH_SIZE` files. File lists go to
   exiftool on stdin (`-@ -`), so argv size is never an issue; batching only
   bounds per-process work, and batches run in parallel capped at
   `EXIFTOOL_MAX_PARALLEL`. `_run_exiftool_batch()` parses the tab-separated
   output and prefers DateTimeOriginal over CreateDate. A timeout, a
   signal-killed exiftool, or a non-zero exit with no output raises
   `ExifToolError`; `process_files()` then aborts **before moving anything**
   (dates are unknown, not absent — no mtime fallback). Per file, the result
   dict carries a status: a file exiftool could open has an entry (its date,
   or `None` when it has no date tag → legitimate mtime fallback); a file
   exiftool could **not** open prints no output row and stays **absent** →
   `plan_moves()` reports it as unreadable (an error; the file is left in
   place, never dated by mtime).
3. `get_mtime_dates()` — the only per-file `stat`, called by
   `process_files()` with exactly the files exiftool inspected and found no
   date for (an explicit `None` in `file_dates`); files with EXIF and
   unreadable files are never stat'ed.
4. `plan_moves()` — **pure** routing function (no I/O; the mtime fallback
   reads the pre-fetched `mtime_dates`). Decides each file's destination
   folder and new name. Keep it pure so routing stays unit-testable without
   mocks.
5. `ensure_folders_exist()` — pre-creates all date folders and their subfolders.
6. `UniqueFilenameGenerator` — resolves name collisions (`_2`, `_3`, …) against
   both on-disk files and names already allocated this run. Runs sequentially
   before the parallel moves.
7. `move_single_file()` via `ThreadPoolExecutor` — `_move_no_clobber()`:
   `os.link` + `os.unlink` (atomic, fails if the destination exists), an
   `O_EXCL` placeholder + `os.replace` on filesystems without hard links
   (FAT/exFAT), and an exclusive-create copy for cross-device moves. A
   destination is **never** overwritten; a late collision is reported as an
   error, and a failed move never leaves a destination behind (the link/copy
   is rolled back if the source cannot be removed). Stateless and thread-safe.

`InterruptHandler` (context manager) installs a SIGINT handler that only sets a
flag; `process_files()` checks it right after the EXIF scan (before any folder
is created) and the move loop checks it to cancel not-yet-started tasks. Output naming is
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
- **Moves must never replace an existing destination.** Don't reintroduce
  `os.rename`/`shutil.move` in the move path — `os.rename` silently overwrites
  on POSIX and `shutil.move` moves *into* a same-named directory. Collision
  checks in `UniqueFilenameGenerator` count every directory entry, not just
  files, for the same reason.
- An exiftool failure is not "no EXIF": never let a timeout or killed exiftool
  degrade into mtime-based filing. `ExifToolError` must abort the run. The same
  holds per file: "absent from `file_dates`" means *not inspected* — only an
  explicit `None` entry may fall back to mtime.
- **Never `stat` every file in the scan.** The mtime is needed only for the
  (usually few) files without an EXIF date; on a NAS each `stat` is a network
  round-trip. Keep `find_files()` stat-free and fetch mtimes lazily through
  `get_mtime_dates()`.
- **Never read CR3 with exiftool `-fast2` (or higher).** CR3 is a QuickTime
  container and `-fast2` stops parsing at the `mdat` atom, so a file whose
  `moov` sits after the media data loses its date and gets silently filed by
  mtime. `QUICKTIME_EXTENSIONS` keeps those on `-fast`; `-fast2` is only safe
  for JPEG and TIFF-based RAW.
- No linter is configured; the bar is a green `pytest` run.
- `REVIEW.md` is a running log of review rounds — append a new section rather
  than rewriting past ones.

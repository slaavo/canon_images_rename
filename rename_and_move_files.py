#!/usr/bin/env python3
"""
Script: rename_and_move_files.py
Description: Fast batch rename and organize photos by EXIF date.

Supported formats:
- RAW: CR3, DNG, ARW (Sony), NEF (Nikon), ORF (Olympus), RAF (Fuji), RW2 (Panasonic)
- JPEG: JPG, JPEG

Requires: Python 3.10+, exiftool
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime as dt
from pathlib import Path
from types import FrameType
from typing import NamedTuple

# Type alias for signal handlers
SignalHandler = Callable[[int, FrameType | None], None] | int | None

# RAW and JPEG extensions (lowercase)
RAW_EXTENSIONS: frozenset[str] = frozenset({".cr3", ".dng", ".arw", ".nef", ".orf", ".raf", ".rw2"})
JPEG_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg"})
ALL_EXTENSIONS: frozenset[str] = RAW_EXTENSIONS | JPEG_EXTENSIONS

# Date format pattern for validation
DATE_PATTERN = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{6}$")

# Timeout for exiftool subprocess (seconds)
EXIFTOOL_TIMEOUT = 300

# Max number of files per single exiftool invocation.
# Prevents hitting OS ARG_MAX (~2 MB on Linux) with long paths.
EXIFTOOL_BATCH_SIZE = 5000

# Default number of parallel workers for file operations.
# 8 is a good default for SSD; use 1-2 for HDD, 8-16 for NVMe.
DEFAULT_WORKERS = 8

# Hard upper limit for parallel workers
MAX_WORKERS = 64


class FileInfo(NamedTuple):
    """Metadata for a single file to be processed."""
    path: Path
    datetime_str: str
    new_filename: str
    dest_folder: Path


class ColorFormatter(logging.Formatter):
    """Custom logging formatter with ANSI color codes for console output."""

    COLORS = {
        logging.DEBUG: "\033[0;37m",    # Gray
        logging.INFO: "\033[0;32m",     # Green
        logging.WARNING: "\033[1;33m",  # Yellow
        logging.ERROR: "\033[0;31m",    # Red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # Shallow copy — we only modify levelname (immutable string replacement)
        record_copy = copy.copy(record)
        color = self.COLORS.get(record_copy.levelno, self.RESET)
        record_copy.levelname = f"{color}[{record_copy.levelname}]{self.RESET}"
        return super().format(record_copy)


def setup_logging(verbose: bool = False) -> None:
    """Configure the photo_organizer logger. Safe to call multiple times."""
    logger = logging.getLogger("photo_organizer")

    # Clear existing handlers to prevent duplicates on re-configuration
    logger.handlers.clear()

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)


# Initialize logger (will be reconfigured if --verbose is passed)
setup_logging()
log = logging.getLogger("photo_organizer")


class InterruptHandler:
    """Context manager for graceful Ctrl+C handling during file operations."""

    def __init__(self) -> None:
        self.interrupted = False
        self.processed_count = 0
        self._original_handler: SignalHandler = signal.SIG_DFL
        self._entered = False

    def __enter__(self) -> InterruptHandler:
        self._original_handler = signal.signal(signal.SIGINT, self._handler)
        self._entered = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._entered:
            signal.signal(signal.SIGINT, self._original_handler)

    def _handler(self, signum: int, frame: FrameType | None) -> None:
        self.interrupted = True
        print()  # Newline after progress bar
        log.warning("Interrupt received. Finishing current operation...")


def check_exiftool() -> bool:
    """Check if exiftool is installed and reachable."""
    try:
        subprocess.run(
            ["exiftool", "-ver"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return True
    except subprocess.TimeoutExpired:
        log.error("exiftool check timed out")
        return False
    except (subprocess.CalledProcessError, FileNotFoundError):
        log.error("exiftool is not installed")
        log.info("On Ubuntu/Debian: sudo apt install libimage-exiftool-perl")
        log.info("On macOS: brew install exiftool")
        log.info("On Windows: https://exiftool.org")
        return False


def validate_date(date_str: str | None) -> str | None:
    """Validate date string matches the YYYY_MM_DD_HHMMSS format."""
    if date_str and DATE_PATTERN.match(date_str):
        return date_str
    return None


def _run_exiftool_batch(batch: list[Path]) -> dict[str, str]:
    """
    Run exiftool on a single batch of files.

    Returns a dict mapping filename -> formatted date string.
    """
    results: dict[str, str] = {}

    try:
        # -d (date format) must come before the tags it applies to
        result = subprocess.run(
            [
                "exiftool", "-T",
                "-d", "%Y_%m_%d_%H%M%S",
                "-filename", "-DateTimeOriginal", "-CreateDate",
            ] + [str(f) for f in batch],
            capture_output=True,
            text=True,
            timeout=EXIFTOOL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log.error(f"exiftool timed out after {EXIFTOOL_TIMEOUT} seconds")
        return {}

    # Log any stderr output (warnings, errors from exiftool)
    if result.stderr.strip():
        for line in result.stderr.strip().split("\n"):
            log.debug(f"exiftool: {line}")

    # Parse tab-separated output: filename \t DateTimeOriginal \t CreateDate
    if not result.stdout.strip():
        return results

    for line in result.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) < 2:
            continue

        # exiftool may return a full path; extract the filename only
        filename = Path(parts[0]).name

        date_original = validate_date(parts[1].strip())
        date_create = validate_date(parts[2].strip()) if len(parts) >= 3 else None

        # Prefer DateTimeOriginal, fall back to CreateDate
        date_value = date_original or date_create
        if date_value:
            results[filename] = date_value

    return results


def get_exif_dates(files: list[Path]) -> dict[str, str]:
    """
    Get dates for all files via exiftool.

    Splits into batches of EXIFTOOL_BATCH_SIZE to stay within
    OS argument length limits (ARG_MAX).

    Returns a dict mapping filename -> formatted date string.
    """
    if not files:
        return {}

    file_dates: dict[str, str] = {}

    for i in range(0, len(files), EXIFTOOL_BATCH_SIZE):
        batch = files[i : i + EXIFTOOL_BATCH_SIZE]
        file_dates.update(_run_exiftool_batch(batch))

    return file_dates


def get_file_mod_date(file: Path) -> str | None:
    """Get the file modification date as a formatted string (fallback)."""
    try:
        mtime = file.stat().st_mtime
        return dt.fromtimestamp(mtime).strftime("%Y_%m_%d_%H%M%S")
    except OSError:
        return None


def find_files(input_folder: Path) -> list[Path]:
    """
    Find all supported image files in the given folder.

    Uses os.scandir() for efficiency (cached stat results).
    """
    files: list[Path] = []

    try:
        with os.scandir(input_folder) as entries:
            for entry in entries:
                # entry.is_file() uses cached stat from scandir
                _, ext = os.path.splitext(entry.name)
                if entry.is_file() and ext.lower() in ALL_EXTENSIONS:
                    files.append(Path(entry.path))
    except PermissionError as e:
        log.error(f"Permission denied: {e}")
        return []
    except OSError as e:
        log.error(f"Error reading directory: {e}")
        return []

    # Sort for deterministic order (casefold for better Unicode handling)
    files.sort(key=lambda f: f.name.casefold())
    return files


class UniqueFilenameGenerator:
    """
    Generates unique filenames by tracking both existing files on disk
    and names allocated during the current session (for dry-run accuracy).
    """

    def __init__(self) -> None:
        # Cache of existing files per folder: folder -> set of filenames
        self._existing_cache: dict[Path, set[str]] = {}
        # Names allocated in this session (prevents collisions in dry-run)
        self._allocated: dict[Path, set[str]] = {}

    def _get_existing(self, folder: Path) -> set[str]:
        """Get or cache existing filenames in the given folder."""
        if folder not in self._existing_cache:
            existing: set[str] = set()
            try:
                with os.scandir(folder) as entries:
                    for entry in entries:
                        if entry.is_file():
                            existing.add(entry.name)
            except OSError:
                # Folder may not exist yet (e.g., dry-run) or permission denied
                pass
            self._existing_cache[folder] = existing
        return self._existing_cache[folder]

    def _get_allocated(self, folder: Path) -> set[str]:
        """Get the set of allocated names for the given folder."""
        if folder not in self._allocated:
            self._allocated[folder] = set()
        return self._allocated[folder]

    def generate(self, dest_folder: Path, base_filename: str) -> str:
        """
        Generate a unique filename, checking both existing and allocated names.

        If a collision is found, appends _2, _3, ... up to _99999.
        Example: IMG_001.CR3 -> IMG_001_2.CR3 if IMG_001.CR3 already exists.
        """
        existing = self._get_existing(dest_folder)
        allocated = self._get_allocated(dest_folder)

        if base_filename not in existing and base_filename not in allocated:
            allocated.add(base_filename)
            return base_filename

        # Split into stem and suffix: "name.ext", "name", or ".hidden"
        dot_pos = base_filename.rfind(".")
        if dot_pos > 0:
            stem = base_filename[:dot_pos]
            suffix = base_filename[dot_pos:]
        else:
            stem = base_filename
            suffix = ""

        counter = 2
        while counter <= 99999:
            new_filename = f"{stem}_{counter}{suffix}"
            if new_filename not in existing and new_filename not in allocated:
                allocated.add(new_filename)
                return new_filename
            counter += 1

        log.error(f"Too many duplicates for {base_filename}")
        fallback = f"{stem}_{counter}{suffix}"
        allocated.add(fallback)
        return fallback


def print_progress(current: int, total: int, update_interval: int = 1) -> None:
    """
    Print a progress bar to stdout.

    Only updates every ``update_interval`` files (or at 100%) to reduce I/O.
    """
    if current != total and current % update_interval != 0:
        return

    pct = current * 100 // total
    filled = min(pct // 5, 20)
    bar = "=" * filled + (">" if filled < 20 else "")
    print(f"\rProgress: {pct:3d}% [{bar:<20}] {current}/{total}", end="", flush=True)


def ensure_folders_exist(output_folder: Path, date_folders: set[str]) -> None:
    """Pre-create all date folders and their subfolders in batch."""
    for date_folder in date_folders:
        date_path = output_folder / date_folder
        date_path.mkdir(parents=True, exist_ok=True)
        (date_path / "!jpg").mkdir(exist_ok=True)
        (date_path / "!orig").mkdir(exist_ok=True)


class MoveResult(NamedTuple):
    """Result of a single file move operation."""
    success: bool
    source_name: str
    dest_path: Path | None = None
    error: str | None = None
    is_duplicate: bool = False


def move_single_file(
    source: Path,
    dest_path: Path,
    is_duplicate: bool,
) -> MoveResult:
    """
    Move a single file from source to dest_path.

    Tries os.rename first (instant on same filesystem), falls back to
    shutil.move for cross-device moves. Designed to be called from a
    thread pool — each invocation is independent with no shared mutable state.
    """
    try:
        try:
            os.rename(source, dest_path)
        except OSError:
            # Cross-device move — fall back to copy + delete
            shutil.move(source, dest_path)

        return MoveResult(
            success=True,
            source_name=source.name,
            dest_path=dest_path,
            is_duplicate=is_duplicate,
        )

    except (OSError, shutil.Error) as e:
        return MoveResult(
            success=False,
            source_name=source.name,
            error=str(e),
        )


def validate_paths(input_folder: Path, output_folder: Path) -> bool:
    """
    Validate that input and output paths are safe to use together.

    Returns False if the output folder is inside the input folder
    (which could cause infinite loops).
    """
    try:
        input_resolved = input_folder.resolve()
        output_resolved = output_folder.resolve()

        # Same folder is OK — files will be moved into subfolders
        if output_resolved == input_resolved:
            return True

        # Check if output is a subfolder of input
        try:
            output_resolved.relative_to(input_resolved)
            # If we get here, output IS inside input
            log.error("Output folder cannot be inside input folder")
            log.error(f"  Input:  {input_resolved}")
            log.error(f"  Output: {output_resolved}")
            return False
        except ValueError:
            # Not relative — safe
            return True

    except OSError as e:
        log.error(f"Error validating paths: {e}")
        return False


def plan_moves(
    files: list[Path],
    file_dates: dict[str, str],
    output_folder: Path,
    move_raw_to_orig: bool,
) -> tuple[list[FileInfo], set[str], int, int]:
    """
    Build FileInfo list and collect date folders.

    Pure function — no I/O except get_file_mod_date fallback.

    Returns:
        (file_infos, date_folders, fallback_count, skipped_count)
    """
    file_infos: list[FileInfo] = []
    date_folders: set[str] = set()
    skipped_count = 0
    fallback_count = 0

    for file in files:
        datetime_str = file_dates.get(file.name)
        used_fallback = False

        if not datetime_str:
            datetime_str = get_file_mod_date(file)
            if datetime_str:
                used_fallback = True
                fallback_count += 1
            else:
                log.warning(f"No date for: {file.name} (skipping)")
                skipped_count += 1
                continue

        if used_fallback:
            log.debug(f"Using file modification date for: {file.name}")

        # Build destination paths
        date_folder = datetime_str[:10]
        date_folders.add(date_folder)
        date_folder_path = output_folder / date_folder

        # Route file based on extension
        ext_lower = file.suffix.lower()
        if ext_lower in JPEG_EXTENSIONS:
            dest_folder = date_folder_path / "!orig"
        elif move_raw_to_orig:
            dest_folder = date_folder_path / "!orig"
        else:
            dest_folder = date_folder_path

        base_filename = f"{datetime_str}_{file.stem}{file.suffix}"

        file_infos.append(FileInfo(
            path=file,
            datetime_str=datetime_str,
            new_filename=base_filename,
            dest_folder=dest_folder,
        ))

    return file_infos, date_folders, fallback_count, skipped_count


def process_files(
    input_folder: Path,
    output_folder: Path,
    move_raw_to_orig: bool,
    dry_run: bool,
    interrupt_handler: InterruptHandler,
    workers: int = DEFAULT_WORKERS,
) -> tuple[int, int]:
    """
    Process and organize photo files.

    Uses a thread pool for parallel file moves (optimized for SSD).

    Returns:
        A tuple of (success_count, error_count).
    """
    files = find_files(input_folder)

    if not files:
        log.warning(f"No supported files found in: {input_folder}")
        return 0, 0

    log.info(f"Found {len(files)} files to process")
    if dry_run:
        log.warning("DRY RUN MODE — no changes will be made")

    # Get all EXIF dates via exiftool (batched if >5000 files)
    log.info("Reading EXIF data...")
    file_dates = get_exif_dates(files)
    log.info(f"Got EXIF dates for {len(file_dates)}/{len(files)} files")

    # Prepare file info and collect unique date folders
    log.info("Preparing file operations...")
    file_infos, date_folders, fallback_count, skipped_count = plan_moves(
        files, file_dates, output_folder, move_raw_to_orig,
    )

    if fallback_count > 0:
        log.warning(f"Using file modification date for {fallback_count} files (no EXIF data)")

    if skipped_count > 0:
        log.warning(f"Skipping {skipped_count} files without any date metadata")

    if not file_infos:
        log.warning("No files to process after filtering")
        return 0, 0

    # Pre-create all folders (skip in dry-run)
    if not dry_run:
        log.info(f"Creating {len(date_folders)} date folders...")
        ensure_folders_exist(output_folder, date_folders)

    # Generate all unique filenames BEFORE moving (must be sequential
    # to avoid duplicate name collisions)
    log.info("Resolving filename conflicts...")
    filename_gen = UniqueFilenameGenerator()

    move_tasks: list[tuple[Path, Path, bool]] = []

    for info in file_infos:
        unique_filename = filename_gen.generate(info.dest_folder, info.new_filename)
        is_duplicate = (unique_filename != info.new_filename)
        dest_path = info.dest_folder / unique_filename
        move_tasks.append((info.path, dest_path, is_duplicate))

    total = len(move_tasks)

    # Dry-run: just print what would happen
    if dry_run:
        for source, dest_path, is_duplicate in move_tasks:
            suffix = " (renamed: duplicate)" if is_duplicate else ""
            print(f"  {source.name} -> {dest_path}{suffix}")
        return total, 0

    # Move files in parallel
    log.info(f"Moving files (using {workers} workers)...")

    success_count = 0
    error_count = 0
    completed = 0

    # Throttle progress updates to ~100 updates total
    update_interval = max(1, total // 100)

    def update_progress() -> None:
        """Update progress bar. Called from main thread only."""
        nonlocal completed
        completed += 1
        print_progress(completed, total, update_interval)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_task = {
            executor.submit(move_single_file, source, dest, is_dup): (source, dest, is_dup)
            for source, dest, is_dup in move_tasks
        }

        try:
            for future in concurrent.futures.as_completed(future_to_task):
                result = future.result()
                update_progress()

                if result.success:
                    success_count += 1
                    interrupt_handler.processed_count += 1
                    if result.is_duplicate and result.dest_path is not None:
                        log.debug(f"Renamed duplicate: {result.source_name} -> {result.dest_path.name}")
                else:
                    log.error(f"\n  Failed: {result.source_name} ({result.error})")
                    error_count += 1

                # Check for interrupt AFTER processing the current result.
                # cancel() only affects tasks not yet started by the pool.
                if interrupt_handler.interrupted:
                    pending = sum(1 for f in future_to_task if not f.done())
                    if pending > 0:
                        log.warning(f"Cancelling {pending} pending tasks...")
                    for f in future_to_task:
                        f.cancel()
                    break

        except KeyboardInterrupt:
            # Fallback in case the signal handler did not catch it
            log.warning("Interrupted by user")
            interrupt_handler.interrupted = True

    # Executor __exit__ waits for running tasks to finish
    if interrupt_handler.interrupted:
        log.info(f"Stopped. Processed: {success_count}, Errors: {error_count}")

    # Clear progress line
    print()
    return success_count, error_count


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fast batch rename and organize photos by date",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Process current directory
  %(prog)s /path/to/photos              # Process specific folder
  %(prog)s -o /output /path/to/photos   # Different output folder
  %(prog)s -d /path/to/photos           # Dry run (preview changes)
  %(prog)s -r /path/to/photos           # Move RAW files to !orig subfolder
  %(prog)s -w 8 /path/to/photos         # Use 8 parallel workers (faster on SSD)

Supported formats:
  RAW:  CR3, DNG, ARW, NEF, ORF, RAF, RW2
  JPEG: JPG, JPEG
        """,
    )
    parser.add_argument(
        "input_folder",
        nargs="?",
        default=".",
        help="Input folder (default: current directory)",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="DIR",
        help="Output folder (default: same as input)",
    )
    parser.add_argument(
        "-r", "--raw-subfolder",
        action="store_true",
        help="Move RAW files (CR3/DNG/etc.) to !orig subfolder",
    )
    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        metavar="N",
        help=f"Number of parallel workers (default: {DEFAULT_WORKERS}, range: 1-{MAX_WORKERS})",
    )

    args = parser.parse_args()

    # Validate workers range
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.workers > MAX_WORKERS:
        parser.error(f"--workers must be at most {MAX_WORKERS}")

    # Reconfigure logging if verbose (handlers are cleared to prevent duplicates)
    if args.verbose:
        setup_logging(verbose=True)

    # resolve() with strict=False (default since 3.6) doesn't raise on missing paths
    input_folder = Path(args.input_folder).resolve(strict=False)
    output_folder = Path(args.output).resolve(strict=False) if args.output else input_folder

    if not input_folder.is_dir():
        log.error(f"Input folder does not exist: {input_folder}")
        return 1

    if not check_exiftool():
        return 1

    if not validate_paths(input_folder, output_folder):
        return 1

    output_folder.mkdir(parents=True, exist_ok=True)

    with InterruptHandler() as interrupt_handler:
        success, errors = process_files(
            input_folder,
            output_folder,
            args.raw_subfolder,
            args.dry_run,
            interrupt_handler,
            workers=args.workers,
        )

        if interrupt_handler.interrupted:
            return 130  # Standard Ctrl+C exit code

        log.info(f"Done! Processed: {success}, Errors: {errors}")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

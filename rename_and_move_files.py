#!/usr/bin/env python3
"""
Script: rename_and_move_files.py
Description: Fast batch rename and organize photos by date

Supported formats:
- RAW: CR3, DNG, ARW (Sony), NEF (Nikon), ORF (Olympus), RAF (Fuji), RW2 (Panasonic)
- JPEG: JPG, JPEG

Requires: Python 3.8+, exiftool
"""

from __future__ import annotations

import argparse
import copy
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
from datetime import datetime as dt
from pathlib import Path
from types import FrameType
from typing import Callable, Dict, FrozenSet, List, NamedTuple, Optional, Set, Tuple, Union

# Type alias for signal handlers (compatible with Python 3.8+)
# signal.Handlers was added in Python 3.10, so we use Callable for compatibility
SignalHandler = Union[Callable[[int, Optional[FrameType]], None], int, None]

# RAW and JPEG extensions (lowercase) - compatible with Python 3.8
RAW_EXTENSIONS: FrozenSet[str] = frozenset({".cr3", ".dng", ".arw", ".nef", ".orf", ".raf", ".rw2"})
JPEG_EXTENSIONS: FrozenSet[str] = frozenset({".jpg", ".jpeg"})
ALL_EXTENSIONS: FrozenSet[str] = RAW_EXTENSIONS.union(JPEG_EXTENSIONS)

# Date format pattern for validation
DATE_PATTERN = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{6}$")

# Timeout for exiftool subprocess (seconds)
EXIFTOOL_TIMEOUT = 300


class FileInfo(NamedTuple):
    """Metadata for a single file."""
    path: Path
    datetime_str: str
    new_filename: str
    dest_folder: Path


class ColorFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""

    COLORS = {
        logging.DEBUG: "\033[0;37m",    # Gray
        logging.INFO: "\033[0;32m",     # Green
        logging.WARNING: "\033[1;33m",  # Yellow
        logging.ERROR: "\033[0;31m",    # Red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # Shallow copy is sufficient - we only modify levelname (immutable string)
        record_copy = copy.copy(record)
        color = self.COLORS.get(record_copy.levelno, self.RESET)
        record_copy.levelname = f"{color}[{record_copy.levelname}]{self.RESET}"
        return super().format(record_copy)


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return logger. Safe to call multiple times."""
    logger = logging.getLogger("photo_organizer")
    
    # Clear existing handlers to prevent duplicates
    logger.handlers.clear()
    
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)

    return logger


# Initialize logger (will be reconfigured if --verbose)
log = setup_logging()


class InterruptHandler:
    """Context manager for graceful Ctrl+C handling."""
    
    def __init__(self) -> None:
        self.interrupted = False
        self.processed_count = 0
        self._original_handler: SignalHandler = signal.SIG_DFL
        self._entered = False
    
    def __enter__(self) -> "InterruptHandler":
        self._original_handler = signal.signal(signal.SIGINT, self._handler)
        self._entered = True
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._entered:
            signal.signal(signal.SIGINT, self._original_handler)
        # Implicit return None (don't suppress exceptions)
    
    def _handler(self, signum: int, frame: Optional[FrameType]) -> None:
        self.interrupted = True
        print()  # Newline after progress bar
        log.warning("Interrupt received. Finishing current operation...")


def check_exiftool() -> bool:
    """Check if exiftool is installed."""
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


def validate_date(date_str: Optional[str]) -> Optional[str]:
    """Validate date string format YYYY_MM_DD_HHMMSS."""
    if date_str and DATE_PATTERN.match(date_str):
        return date_str
    return None


def get_exif_dates(files: List[Path]) -> Dict[str, str]:
    """
    Get dates for all files in a single exiftool call.

    Fetches both DateTimeOriginal and CreateDate, uses DateTimeOriginal
    if available, falls back to CreateDate.
    
    Returns dict mapping filename -> formatted date string.
    """
    if not files:
        return {}

    file_dates: Dict[str, str] = {}

    try:
        # Get both date fields in one call
        # -d (date format) must come before the tags it affects
        result = subprocess.run(
            [
                "exiftool", "-T",
                "-d", "%Y_%m_%d_%H%M%S",
                "-filename", "-DateTimeOriginal", "-CreateDate"
            ] + [str(f) for f in files],
            capture_output=True,
            text=True,
            timeout=EXIFTOOL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log.error(f"exiftool timed out after {EXIFTOOL_TIMEOUT} seconds")
        return {}

    # Log stderr if present (warnings, errors)
    if result.stderr.strip():
        for line in result.stderr.strip().split("\n"):
            log.debug(f"exiftool: {line}")

    # Parse output: filename \t DateTimeOriginal \t CreateDate
    if not result.stdout.strip():
        return file_dates
        
    for line in result.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) < 2:
            continue
            
        # Extract just filename (exiftool may return full path)
        filename = Path(parts[0]).name
        
        # Get dates from available columns
        # parts[1] is guaranteed to exist (checked above), parts[2] may not
        date_original = validate_date(parts[1].strip())
        date_create = validate_date(parts[2].strip()) if len(parts) >= 3 else None
        
        # Prefer DateTimeOriginal, fallback to CreateDate
        date_value = date_original or date_create
        if date_value:
            file_dates[filename] = date_value

    return file_dates


def get_file_mod_date(file: Path) -> Optional[str]:
    """Get file modification date as fallback."""
    try:
        mtime = file.stat().st_mtime
        return dt.fromtimestamp(mtime).strftime("%Y_%m_%d_%H%M%S")
    except OSError:
        return None


def find_files(input_folder: Path) -> List[Path]:
    """
    Find all supported image files in folder.
    
    Uses os.scandir() for efficiency (cached stat results).
    """
    files: List[Path] = []
    
    try:
        with os.scandir(input_folder) as entries:
            for entry in entries:
                # entry.is_file() uses cached stat from scandir
                # os.path.splitext is faster than creating Path object
                _, ext = os.path.splitext(entry.name)
                if entry.is_file() and ext.lower() in ALL_EXTENSIONS:
                    files.append(Path(entry.path))
    except PermissionError as e:
        log.error(f"Permission denied: {e}")
        return []
    except OSError as e:
        log.error(f"Error reading directory: {e}")
        return []
    
    # Sort for predictable order (casefold for better Unicode handling)
    files.sort(key=lambda f: f.name.casefold())
    return files


class UniqueFilenameGenerator:
    """
    Generates unique filenames, tracking both existing files and 
    newly "allocated" names (for dry-run accuracy).
    """
    
    def __init__(self) -> None:
        # Cache of existing files per folder: folder -> set of filenames
        self._existing_cache: Dict[Path, Set[str]] = {}
        # Track allocated names in this session (for dry-run)
        self._allocated: Dict[Path, Set[str]] = {}
    
    def _get_existing(self, folder: Path) -> Set[str]:
        """Get or cache existing filenames in folder."""
        if folder not in self._existing_cache:
            existing: Set[str] = set()
            try:
                with os.scandir(folder) as entries:
                    for entry in entries:
                        if entry.is_file():
                            existing.add(entry.name)
            except OSError:
                # Folder doesn't exist (e.g., dry-run) or permission denied
                pass
            self._existing_cache[folder] = existing
        return self._existing_cache[folder]
    
    def _get_allocated(self, folder: Path) -> Set[str]:
        """Get allocated names for folder."""
        if folder not in self._allocated:
            self._allocated[folder] = set()
        return self._allocated[folder]
    
    def generate(self, dest_folder: Path, base_filename: str) -> str:
        """
        Generate unique filename, checking both existing and allocated names.
        
        Example: IMG_001.CR3 -> IMG_001_2.CR3 if IMG_001.CR3 exists
        """
        existing = self._get_existing(dest_folder)
        allocated = self._get_allocated(dest_folder)
        
        # Check without creating new set (optimization)
        if base_filename not in existing and base_filename not in allocated:
            allocated.add(base_filename)
            return base_filename
        
        # Parse filename: handle "name.ext", "name", and ".hidden"
        dot_pos = base_filename.rfind(".")
        if dot_pos > 0:  # Normal case: "name.ext"
            stem = base_filename[:dot_pos]
            suffix = base_filename[dot_pos:]
        else:  # No extension or hidden file like ".hidden"
            stem = base_filename
            suffix = ""
        
        counter = 2
        while counter <= 99999:
            new_filename = f"{stem}_{counter}{suffix}"
            if new_filename not in existing and new_filename not in allocated:
                allocated.add(new_filename)
                return new_filename
            counter += 1
        
        # This shouldn't happen in practice - log and return (let move fail)
        log.error(f"Too many duplicates for {base_filename}")
        fallback = f"{stem}_{counter}{suffix}"
        allocated.add(fallback)
        return fallback


def print_progress(current: int, total: int, update_interval: int = 1) -> None:
    """
    Print progress bar. Only updates every `update_interval` files
    or at 100% to reduce I/O.
    """
    # Check cheaper condition first (equality vs modulo)
    if current != total and current % update_interval != 0:
        return
        
    pct = current * 100 // total
    filled = min(pct // 5, 20)
    bar = "=" * filled + (">" if filled < 20 else "")
    print(f"\rProgress: {pct:3d}% [{bar:<20}] {current}/{total}", end="", flush=True)


def ensure_folders_exist(output_folder: Path, date_folders: Set[str]) -> None:
    """Pre-create all date folders and subfolders in batch."""
    for date_folder in date_folders:
        date_path = output_folder / date_folder
        date_path.mkdir(parents=True, exist_ok=True)
        (date_path / "!jpg").mkdir(exist_ok=True)
        (date_path / "!orig").mkdir(exist_ok=True)


def validate_paths(input_folder: Path, output_folder: Path) -> bool:
    """
    Validate that input and output paths are safe to use together.
    
    Returns False if output is inside input (could cause infinite loops).
    """
    try:
        # Resolve to handle symlinks and relative paths
        input_resolved = input_folder.resolve()
        output_resolved = output_folder.resolve()
        
        # Check if output is same as or inside input
        if output_resolved == input_resolved:
            # Same folder is OK - files will be moved to subfolders
            return True
        
        # Check if output is a subfolder of input
        try:
            output_resolved.relative_to(input_resolved)
            # If we get here, output is inside input
            log.error(f"Output folder cannot be inside input folder")
            log.error(f"  Input:  {input_resolved}")
            log.error(f"  Output: {output_resolved}")
            return False
        except ValueError:
            # output is not relative to input - this is fine
            return True
            
    except OSError as e:
        log.error(f"Error validating paths: {e}")
        return False


def process_files(
    input_folder: Path,
    output_folder: Path,
    move_raw_to_orig: bool,
    dry_run: bool,
    interrupt_handler: InterruptHandler,
) -> Tuple[int, int]:
    """
    Process and organize photo files.

    Returns:
        Tuple of (success_count, error_count)
    """
    # Find files
    files = find_files(input_folder)

    if not files:
        log.warning(f"No supported files found in: {input_folder}")
        return 0, 0

    log.info(f"Found {len(files)} files to process")
    if dry_run:
        log.warning("DRY RUN MODE - no changes will be made")

    # Get all EXIF dates in single batch call
    log.info("Reading EXIF data (single batch call)...")
    file_dates = get_exif_dates(files)
    log.info(f"Got EXIF dates for {len(file_dates)}/{len(files)} files")

    # Prepare file info and collect unique date folders
    log.info("Preparing file operations...")
    file_infos: List[FileInfo] = []
    date_folders: Set[str] = set()
    skipped_count = 0
    fallback_count = 0

    for file in files:
        # Get datetime from EXIF or fallback
        datetime_str = file_dates.get(file.name)
        used_fallback = False

        if not datetime_str:
            datetime_str = get_file_mod_date(file)
            if datetime_str:
                used_fallback = True
                fallback_count += 1
            else:
                log.warning(f"No date for: {file.name} (will skip)")
                skipped_count += 1
                continue

        if used_fallback:
            log.debug(f"Using file modification date for: {file.name}")

        # Build paths
        date_folder = datetime_str[:10]
        date_folders.add(date_folder)
        date_folder_path = output_folder / date_folder

        # Determine destination based on file type
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

    if fallback_count > 0:
        log.warning(f"Using file modification date for {fallback_count} files (no EXIF data)")

    if skipped_count > 0:
        log.warning(f"Skipping {skipped_count} files without any date metadata")

    if not file_infos:
        log.warning("No files to process after filtering")
        return 0, skipped_count

    # Pre-create all folders (skip in dry-run)
    if not dry_run:
        log.info(f"Creating {len(date_folders)} date folders...")
        ensure_folders_exist(output_folder, date_folders)

    # Process files
    log.info("Moving files...")
    success_count = 0
    error_count = skipped_count
    total = len(file_infos)
    
    # Update progress less frequently for large batches
    update_interval = max(1, total // 100)
    
    # Unique filename generator (tracks allocated names for dry-run accuracy)
    filename_gen = UniqueFilenameGenerator()

    for i, info in enumerate(file_infos, 1):
        # Check for interrupt
        if interrupt_handler.interrupted:
            log.warning(f"Stopping early. Processed {success_count} files.")
            break
            
        print_progress(i, total, update_interval)
        
        # Generate unique filename (works correctly for both dry-run and real mode)
        unique_filename = filename_gen.generate(info.dest_folder, info.new_filename)
        is_duplicate = (unique_filename != info.new_filename)
        dest_path = info.dest_folder / unique_filename

        if dry_run:
            suffix = " (renamed: duplicate)" if is_duplicate else ""
            print(f"\n  {info.path.name} -> {dest_path}{suffix}")
            success_count += 1
            interrupt_handler.processed_count += 1
        else:
            try:
                # Verify source file still exists
                if not info.path.exists():
                    log.error(f"\n  Source file missing: {info.path.name}")
                    error_count += 1
                    continue
                    
                if is_duplicate:
                    log.debug(f"Renamed duplicate: {info.new_filename} -> {unique_filename}")

                shutil.move(str(info.path), str(dest_path))
                success_count += 1
                interrupt_handler.processed_count += 1

            except (OSError, shutil.Error) as e:
                log.error(f"\n  Failed: {info.path.name} ({e})")
                error_count += 1

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

    args = parser.parse_args()

    # Reconfigure logging if verbose (handlers cleared to prevent duplicates)
    global log
    if args.verbose:
        log = setup_logging(verbose=True)

    # resolve() with strict=False (default in 3.9+) doesn't raise on missing paths
    input_folder = Path(args.input_folder).resolve(strict=False)
    output_folder = Path(args.output).resolve(strict=False) if args.output else input_folder

    if not input_folder.is_dir():
        log.error(f"Input folder does not exist: {input_folder}")
        return 1

    if not check_exiftool():
        return 1
    
    # Validate path relationship
    if not validate_paths(input_folder, output_folder):
        return 1

    output_folder.mkdir(parents=True, exist_ok=True)

    # Use interrupt handler as context manager
    with InterruptHandler() as interrupt_handler:
        success, errors = process_files(
            input_folder,
            output_folder,
            args.raw_subfolder,
            args.dry_run,
            interrupt_handler,
        )

        if interrupt_handler.interrupted:
            log.info(f"Interrupted. Processed: {success}, Errors: {errors}")
            return 130  # Standard Ctrl+C exit code
        
        log.info(f"Done! Processed: {success}, Errors: {errors}")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

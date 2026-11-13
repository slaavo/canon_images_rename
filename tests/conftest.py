"""Shared pytest fixtures for photo organizer tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


# WinError 1314: creating symlinks needs Developer Mode or admin rights
_ERROR_PRIVILEGE_NOT_HELD = 1314


def _symlink_not_permitted(error: OSError) -> bool:
    return os.name == "nt" and getattr(error, "winerror", None) == _ERROR_PRIVILEGE_NOT_HELD


def make_file_symlink_or_skip(link: Path, target: str | Path) -> None:
    """Create a file symlink, or skip the test where the OS does not allow it."""
    try:
        link.symlink_to(target)
    except OSError as e:
        if _symlink_not_permitted(e):
            pytest.skip("creating symlinks needs Developer Mode or admin rights on Windows")
        raise


def make_dir_link(link: Path, target: Path) -> None:
    """
    Create a directory link to `target`: a symlink, or on Windows without the
    symlink privilege a junction (needs no privilege; resolve() follows both).
    """
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as e:
        if not _symlink_not_permitted(e):
            raise
        import _winapi  # Windows-only stdlib module

        _winapi.CreateJunction(str(target), str(link))


# Sample exiftool tab-separated outputs (reusable test data)
EXIFTOOL_OUTPUT_SINGLE = b"IMG_001.jpg\t2024_01_15_143052\t2024_01_15_143052\n"

EXIFTOOL_OUTPUT_MULTIPLE = (
    b"IMG_001.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
    b"IMG_002.JPG\t2024_01_15_143105\t2024_01_15_143105\n"
    b"IMG_003.cr3\t2024_01_16_091500\t2024_01_16_091500\n"
    b"IMG_004.CR3\t-\t-\n"  # No date
)

EXIFTOOL_OUTPUT_FALLBACK = b"IMG_001.jpg\t-\t2024_01_15_143052\n"


@pytest.fixture
def sample_photos(tmp_path: Path) -> Path:
    """
    Create a temporary directory with sample photo files (empty, no EXIF).

    Covers all supported extensions.
    Returns the path to the directory containing the files.
    """
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()

    # JPEG formats
    (photos_dir / "IMG_001.jpg").touch()
    (photos_dir / "IMG_002.JPG").touch()
    (photos_dir / "IMG_003.jpeg").touch()

    # RAW formats — all supported types
    (photos_dir / "IMG_004.cr3").touch()
    (photos_dir / "IMG_005.CR3").touch()
    (photos_dir / "IMG_006.dng").touch()
    (photos_dir / "IMG_007.arw").touch()
    (photos_dir / "IMG_008.nef").touch()
    (photos_dir / "IMG_009.orf").touch()
    (photos_dir / "IMG_010.raf").touch()
    (photos_dir / "IMG_011.rw2").touch()

    # Should be ignored
    (photos_dir / "document.pdf").touch()
    (photos_dir / "notes.txt").touch()

    return photos_dir

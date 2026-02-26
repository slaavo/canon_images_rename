"""Shared pytest fixtures for photo organizer tests."""

from __future__ import annotations

from pathlib import Path

import pytest


# Sample exiftool tab-separated outputs (reusable test data)
EXIFTOOL_OUTPUT_SINGLE = "IMG_001.jpg\t2024_01_15_143052\t2024_01_15_143052\n"

EXIFTOOL_OUTPUT_MULTIPLE = (
    "IMG_001.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
    "IMG_002.JPG\t2024_01_15_143105\t2024_01_15_143105\n"
    "IMG_003.cr3\t2024_01_16_091500\t2024_01_16_091500\n"
    "IMG_004.CR3\t-\t-\n"  # No date
)

EXIFTOOL_OUTPUT_FALLBACK = "IMG_001.jpg\t-\t2024_01_15_143052\n"


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

"""Shared pytest fixtures for photo organizer tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_photos(tmp_path: Path) -> Path:
    """
    Create a temporary directory with sample photo files (empty, no EXIF).

    Returns the path to the directory containing the files.
    """
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()

    # Create sample files (empty - no actual image data)
    (photos_dir / "IMG_001.jpg").touch()
    (photos_dir / "IMG_002.JPG").touch()
    (photos_dir / "IMG_003.cr3").touch()
    (photos_dir / "IMG_004.CR3").touch()
    (photos_dir / "IMG_005.dng").touch()
    (photos_dir / "document.pdf").touch()  # Should be ignored
    (photos_dir / "notes.txt").touch()     # Should be ignored

    return photos_dir


@pytest.fixture
def exiftool_output_single() -> str:
    """Sample exiftool tab-separated output for a single file."""
    return "IMG_001.jpg\t2024_01_15_143052\t2024_01_15_143052\n"


@pytest.fixture
def exiftool_output_multiple() -> str:
    """Sample exiftool tab-separated output for multiple files."""
    return (
        "IMG_001.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        "IMG_002.JPG\t2024_01_15_143105\t2024_01_15_143105\n"
        "IMG_003.cr3\t2024_01_16_091500\t2024_01_16_091500\n"
        "IMG_004.CR3\t-\t-\n"  # No date
    )


@pytest.fixture
def exiftool_output_fallback() -> str:
    """Sample exiftool output with DateTimeOriginal missing, only CreateDate."""
    return "IMG_001.jpg\t-\t2024_01_15_143052\n"

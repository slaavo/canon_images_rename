"""Tests for validation functions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rename_and_move_files import validate_date, validate_paths


class TestValidateDate:
    """Tests for validate_date function."""

    def test_valid_date_format(self):
        """Valid YYYY_MM_DD_HHMMSS format should be returned as-is."""
        assert validate_date("2024_01_15_143052") == "2024_01_15_143052"
        assert validate_date("2000_12_31_235959") == "2000_12_31_235959"
        assert validate_date("1999_01_01_000000") == "1999_01_01_000000"

    def test_invalid_date_formats(self):
        """Invalid formats should return None."""
        # Wrong separators
        assert validate_date("2024-01-15-143052") is None
        assert validate_date("2024/01/15/143052") is None

        # Wrong length
        assert validate_date("2024_01_15_14305") is None
        assert validate_date("2024_01_15_1430522") is None
        assert validate_date("24_01_15_143052") is None

        # Missing parts
        assert validate_date("2024_01_15") is None
        assert validate_date("143052") is None

    def test_empty_and_none(self):
        """Empty string and None should return None."""
        assert validate_date("") is None
        assert validate_date(None) is None

    def test_exiftool_dash_placeholder(self):
        """Exiftool's '-' placeholder for missing date should return None."""
        assert validate_date("-") is None

    def test_whitespace(self):
        """Strings with only whitespace should return None."""
        assert validate_date("   ") is None
        assert validate_date("\t\n") is None


class TestValidatePaths:
    """Tests for validate_paths function."""

    def test_same_folder_is_valid(self, tmp_path: Path):
        """Input and output being the same folder should be valid."""
        assert validate_paths(tmp_path, tmp_path) is True

    def test_different_folders_valid(self, tmp_path: Path):
        """Completely separate input and output folders should be valid."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        assert validate_paths(input_dir, output_dir) is True

    def test_output_inside_input_invalid(self, tmp_path: Path):
        """Output folder inside input folder should be invalid."""
        input_dir = tmp_path / "photos"
        output_dir = input_dir / "organized"
        input_dir.mkdir()
        output_dir.mkdir()

        assert validate_paths(input_dir, output_dir) is False

    def test_input_inside_output_valid(self, tmp_path: Path):
        """Input folder inside output folder should be valid (unusual but OK)."""
        output_dir = tmp_path / "archive"
        input_dir = output_dir / "new_photos"
        output_dir.mkdir()
        input_dir.mkdir()

        assert validate_paths(input_dir, output_dir) is True

    def test_symlink_resolution(self, tmp_path: Path):
        """Symlinks should be resolved before comparison."""
        real_dir = tmp_path / "real"
        real_dir.mkdir()

        link_dir = tmp_path / "link"
        link_dir.symlink_to(real_dir)

        # Same physical location via symlink
        assert validate_paths(real_dir, link_dir) is True

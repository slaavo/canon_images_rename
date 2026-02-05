"""Tests for EXIF date extraction functions."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from rename_and_move_files import (
    get_exif_dates,
    _run_exiftool_batch,
    check_exiftool,
    get_file_mod_date,
)


class TestGetExifDates:
    """Tests for get_exif_dates function."""

    def test_empty_file_list(self):
        """Empty file list should return empty dict."""
        assert get_exif_dates([]) == {}

    def test_parses_single_file(self, exiftool_output_single: str):
        """Parse exiftool output for a single file."""
        mock_result = MagicMock()
        mock_result.stdout = exiftool_output_single
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            files = [Path("/fake/IMG_001.jpg")]
            dates = get_exif_dates(files)

        assert dates == {"IMG_001.jpg": "2024_01_15_143052"}

    def test_parses_multiple_files(self, exiftool_output_multiple: str):
        """Parse exiftool output for multiple files."""
        mock_result = MagicMock()
        mock_result.stdout = exiftool_output_multiple
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            files = [
                Path("/fake/IMG_001.jpg"),
                Path("/fake/IMG_002.JPG"),
                Path("/fake/IMG_003.cr3"),
                Path("/fake/IMG_004.CR3"),
            ]
            dates = get_exif_dates(files)

        assert dates == {
            "IMG_001.jpg": "2024_01_15_143052",
            "IMG_002.JPG": "2024_01_15_143105",
            "IMG_003.cr3": "2024_01_16_091500",
            # IMG_004.CR3 has no date, should be missing
        }
        assert "IMG_004.CR3" not in dates

    def test_prefers_datetime_original_over_create_date(self):
        """DateTimeOriginal should be preferred over CreateDate."""
        mock_result = MagicMock()
        mock_result.stdout = "IMG.jpg\t2024_01_15_100000\t2024_01_15_200000\n"
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            dates = get_exif_dates([Path("/fake/IMG.jpg")])

        assert dates["IMG.jpg"] == "2024_01_15_100000"

    def test_falls_back_to_create_date(self, exiftool_output_fallback: str):
        """When DateTimeOriginal is missing, use CreateDate."""
        mock_result = MagicMock()
        mock_result.stdout = exiftool_output_fallback
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            dates = get_exif_dates([Path("/fake/IMG_001.jpg")])

        assert dates == {"IMG_001.jpg": "2024_01_15_143052"}

    def test_handles_timeout(self):
        """Timeout should return empty dict."""
        import subprocess

        with patch(
            "rename_and_move_files.subprocess.run",
            side_effect=subprocess.TimeoutExpired("exiftool", 300),
        ):
            dates = get_exif_dates([Path("/fake/IMG.jpg")])

        assert dates == {}

    def test_handles_empty_output(self):
        """Empty exiftool output should return empty dict."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            dates = get_exif_dates([Path("/fake/IMG.jpg")])

        assert dates == {}

    def test_batching_large_file_list(self):
        """Files should be processed in batches."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            # Create 7500 fake files (should be 2 batches with EXIFTOOL_BATCH_SIZE=5000)
            files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(7500)]
            get_exif_dates(files)

        # Should have been called twice (2 batches)
        assert mock_run.call_count == 2


class TestCheckExiftool:
    """Tests for check_exiftool function."""

    def test_exiftool_available(self):
        """Return True when exiftool is available."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            assert check_exiftool() is True

    def test_exiftool_not_found(self):
        """Return False when exiftool is not found."""
        with patch(
            "rename_and_move_files.subprocess.run",
            side_effect=FileNotFoundError(),
        ):
            assert check_exiftool() is False

    def test_exiftool_timeout(self):
        """Return False when exiftool check times out."""
        import subprocess

        with patch(
            "rename_and_move_files.subprocess.run",
            side_effect=subprocess.TimeoutExpired("exiftool", 10),
        ):
            assert check_exiftool() is False


class TestGetFileModDate:
    """Tests for get_file_mod_date function."""

    def test_returns_formatted_date(self, tmp_path: Path):
        """Return modification date in correct format."""
        test_file = tmp_path / "test.jpg"
        test_file.touch()

        result = get_file_mod_date(test_file)

        # Should match YYYY_MM_DD_HHMMSS format
        assert result is not None
        assert len(result) == 17
        assert result[4] == "_"
        assert result[7] == "_"
        assert result[10] == "_"

    def test_nonexistent_file_returns_none(self, tmp_path: Path):
        """Return None for nonexistent file."""
        nonexistent = tmp_path / "does_not_exist.jpg"

        result = get_file_mod_date(nonexistent)

        assert result is None

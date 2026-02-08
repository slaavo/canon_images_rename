"""Tests for EXIF date extraction functions."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from rename_and_move_files import (
    _run_exiftool_batch,
    get_exif_dates,
    check_exiftool,
    get_file_mod_date,
    EXIFTOOL_BATCH_SIZE,
)
from tests.conftest import (
    EXIFTOOL_OUTPUT_SINGLE,
    EXIFTOOL_OUTPUT_MULTIPLE,
    EXIFTOOL_OUTPUT_FALLBACK,
)


class TestGetExifDates:
    """Tests for get_exif_dates function."""

    def test_empty_file_list(self):
        """Empty file list should return empty dict."""
        assert get_exif_dates([]) == {}

    def test_parses_single_file(self):
        """Parse exiftool output for a single file."""
        mock_result = MagicMock()
        mock_result.stdout = EXIFTOOL_OUTPUT_SINGLE
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            files = [Path("/fake/IMG_001.jpg")]
            dates = get_exif_dates(files)

        assert dates == {"IMG_001.jpg": "2024_01_15_143052"}

    def test_parses_multiple_files(self):
        """Parse exiftool output for multiple files."""
        mock_result = MagicMock()
        mock_result.stdout = EXIFTOOL_OUTPUT_MULTIPLE
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

    def test_falls_back_to_create_date(self):
        """When DateTimeOriginal is missing, use CreateDate."""
        mock_result = MagicMock()
        mock_result.stdout = EXIFTOOL_OUTPUT_FALLBACK
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            dates = get_exif_dates([Path("/fake/IMG_001.jpg")])

        assert dates == {"IMG_001.jpg": "2024_01_15_143052"}

    def test_handles_timeout(self):
        """Timeout should return empty dict."""
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
        """Files should be processed in batches of EXIFTOOL_BATCH_SIZE."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""

        file_count = EXIFTOOL_BATCH_SIZE + 2500
        expected_batches = 2  # 5000 + 2500

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(file_count)]
            get_exif_dates(files)

        assert mock_run.call_count == expected_batches


class TestRunExiftoolBatch:
    """Tests for _run_exiftool_batch (internal batch parser)."""

    def test_parses_absolute_path_in_output(self):
        """exiftool may return absolute paths; only filename should be used."""
        mock_result = MagicMock()
        mock_result.stdout = "/long/path/to/IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch([Path("/long/path/to/IMG.jpg")])

        assert results == {"IMG.jpg": "2024_01_15_143052"}

    def test_logs_stderr(self):
        """stderr from exiftool should be logged as debug."""
        mock_result = MagicMock()
        mock_result.stdout = "IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        mock_result.stderr = "Warning - [minor] some exiftool warning\n"

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with patch("rename_and_move_files.log.debug") as mock_debug:
                _run_exiftool_batch([Path("/fake/IMG.jpg")])

        mock_debug.assert_called_once()
        assert "exiftool" in mock_debug.call_args[0][0]

    def test_skips_malformed_lines(self):
        """Lines with fewer than 2 tab-separated fields should be skipped."""
        mock_result = MagicMock()
        mock_result.stdout = "malformed_line_no_tabs\n"
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch([Path("/fake/IMG.jpg")])

        assert results == {}

    def test_timeout_returns_empty(self):
        """Timeout should return empty dict and not raise."""
        with patch(
            "rename_and_move_files.subprocess.run",
            side_effect=subprocess.TimeoutExpired("exiftool", 300),
        ):
            results = _run_exiftool_batch([Path("/fake/IMG.jpg")])

        assert results == {}


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

    def test_exiftool_returns_error(self):
        """Return False when exiftool returns non-zero exit code."""
        with patch(
            "rename_and_move_files.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "exiftool"),
        ):
            assert check_exiftool() is False

    def test_exiftool_timeout(self):
        """Return False when exiftool check times out."""
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

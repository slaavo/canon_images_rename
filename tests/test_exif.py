"""Tests for EXIF date extraction functions."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from rename_and_move_files import (
    _run_exiftool_batch,
    get_exif_dates,
    check_exiftool,
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

    def test_multiple_batches_merge_results(self):
        """Results from all (parallel) batches should be merged into one dict."""
        batch_results = [
            {"IMG_A.jpg": "2024_01_15_100000"},
            {"IMG_B.jpg": "2024_01_16_110000"},
        ]

        with patch(
            "rename_and_move_files._run_exiftool_batch",
            side_effect=batch_results,
        ):
            files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(EXIFTOOL_BATCH_SIZE + 1)]
            dates = get_exif_dates(files)

        assert dates == {
            "IMG_A.jpg": "2024_01_15_100000",
            "IMG_B.jpg": "2024_01_16_110000",
        }

    def test_jpeg_uses_fast2_flag(self):
        """JPEG (and TIFF-based RAW) should be read with -fast2."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            get_exif_dates([Path("/fake/IMG.jpg"), Path("/fake/IMG.dng")])

        argv = mock_run.call_args[0][0]
        assert "-fast2" in argv

    def test_quicktime_raw_uses_fast_not_fast2(self):
        """CR3 is a QuickTime container: -fast2 would stop at mdat, so use -fast."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            get_exif_dates([Path("/fake/IMG.CR3")])

        argv = mock_run.call_args[0][0]
        assert "-fast" in argv
        assert "-fast2" not in argv

    def test_mixed_cr3_and_jpeg_use_separate_invocations(self):
        """Mixed folders split into one -fast batch (CR3) and one -fast2 batch (rest)."""
        cr3 = Path("/fake/IMG_001.CR3")
        jpg = Path("/fake/IMG_001.JPG")

        def fake_batch(batch, fast_flag):
            return {f"{batch[0].name}": fast_flag}

        with patch(
            "rename_and_move_files._run_exiftool_batch",
            side_effect=fake_batch,
        ) as mock_batch:
            dates = get_exif_dates([cr3, jpg])

        assert mock_batch.call_count == 2
        calls = {tuple(c.args[0]): c.args[1] for c in mock_batch.call_args_list}
        assert calls == {(cr3,): "-fast", (jpg,): "-fast2"}
        # Results from both invocations are merged
        assert dates == {"IMG_001.CR3": "-fast", "IMG_001.JPG": "-fast2"}


class TestRunExiftoolBatch:
    """Tests for _run_exiftool_batch (internal batch parser)."""

    def test_passes_fast_flag_to_exiftool(self):
        """The given -fast level should appear in the exiftool argv."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            _run_exiftool_batch([Path("/fake/IMG.cr3")], "-fast")

        argv = mock_run.call_args[0][0]
        assert argv[0] == "exiftool"
        assert "-fast" in argv
        assert "-fast2" not in argv

    def test_parses_absolute_path_in_output(self):
        """exiftool may return absolute paths; only filename should be used."""
        mock_result = MagicMock()
        mock_result.stdout = "/long/path/to/IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch([Path("/long/path/to/IMG.jpg")], "-fast2")

        assert results == {"IMG.jpg": "2024_01_15_143052"}

    def test_logs_stderr(self):
        """stderr from exiftool should be logged as debug."""
        mock_result = MagicMock()
        mock_result.stdout = "IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        mock_result.stderr = "Warning - [minor] some exiftool warning\n"

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with patch("rename_and_move_files.log.debug") as mock_debug:
                _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

        mock_debug.assert_called_once()
        assert "exiftool" in mock_debug.call_args[0][0]

    def test_skips_malformed_lines(self):
        """Lines with fewer than 2 tab-separated fields should be skipped."""
        mock_result = MagicMock()
        mock_result.stdout = "malformed_line_no_tabs\n"
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

        assert results == {}

    def test_timeout_returns_empty(self):
        """Timeout should return empty dict and not raise."""
        with patch(
            "rename_and_move_files.subprocess.run",
            side_effect=subprocess.TimeoutExpired("exiftool", 300),
        ):
            results = _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

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

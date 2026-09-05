"""Tests for EXIF date extraction functions."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rename_and_move_files import (
    _run_exiftool_batch,
    get_exif_dates,
    check_exiftool,
    ExifToolError,
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
        mock_result.returncode = 0
        mock_result.stdout = EXIFTOOL_OUTPUT_SINGLE
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            files = [Path("/fake/IMG_001.jpg")]
            dates = get_exif_dates(files)

        assert dates == {"IMG_001.jpg": "2024_01_15_143052"}

    def test_parses_multiple_files(self):
        """Parse exiftool output for multiple files."""
        mock_result = MagicMock()
        mock_result.returncode = 0
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
        mock_result.returncode = 0
        mock_result.stdout = "IMG.jpg\t2024_01_15_100000\t2024_01_15_200000\n"
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            dates = get_exif_dates([Path("/fake/IMG.jpg")])

        assert dates["IMG.jpg"] == "2024_01_15_100000"

    def test_falls_back_to_create_date(self):
        """When DateTimeOriginal is missing, use CreateDate."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = EXIFTOOL_OUTPUT_FALLBACK
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            dates = get_exif_dates([Path("/fake/IMG_001.jpg")])

        assert dates == {"IMG_001.jpg": "2024_01_15_143052"}

    def test_timeout_raises(self):
        """A timeout means the dates are unknown, not absent: raise, don't return {}."""
        with patch(
            "rename_and_move_files.subprocess.run",
            side_effect=subprocess.TimeoutExpired("exiftool", 300),
        ):
            with pytest.raises(ExifToolError):
                get_exif_dates([Path("/fake/IMG.jpg")])

    def test_handles_empty_output(self):
        """Empty exiftool output should return empty dict."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            dates = get_exif_dates([Path("/fake/IMG.jpg")])

        assert dates == {}

    def test_batching_large_file_list(self):
        """Files should be processed in batches of EXIFTOOL_BATCH_SIZE."""
        mock_result = MagicMock()
        mock_result.returncode = 0
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
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            get_exif_dates([Path("/fake/IMG.jpg"), Path("/fake/IMG.dng")])

        argv = mock_run.call_args[0][0]
        assert "-fast2" in argv

    def test_quicktime_raw_uses_fast_not_fast2(self):
        """CR3 is a QuickTime container: -fast2 would stop at mdat, so use -fast."""
        mock_result = MagicMock()
        mock_result.returncode = 0
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
        mock_result.returncode = 0
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
        mock_result.returncode = 0
        mock_result.stdout = "/long/path/to/IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch([Path("/long/path/to/IMG.jpg")], "-fast2")

        assert results == {"IMG.jpg": "2024_01_15_143052"}

    def test_logs_stderr(self):
        """stderr from exiftool should be logged as debug."""
        mock_result = MagicMock()
        mock_result.returncode = 0
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
        mock_result.returncode = 0
        mock_result.stdout = "malformed_line_no_tabs\n"
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

        assert results == {}

    def test_timeout_raises(self):
        """Timeout should raise ExifToolError."""
        with patch(
            "rename_and_move_files.subprocess.run",
            side_effect=subprocess.TimeoutExpired("exiftool", 300),
        ):
            with pytest.raises(ExifToolError, match="timed out"):
                _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

    def test_signal_killed_exiftool_raises(self):
        """A negative return code (killed by a signal, e.g. Ctrl+C) is a failure."""
        mock_result = MagicMock()
        mock_result.returncode = -2
        mock_result.stdout = "IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"  # partial output
        mock_result.stderr = ""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with pytest.raises(ExifToolError, match="exit code -2"):
                _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

    def test_nonzero_without_output_raises(self):
        """Non-zero exit with no output at all is a total failure."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: something broke\n"

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with pytest.raises(ExifToolError):
                _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

    def test_nonzero_with_output_is_partial_success(self):
        """exiftool exits 1 when one file is unreadable but still prints the others."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        mock_result.stderr = "Error: File not found - /fake/MISSING.jpg\n"

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with patch("rename_and_move_files.log.warning") as mock_warn:
                results = _run_exiftool_batch(
                    [Path("/fake/IMG.jpg"), Path("/fake/MISSING.jpg")], "-fast2",
                )

        assert results == {"IMG.jpg": "2024_01_15_143052"}
        mock_warn.assert_called_once()

    def test_paths_are_passed_on_stdin(self):
        """File list goes to exiftool via '-@ -' on stdin, never on argv (ARG_MAX)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        files = [Path("/fake/a.jpg"), Path("/fake/b.jpg")]

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            _run_exiftool_batch(files, "-fast2")

        argv = mock_run.call_args[0][0]
        assert argv[-2:] == ["-@", "-"]
        assert not any(str(f) in argv for f in files)
        assert mock_run.call_args[1]["input"] == "/fake/a.jpg\n/fake/b.jpg"

    def test_newline_in_path_is_skipped_with_warning(self):
        """A path containing a newline cannot be sent in an arg file; skip it."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        good = Path("/fake/good.jpg")
        bad = Path("/fake/bad\nname.jpg")

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            with patch("rename_and_move_files.log.warning") as mock_warn:
                _run_exiftool_batch([good, bad], "-fast2")

        assert mock_run.call_args[1]["input"] == str(good)
        mock_warn.assert_called_once()

    def test_only_newline_paths_skips_exiftool(self):
        """If nothing is left to pass, exiftool is not run at all."""
        with patch("rename_and_move_files.subprocess.run") as mock_run:
            results = _run_exiftool_batch([Path("/fake/bad\nname.jpg")], "-fast2")

        assert results == {}
        mock_run.assert_not_called()


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

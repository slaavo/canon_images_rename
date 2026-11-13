"""Tests for EXIF date extraction functions."""

from __future__ import annotations

import concurrent.futures
import os
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rename_and_move_files import (
    _all_open_errors,
    _run_exiftool_batch,
    get_exif_dates,
    check_exiftool,
    get_mtime_dates,
    ExifToolError,
    EXIFTOOL_BATCH_SIZE,
    EXIFTOOL_MAX_PARALLEL,
    EXIFTOOL_MIN_BATCH_SIZE,
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
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            files = [Path("/fake/IMG_001.jpg")]
            dates = get_exif_dates(files)

        assert dates == {"IMG_001.jpg": "2024_01_15_143052"}

    def test_parses_multiple_files(self):
        """Parse exiftool output for multiple files."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = EXIFTOOL_OUTPUT_MULTIPLE
        mock_result.stderr = b""

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
            # IMG_004.CR3 was inspected but has no date: present, None
            "IMG_004.CR3": None,
        }

    def test_prefers_datetime_original_over_create_date(self):
        """DateTimeOriginal should be preferred over CreateDate."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"IMG.jpg\t2024_01_15_100000\t2024_01_15_200000\n"
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            dates = get_exif_dates([Path("/fake/IMG.jpg")])

        assert dates["IMG.jpg"] == "2024_01_15_100000"

    def test_falls_back_to_create_date(self):
        """When DateTimeOriginal is missing, use CreateDate."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = EXIFTOOL_OUTPUT_FALLBACK
        mock_result.stderr = b""

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
        mock_result.stdout = b""
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            dates = get_exif_dates([Path("/fake/IMG.jpg")])

        assert dates == {}

    @staticmethod
    def _record_batches(files, max_parallel):
        """Run get_exif_dates with a fake batch runner; return the batches."""
        calls = []
        lock = threading.Lock()

        def fake_batch(batch, fast_flag):
            with lock:
                calls.append((list(batch), fast_flag))
            return {f.name: "2024_01_15_100000" for f in batch}

        with patch("rename_and_move_files.EXIFTOOL_MAX_PARALLEL", max_parallel), patch(
            "rename_and_move_files._run_exiftool_batch", side_effect=fake_batch
        ):
            dates = get_exif_dates(files)
        # Worker threads append in completion order, not submission order;
        # put the batches back in input order so assertions are deterministic.
        position = {f: i for i, f in enumerate(files)}
        calls.sort(key=lambda c: position[c[0][0]])
        return calls, dates

    def test_ordinary_folder_is_split_across_processes(self):
        """A few hundred files must not go to a single exiftool process."""
        files = [Path(f"/fake/IMG_{i:05d}.CR3") for i in range(784)]

        calls, _ = self._record_batches(files, max_parallel=8)

        assert [len(b) for b, _ in calls] == [98] * 8

    def test_small_folder_uses_one_process(self):
        """Up to EXIFTOOL_MIN_BATCH_SIZE files the start-up cost is not worth a split."""
        files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(EXIFTOOL_MIN_BATCH_SIZE)]

        calls, _ = self._record_batches(files, max_parallel=8)

        assert len(calls) == 1

    def test_one_file_over_min_batch_size_splits_evenly(self):
        """Just above EXIFTOOL_MIN_BATCH_SIZE: two balanced batches, no 1-file tail."""
        n = EXIFTOOL_MIN_BATCH_SIZE + 1
        files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(n)]

        calls, _ = self._record_batches(files, max_parallel=8)

        assert sorted(len(b) for b, _ in calls) == [n // 2, n - n // 2]

    def test_batches_differ_by_at_most_one_file(self):
        """Balanced split for awkward counts (no tiny tail batch)."""
        for count in (101, 151, 401, 16001):
            files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(count)]
            calls, _ = self._record_batches(files, max_parallel=8)
            sizes = [len(b) for b, _ in calls]
            assert sum(sizes) == count
            assert max(sizes) - min(sizes) <= 1, (count, sizes)
            assert max(sizes) <= EXIFTOOL_BATCH_SIZE

    def test_batches_never_smaller_than_min_batch_size(self):
        """Splitting stops at EXIFTOOL_MIN_BATCH_SIZE files per process."""
        files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(3 * EXIFTOOL_MIN_BATCH_SIZE - 1)]

        calls, _ = self._record_batches(files, max_parallel=8)

        sizes = [len(b) for b, _ in calls]
        assert sizes == [EXIFTOOL_MIN_BATCH_SIZE, EXIFTOOL_MIN_BATCH_SIZE, EXIFTOOL_MIN_BATCH_SIZE - 1]

    def test_batches_never_larger_than_batch_size(self):
        """EXIFTOOL_BATCH_SIZE caps one process's work even with few processes."""
        files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(3 * EXIFTOOL_BATCH_SIZE + 1)]

        calls, _ = self._record_batches(files, max_parallel=2)

        assert len(calls) == 4
        assert max(len(b) for b, _ in calls) <= EXIFTOOL_BATCH_SIZE

    def test_every_file_in_exactly_one_batch(self):
        """Splitting must neither drop nor duplicate files, and keeps their order."""
        files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(1234)]

        calls, dates = self._record_batches(files, max_parallel=8)

        batched = [f for batch, _ in sorted(calls, key=lambda c: c[0][0].name) for f in batch]
        assert batched == files
        assert len(dates) == len(files)

    def test_quicktime_batches_start_first(self):
        """CR3 (slowest to parse) batches are submitted before the JPEG ones."""
        files = [Path(f"/fake/IMG_{i:05d}.JPG") for i in range(400)]
        files += [Path(f"/fake/IMG_{i:05d}.CR3") for i in range(400)]
        submitted = []

        def fake_batch(batch, fast_flag):
            return {}

        real_executor = concurrent.futures.ThreadPoolExecutor

        class RecordingExecutor(real_executor):
            def map(self, fn, *iterables, **kwargs):
                items = list(iterables[0])
                submitted.extend(flag for _, flag in items)
                return super().map(fn, items, **kwargs)

        with patch("rename_and_move_files.EXIFTOOL_MAX_PARALLEL", 4), patch(
            "rename_and_move_files._run_exiftool_batch", side_effect=fake_batch
        ), patch("rename_and_move_files.concurrent.futures.ThreadPoolExecutor", RecordingExecutor):
            get_exif_dates(files)

        assert submitted == ["-fast"] * 4 + ["-fast2"] * 4

    def test_concurrency_capped_at_max_parallel(self):
        """No more than EXIFTOOL_MAX_PARALLEL exiftool processes run at once."""
        files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(4 * EXIFTOOL_BATCH_SIZE)]
        lock = threading.Lock()
        running = 0
        peak = 0
        calls = 0  # MagicMock.call_count is not thread-safe

        def fake_batch(batch, fast_flag):
            nonlocal running, peak
            nonlocal calls
            with lock:
                calls += 1
                running += 1
                peak = max(peak, running)
            time.sleep(0.02)
            with lock:
                running -= 1
            return {}

        with patch("rename_and_move_files.EXIFTOOL_MAX_PARALLEL", 2), patch(
            "rename_and_move_files._run_exiftool_batch", side_effect=fake_batch
        ):
            get_exif_dates(files)

        assert calls == 4
        assert peak == 2

    def test_max_parallel_bounded_by_cpu_count(self):
        """The default never exceeds the CPU count."""
        assert 1 <= EXIFTOOL_MAX_PARALLEL <= max(1, os.cpu_count() or 1)

    def test_multiple_batches_merge_results(self):
        """Results from all (parallel) batches should be merged into one dict."""
        files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(500)]

        calls, dates = self._record_batches(files, max_parallel=4)

        assert len(calls) == 4
        assert dates == {f.name: "2024_01_15_100000" for f in files}

    def test_batch_failure_propagates_from_parallel_run(self):
        """An ExifToolError in any parallel batch must abort get_exif_dates."""
        files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(500)]

        def fake_batch(batch, fast_flag):
            if batch[0].name == "IMG_00250.jpg":
                raise ExifToolError("boom")
            return {f.name: None for f in batch}

        with patch("rename_and_move_files.EXIFTOOL_MAX_PARALLEL", 4), patch(
            "rename_and_move_files._run_exiftool_batch", side_effect=fake_batch
        ):
            with pytest.raises(ExifToolError):
                get_exif_dates(files)

    def test_jpeg_uses_fast2_flag(self):
        """JPEG (and TIFF-based RAW) should be read with -fast2."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b""
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            get_exif_dates([Path("/fake/IMG.jpg"), Path("/fake/IMG.dng")])

        argv = mock_run.call_args[0][0]
        assert "-fast2" in argv

    def test_quicktime_raw_uses_fast_not_fast2(self):
        """CR3 is a QuickTime container: -fast2 would stop at mdat, so use -fast."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b""
        mock_result.stderr = b""

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

        # call_args_list (one atomic append per call), not the racy call_count
        assert len(mock_batch.call_args_list) == 2
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
        mock_result.stdout = b""
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            _run_exiftool_batch([Path("/fake/IMG.cr3")], "-fast")

        argv = mock_run.call_args[0][0]
        assert argv[0] == "exiftool"
        assert "-fast" in argv
        assert "-fast2" not in argv

    def test_inspected_file_without_date_is_present_as_none(self):
        """A '-' row means exiftool opened the file and found no date: keep the key."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"noexif.jpg\t-\t-\n"
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch([Path("/fake/noexif.jpg")], "-fast2")

        assert results == {"noexif.jpg": None}

    def test_uninspected_file_is_absent(self):
        """A file with no output row (exiftool could not open it) stays absent."""
        mock_result = MagicMock()
        mock_result.returncode = 1  # exiftool: one file had an error
        mock_result.stdout = b"good.jpg\t2024_01_15_143052\t-\n"
        mock_result.stderr = b"Error: File not found - /fake/gone.jpg\n"

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch(
                [Path("/fake/good.jpg"), Path("/fake/gone.jpg")], "-fast2",
            )

        assert results == {"good.jpg": "2024_01_15_143052"}
        assert "gone.jpg" not in results

    def test_parses_absolute_path_in_output(self):
        """exiftool may return absolute paths; only filename should be used."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"/long/path/to/IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch([Path("/long/path/to/IMG.jpg")], "-fast2")

        assert results == {"IMG.jpg": "2024_01_15_143052"}

    def test_logs_stderr(self):
        """stderr from exiftool should be logged as debug."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        mock_result.stderr = b"Warning - [minor] some exiftool warning\n"

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with patch("rename_and_move_files.log.debug") as mock_debug:
                _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

        mock_debug.assert_called_once()
        assert "exiftool" in mock_debug.call_args[0][0]

    def test_skips_malformed_lines(self):
        """Lines with fewer than 2 tab-separated fields should be skipped."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"malformed_line_no_tabs\n"
        mock_result.stderr = b""

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
        mock_result.stdout = b"IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"  # partial output
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with pytest.raises(ExifToolError, match="exit code -2"):
                _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

    def test_nonzero_without_output_raises(self):
        """Non-zero exit with no output at all is a total failure."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = b""
        mock_result.stderr = b"Error: something broke\n"

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with pytest.raises(ExifToolError):
                _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

    @staticmethod
    def _open_errors(*paths, kind=b"File not found"):
        return b"".join(b"Error: " + kind + b" - " + os.fsencode(str(p)) + b"\r\n" for p in paths)

    def test_batch_of_only_unopenable_files_is_not_fatal(self):
        """All files vanished/locked: exit 1, no stdout -> all absent, no abort."""
        batch = [Path("/fake/GONE_1.jpg"), Path("/fake/LOCKED_2.jpg")]
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = b""
        mock_result.stderr = self._open_errors(batch[0]) + self._open_errors(
            batch[1], kind=b"Error opening file"
        )

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            assert _run_exiftool_batch(batch, "-fast2") == {}

    def test_windows_open_errors_match_forward_slash_echo(self):
        """On Windows exiftool echoes C:\\a\\b.jpg as C:/a/b.jpg in its errors."""
        stderr = b"Error: File not found - C:/Photos/GONE.jpg\r\n"

        with patch("rename_and_move_files._IS_WINDOWS", True):
            assert _all_open_errors(stderr, ["C:\\Photos\\GONE.jpg"])

    def test_posix_backslash_is_not_a_separator(self):
        """On POSIX a backslash is part of the name: no normalisation, so no match."""
        stderr = b"Error: File not found - /p/a/b.jpg\n"

        with patch("rename_and_move_files._IS_WINDOWS", False):
            assert not _all_open_errors(stderr, ["/p/a\\b.jpg"])
            assert _all_open_errors(stderr, ["/p/a/b.jpg"])

    def test_open_errors_for_only_some_files_still_fatal(self):
        """No output but an open error for only part of the batch: unexplained -> abort."""
        batch = [Path("/fake/GONE_1.jpg"), Path("/fake/IMG_2.jpg")]
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = b""
        mock_result.stderr = self._open_errors(batch[0])

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with pytest.raises(ExifToolError):
                _run_exiftool_batch(batch, "-fast2")

    def test_open_errors_plus_other_error_still_fatal(self):
        """Any stderr line besides per-file open errors keeps the failure fatal."""
        batch = [Path("/fake/GONE_1.jpg")]
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = b""
        mock_result.stderr = self._open_errors(batch[0]) + b"Error: something broke\n"

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with pytest.raises(ExifToolError):
                _run_exiftool_batch(batch, "-fast2")

    def test_open_errors_with_other_exit_code_still_fatal(self):
        """Only exit code 1 (exiftool's "files had errors") qualifies."""
        batch = [Path("/fake/GONE_1.jpg")]
        mock_result = MagicMock()
        mock_result.returncode = 2
        mock_result.stdout = b""
        mock_result.stderr = self._open_errors(batch[0])

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            with pytest.raises(ExifToolError):
                _run_exiftool_batch(batch, "-fast2")

    def test_unopenable_tail_batch_does_not_abort_run(self):
        """Regression: an unreadable last file must not abort an otherwise good folder."""
        files = [Path(f"/fake/IMG_{i:05d}.jpg") for i in range(EXIFTOOL_MIN_BATCH_SIZE + 1)]
        gone = files[-1]

        def fake_run(argv, input, **kwargs):
            paths = input.split(b"\n")
            result = MagicMock()
            result.returncode = 1 if os.fsencode(str(gone)) in paths else 0
            rows = [os.fsencode(Path(os.fsdecode(p)).name) + b"\t2024_01_15_100000\t-"
                    for p in paths if p != os.fsencode(str(gone))]
            result.stdout = b"\n".join(rows) + (b"\n" if rows else b"")
            result.stderr = self._open_errors(gone) if result.returncode else b""
            return result

        with patch("rename_and_move_files.EXIFTOOL_MAX_PARALLEL", 8), patch(
            "rename_and_move_files.subprocess.run", side_effect=fake_run
        ):
            dates = get_exif_dates(files)

        assert gone.name not in dates  # reported as unreadable, not dated
        assert len(dates) == len(files) - 1

    def test_requests_error_tag(self):
        """The Error column is what tells "could not open" from "no date"."""
        mock_result = MagicMock(returncode=0, stdout=b"", stderr=b"")

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2")

        assert "-Error" in mock_run.call_args[0][0]

    def test_read_denied_file_is_absent_not_none(self):
        """Row with Error = "Error opening file" -> absent (unreadable), not None (mtime)."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = (
            b"locked.jpg\t-\t-\tError opening file\r\n"
            b"IMG_02.jpg\t2022_07_18_135135\t2022_07_18_135135\t-\r\n"
        )
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch(
                [Path("/fake/locked.jpg"), Path("/fake/IMG_02.jpg")], "-fast2"
            )

        assert results == {"IMG_02.jpg": "2022_07_18_135135"}

    def test_batch_of_only_read_denied_files_is_not_fatal(self):
        """All files locked: exiftool still prints rows, so no abort; all absent."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = b"a.jpg\t-\t-\tError opening file\nb.jpg\t-\t-\tError opening file\n"
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            assert _run_exiftool_batch([Path("/fake/a.jpg"), Path("/fake/b.jpg")], "-fast2") == {}

    def test_other_error_tag_keeps_no_date_semantics(self):
        """Only "Error opening file" means not inspected; e.g. an empty file stays None."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = b"empty.jpg\t-\t-\tFile is empty\n"
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            assert _run_exiftool_batch([Path("/fake/empty.jpg")], "-fast2") == {"empty.jpg": None}

    def test_date_row_with_error_column_parses(self):
        """The extra column must not disturb date parsing."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"IMG.jpg\t-\t2024_01_15_143052\t-\n"
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            assert _run_exiftool_batch([Path("/fake/IMG.jpg")], "-fast2") == {
                "IMG.jpg": "2024_01_15_143052"
            }

    def test_nonzero_with_output_is_partial_success(self):
        """exiftool exits 1 when one file is unreadable but still prints the others."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = b"IMG.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        mock_result.stderr = b"Error: File not found - /fake/MISSING.jpg\n"

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
        mock_result.stdout = b""
        mock_result.stderr = b""
        files = [Path("/fake/a.jpg"), Path("/fake/b.jpg")]

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            _run_exiftool_batch(files, "-fast2")

        argv = mock_run.call_args[0][0]
        assert argv[-2:] == ["-@", "-"]
        assert not any(str(f) in argv for f in files)
        assert mock_run.call_args[1]["input"] == b"/fake/a.jpg\n/fake/b.jpg"
        # bytes mode: the locale encoding must never touch the paths
        assert "text" not in mock_run.call_args[1]

    @pytest.mark.skipif(os.name == "nt", reason="POSIX raw-byte file names")
    def test_non_utf8_directory_is_passed_as_raw_bytes(self):
        """A non-UTF-8 byte in a folder name must reach exiftool unchanged, not crash."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"IMG.jpg\t2024_01_15_143052\t-\n"
        mock_result.stderr = b""
        path = Path(os.fsdecode(b"/photos/Zdj\xeacia/IMG.jpg"))  # CP1250 "ę"

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            results = _run_exiftool_batch([path], "-fast2")

        assert mock_run.call_args[1]["input"] == b"/photos/Zdj\xeacia/IMG.jpg"
        assert results == {"IMG.jpg": "2024_01_15_143052"}

    @pytest.mark.skipif(os.name == "nt", reason="POSIX raw-byte file names")
    def test_non_utf8_filename_in_output_matches_scanned_name(self):
        """exiftool echoes raw bytes; the key must equal the name scandir produced."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"IMG_\xff.jpg\t2024_01_15_143052\t-\n"
        mock_result.stderr = b""
        path = Path(os.fsdecode(b"/photos/IMG_\xff.jpg"))

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch([path], "-fast2")

        assert results == {path.name: "2024_01_15_143052"}

    def test_crlf_output_is_parsed(self):
        """Windows line endings must not leak into names or dates."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"a.jpg\t2024_01_15_143052\t-\r\nb.jpg\t-\t-\r\n"
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result):
            results = _run_exiftool_batch([Path("/fake/a.jpg"), Path("/fake/b.jpg")], "-fast2")

        assert results == {"a.jpg": "2024_01_15_143052", "b.jpg": None}

    def test_windows_adds_utf8_filename_charset(self):
        """On Windows exiftool must be told the arg file carries UTF-8 names."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b""
        mock_result.stderr = b""

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            _run_exiftool_batch([Path("/fake/a.jpg")], "-fast2")
        posix_argv = mock_run.call_args[0][0]

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            with patch("rename_and_move_files._IS_WINDOWS", True):
                _run_exiftool_batch([Path("/fake/a.jpg")], "-fast2")
        windows_argv = mock_run.call_args[0][0]

        assert "-charset" not in posix_argv
        i = windows_argv.index("-charset")
        assert windows_argv[i + 1] == "filename=utf8"
        assert windows_argv.index("-charset") < windows_argv.index("-@")

    def test_newline_in_path_is_skipped_with_warning(self):
        """A path containing a newline cannot be sent in an arg file; skip it."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b""
        mock_result.stderr = b""
        good = Path("/fake/good.jpg")
        bad = Path("/fake/bad\nname.jpg")

        with patch("rename_and_move_files.subprocess.run", return_value=mock_result) as mock_run:
            with patch("rename_and_move_files.log.warning") as mock_warn:
                _run_exiftool_batch([good, bad], "-fast2")

        assert mock_run.call_args[1]["input"] == os.fsencode(str(good))
        mock_warn.assert_called_once()

    def test_only_newline_paths_skips_exiftool(self):
        """If nothing is left to pass, exiftool is not run at all."""
        with patch("rename_and_move_files.subprocess.run") as mock_run:
            results = _run_exiftool_batch([Path("/fake/bad\nname.jpg")], "-fast2")

        assert results == {}
        mock_run.assert_not_called()


class TestGetMtimeDates:
    """Tests for get_mtime_dates (the lazy mtime fallback)."""

    def test_returns_formatted_date(self, tmp_path: Path):
        """Return modification date as YYYY_MM_DD_HHMMSS keyed by filename."""
        test_file = tmp_path / "test.jpg"
        test_file.touch()

        result = get_mtime_dates([test_file])

        assert list(result) == ["test.jpg"]
        value = result["test.jpg"]
        assert value is not None
        assert len(value) == 17
        assert value[4] == "_" and value[7] == "_" and value[10] == "_"

    def test_nonexistent_file_maps_to_none(self, tmp_path: Path):
        """A file that cannot be stat'ed maps to None (it will be skipped)."""
        result = get_mtime_dates([tmp_path / "does_not_exist.jpg"])

        assert result == {"does_not_exist.jpg": None}

    def test_empty_list(self):
        assert get_mtime_dates([]) == {}


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

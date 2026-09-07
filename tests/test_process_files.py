"""Integration tests for process_files function."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from rename_and_move_files import (
    ExifToolError,
    InterruptHandler,
    MoveResult,
    process_files,
)


class TestProcessFiles:
    """Integration tests for the main processing pipeline."""

    def _make_photos(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create input dir with photos and an output dir."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        return input_dir, output_dir

    def _mock_exiftool(self, output: str):
        """Create a mock for subprocess.run returning exiftool output."""
        mock_result = MagicMock()
        mock_result.stdout = output
        mock_result.stderr = ""
        mock_result.returncode = 0
        return patch("rename_and_move_files.subprocess.run", return_value=mock_result)

    def test_full_pipeline_jpeg(self, tmp_path: Path):
        """JPEG file should be moved to !orig/ with date prefix."""
        input_dir, output_dir = self._make_photos(tmp_path)
        (input_dir / "photo.jpg").write_text("jpeg data")

        exif_output = "photo.jpg\t2024_01_15_143052\t2024_01_15_143052\n"

        with self._mock_exiftool(exif_output):
            handler = InterruptHandler()
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=False,
                interrupt_handler=handler, workers=1,
            )

        assert success == 1
        assert errors == 0
        dest = output_dir / "2024_01_15" / "!orig" / "2024_01_15_143052_photo.jpg"
        assert dest.exists()
        assert dest.read_text() == "jpeg data"

    def test_full_pipeline_raw_default(self, tmp_path: Path):
        """RAW file should stay in date folder root by default."""
        input_dir, output_dir = self._make_photos(tmp_path)
        (input_dir / "photo.cr3").write_text("raw data")

        exif_output = "photo.cr3\t2024_01_15_143052\t2024_01_15_143052\n"

        with self._mock_exiftool(exif_output):
            handler = InterruptHandler()
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=False,
                interrupt_handler=handler, workers=1,
            )

        assert success == 1
        dest = output_dir / "2024_01_15" / "2024_01_15_143052_photo.cr3"
        assert dest.exists()

    def test_full_pipeline_raw_to_orig(self, tmp_path: Path):
        """RAW file should go to !orig/ with -r flag."""
        input_dir, output_dir = self._make_photos(tmp_path)
        (input_dir / "photo.cr3").write_text("raw data")

        exif_output = "photo.cr3\t2024_01_15_143052\t2024_01_15_143052\n"

        with self._mock_exiftool(exif_output):
            handler = InterruptHandler()
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=True, dry_run=False,
                interrupt_handler=handler, workers=1,
            )

        assert success == 1
        dest = output_dir / "2024_01_15" / "!orig" / "2024_01_15_143052_photo.cr3"
        assert dest.exists()

    def test_dry_run_does_not_move(self, tmp_path: Path):
        """Dry run should not move files or create folders."""
        input_dir, output_dir = self._make_photos(tmp_path)
        (input_dir / "photo.jpg").write_text("data")

        exif_output = "photo.jpg\t2024_01_15_143052\t2024_01_15_143052\n"

        with self._mock_exiftool(exif_output):
            handler = InterruptHandler()
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=True,
                interrupt_handler=handler, workers=1,
            )

        assert success == 1
        assert errors == 0
        # Source should still exist
        assert (input_dir / "photo.jpg").exists()
        # Date folder should NOT be created
        assert not (output_dir / "2024_01_15").exists()

    def test_no_files_returns_zero(self, tmp_path: Path):
        """Empty input folder should return (0, 0)."""
        input_dir, output_dir = self._make_photos(tmp_path)

        handler = InterruptHandler()
        success, errors = process_files(
            input_dir, output_dir,
            move_raw_to_orig=False, dry_run=False,
            interrupt_handler=handler, workers=1,
        )

        assert success == 0
        assert errors == 0

    def test_multiple_files_same_date(self, tmp_path: Path):
        """Multiple files with same date should get unique names."""
        input_dir, output_dir = self._make_photos(tmp_path)
        (input_dir / "A.jpg").write_text("a")
        (input_dir / "B.jpg").write_text("b")

        exif_output = (
            "A.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
            "B.jpg\t2024_01_15_143052\t2024_01_15_143052\n"
        )

        with self._mock_exiftool(exif_output):
            handler = InterruptHandler()
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=False,
                interrupt_handler=handler, workers=1,
            )

        assert success == 2
        assert errors == 0

    def test_creates_subfolders(self, tmp_path: Path):
        """Processing should create !jpg and !orig subfolders."""
        input_dir, output_dir = self._make_photos(tmp_path)
        (input_dir / "photo.jpg").write_text("data")

        exif_output = "photo.jpg\t2024_01_15_143052\t2024_01_15_143052\n"

        with self._mock_exiftool(exif_output):
            handler = InterruptHandler()
            process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=False,
                interrupt_handler=handler, workers=1,
            )

        assert (output_dir / "2024_01_15" / "!jpg").is_dir()
        assert (output_dir / "2024_01_15" / "!orig").is_dir()


class TestMultipleWorkers:
    """Test that processing works correctly with multiple worker threads."""

    def _make_photos(self, tmp_path: Path) -> tuple[Path, Path]:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        return input_dir, output_dir

    def _mock_exiftool(self, output: str):
        mock_result = MagicMock()
        mock_result.stdout = output
        mock_result.stderr = ""
        mock_result.returncode = 0
        return patch("rename_and_move_files.subprocess.run", return_value=mock_result)

    def test_multiple_workers_same_result(self, tmp_path: Path):
        """Processing with workers=4 should succeed for all files."""
        input_dir, output_dir = self._make_photos(tmp_path)
        (input_dir / "A.jpg").write_text("a")
        (input_dir / "B.jpg").write_text("b")
        (input_dir / "C.cr3").write_text("c")

        exif_output = (
            "A.jpg\t2024_03_10_120000\t2024_03_10_120000\n"
            "B.jpg\t2024_03_10_130000\t2024_03_10_130000\n"
            "C.cr3\t2024_03_10_140000\t2024_03_10_140000\n"
        )

        with self._mock_exiftool(exif_output):
            handler = InterruptHandler()
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=False,
                interrupt_handler=handler, workers=4,
            )

        assert errors == 0
        assert success == 3


class TestMoveFailure:
    """Test error counting when file moves fail."""

    def _make_photos(self, tmp_path: Path) -> tuple[Path, Path]:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        return input_dir, output_dir

    def _mock_exiftool(self, output: str):
        mock_result = MagicMock()
        mock_result.stdout = output
        mock_result.stderr = ""
        mock_result.returncode = 0
        return patch("rename_and_move_files.subprocess.run", return_value=mock_result)

    def test_error_count_incremented_on_move_failure(self, tmp_path: Path):
        """Each failed move should increment the error count."""
        input_dir, output_dir = self._make_photos(tmp_path)
        (input_dir / "photo.cr3").write_text("raw data")

        exif_output = "photo.cr3\t2024_03_10_120000\t2024_03_10_120000\n"

        with self._mock_exiftool(exif_output):
            with patch(
                "rename_and_move_files.move_single_file",
                return_value=MoveResult(
                    success=False, source_name="photo.cr3", error="Permission denied"
                ),
            ):
                handler = InterruptHandler()
                success, errors = process_files(
                    input_dir, output_dir,
                    move_raw_to_orig=False, dry_run=False,
                    interrupt_handler=handler, workers=1,
                )

        assert errors == 1
        assert success == 0


class TestInterruptDuringMove:
    """Test graceful interrupt handling during the parallel move loop."""

    def _make_photos(self, tmp_path: Path) -> tuple[Path, Path]:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        return input_dir, output_dir

    def _mock_exiftool(self, output: str):
        mock_result = MagicMock()
        mock_result.stdout = output
        mock_result.stderr = ""
        mock_result.returncode = 0
        return patch("rename_and_move_files.subprocess.run", return_value=mock_result)

    def test_interrupt_cancels_pending_moves(self, tmp_path: Path):
        """Setting the interrupt flag mid-batch should cancel pending moves."""
        input_dir, output_dir = self._make_photos(tmp_path)
        names = [f"IMG_{i}.jpg" for i in range(5)]
        for n in names:
            (input_dir / n).write_text("data")

        exif_output = "".join(
            f"{n}\t2024_03_10_12000{i}\t2024_03_10_12000{i}\n"
            for i, n in enumerate(names)
        )

        handler = InterruptHandler()

        def interrupting_move(source, dest_path, is_duplicate):
            # Trip the interrupt flag as soon as the first move runs.
            handler.interrupted = True
            return MoveResult(
                success=True, source_name=source.name,
                dest_path=dest_path, is_duplicate=is_duplicate,
            )

        with self._mock_exiftool(exif_output):
            with patch(
                "rename_and_move_files.move_single_file",
                side_effect=interrupting_move,
            ) as mock_move:
                success, errors = process_files(
                    input_dir, output_dir,
                    move_raw_to_orig=False, dry_run=False,
                    interrupt_handler=handler, workers=1,
                )

        # The interrupt was observed and the loop broke after the first
        # completed result instead of reporting all 5 as processed — i.e. the
        # interrupt stopped the loop early (the remaining results are dropped
        # and any not-yet-started tasks are cancelled).
        assert handler.interrupted is True
        assert success == 1
        assert errors == 0


class TestExifReadFailure:
    """exiftool failure or an interrupt during the EXIF scan must move nothing."""

    def _make_photos(self, tmp_path: Path) -> tuple[Path, Path]:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / "photo.jpg").write_text("data")
        return input_dir, output_dir

    def test_exiftool_failure_moves_nothing(self, tmp_path: Path):
        """A timeout/killed exiftool is an error; no mtime fallback, no moves."""
        input_dir, output_dir = self._make_photos(tmp_path)

        with patch(
            "rename_and_move_files.get_exif_dates",
            side_effect=ExifToolError("exiftool timed out"),
        ):
            handler = InterruptHandler()
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=False,
                interrupt_handler=handler, workers=1,
            )

        assert (success, errors) == (0, 1)
        assert (input_dir / "photo.jpg").exists()
        assert list(output_dir.iterdir()) == []

    def test_interrupt_during_exif_read_moves_nothing(self, tmp_path: Path):
        """Ctrl+C during the EXIF scan stops before any folder is created."""
        input_dir, output_dir = self._make_photos(tmp_path)
        handler = InterruptHandler()

        def interrupting_exif(files):
            handler.interrupted = True
            return {"photo.jpg": "2024_01_15_143052"}

        with patch("rename_and_move_files.get_exif_dates", side_effect=interrupting_exif):
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=False,
                interrupt_handler=handler, workers=1,
            )

        assert (success, errors) == (0, 0)
        assert (input_dir / "photo.jpg").exists()
        assert list(output_dir.iterdir()) == []

    def test_interrupt_that_kills_exiftool_is_not_an_error(self, tmp_path: Path):
        """Ctrl+C kills the exiftool child too; report an interrupt, not a failure."""
        input_dir, output_dir = self._make_photos(tmp_path)
        handler = InterruptHandler()

        def killed_exif(files):
            handler.interrupted = True
            raise ExifToolError("exiftool failed with exit code -2")

        with patch("rename_and_move_files.get_exif_dates", side_effect=killed_exif):
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=False,
                interrupt_handler=handler, workers=1,
            )

        assert (success, errors) == (0, 0)
        assert list(output_dir.iterdir()) == []


class TestUnreadableFile:
    """A file exiftool could not open is an error and is left in place."""

    def _setup(self, tmp_path: Path) -> tuple[Path, Path]:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / "good.jpg").write_text("good")
        (input_dir / "bad.jpg").write_text("bad")
        return input_dir, output_dir

    def _mock_exiftool_missing_bad(self):
        mock_result = MagicMock()
        mock_result.returncode = 1  # exiftool: one file had an error
        mock_result.stdout = "good.jpg\t2024_01_15_143052\t-\n"  # no row for bad.jpg
        mock_result.stderr = "Error: File not found - bad.jpg\n"
        return patch("rename_and_move_files.subprocess.run", return_value=mock_result)

    def test_unreadable_file_is_error_and_not_moved(self, tmp_path: Path):
        input_dir, output_dir = self._setup(tmp_path)

        with self._mock_exiftool_missing_bad():
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=False,
                interrupt_handler=InterruptHandler(), workers=1,
            )

        assert (success, errors) == (1, 1)
        assert (input_dir / "bad.jpg").read_text() == "bad"
        moved = sorted(p.name for p in output_dir.rglob("*.jpg"))
        assert moved == ["2024_01_15_143052_good.jpg"]

    def test_unreadable_file_counted_in_dry_run(self, tmp_path: Path):
        input_dir, output_dir = self._setup(tmp_path)

        with self._mock_exiftool_missing_bad():
            success, errors = process_files(
                input_dir, output_dir,
                move_raw_to_orig=False, dry_run=True,
                interrupt_handler=InterruptHandler(), workers=1,
            )

        assert (success, errors) == (1, 1)
        assert list(output_dir.iterdir()) == []

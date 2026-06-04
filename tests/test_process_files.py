"""Integration tests for process_files function."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from rename_and_move_files import process_files, InterruptHandler, MoveResult


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

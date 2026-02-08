"""Tests for plan_moves function (file routing logic)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from rename_and_move_files import plan_moves


class TestPlanMoves:
    """Tests for plan_moves — pure routing logic extracted from process_files."""

    def test_jpeg_routed_to_orig(self):
        """JPEG files should always go to !orig/ subfolder."""
        files = [Path("/photos/IMG.jpg")]
        dates = {"IMG.jpg": "2024_01_15_143052"}

        infos, folders, fallback, skipped = plan_moves(
            files, dates, Path("/out"), move_raw_to_orig=False,
        )

        assert len(infos) == 1
        assert infos[0].dest_folder == Path("/out/2024_01_15/!orig")
        assert infos[0].new_filename == "2024_01_15_143052_IMG.jpg"

    def test_jpeg_uppercase_routed_to_orig(self):
        """JPEG files with uppercase extension should also go to !orig/."""
        files = [Path("/photos/IMG.JPG")]
        dates = {"IMG.JPG": "2024_01_15_143052"}

        infos, folders, _, _ = plan_moves(
            files, dates, Path("/out"), move_raw_to_orig=False,
        )

        assert infos[0].dest_folder == Path("/out/2024_01_15/!orig")

    def test_raw_stays_in_root_by_default(self):
        """RAW files should stay in date folder root without -r flag."""
        files = [Path("/photos/IMG.cr3")]
        dates = {"IMG.cr3": "2024_01_15_143052"}

        infos, folders, _, _ = plan_moves(
            files, dates, Path("/out"), move_raw_to_orig=False,
        )

        assert infos[0].dest_folder == Path("/out/2024_01_15")

    def test_raw_goes_to_orig_with_flag(self):
        """RAW files should go to !orig/ with move_raw_to_orig=True."""
        files = [Path("/photos/IMG.CR3")]
        dates = {"IMG.CR3": "2024_01_15_143052"}

        infos, folders, _, _ = plan_moves(
            files, dates, Path("/out"), move_raw_to_orig=True,
        )

        assert infos[0].dest_folder == Path("/out/2024_01_15/!orig")

    def test_date_folders_collected(self):
        """Unique date folders should be collected."""
        files = [
            Path("/photos/A.jpg"),
            Path("/photos/B.jpg"),
            Path("/photos/C.cr3"),
        ]
        dates = {
            "A.jpg": "2024_01_15_100000",
            "B.jpg": "2024_01_15_200000",  # same date
            "C.cr3": "2024_01_16_100000",  # different date
        }

        _, folders, _, _ = plan_moves(
            files, dates, Path("/out"), move_raw_to_orig=False,
        )

        assert folders == {"2024_01_15", "2024_01_16"}

    def test_fallback_to_mtime(self, tmp_path: Path):
        """Files without EXIF should fall back to file modification date."""
        test_file = tmp_path / "IMG.jpg"
        test_file.touch()

        infos, _, fallback_count, skipped = plan_moves(
            [test_file], {}, Path("/out"), move_raw_to_orig=False,
        )

        assert len(infos) == 1
        assert fallback_count == 1
        assert skipped == 0

    def test_skips_file_without_any_date(self, tmp_path: Path):
        """Files with no EXIF and no mtime should be skipped."""
        files = [Path("/fake/IMG.jpg")]

        with patch("rename_and_move_files.get_file_mod_date", return_value=None):
            infos, _, fallback, skipped = plan_moves(
                files, {}, Path("/out"), move_raw_to_orig=False,
            )

        assert len(infos) == 0
        assert skipped == 1

    def test_empty_file_list(self):
        """Empty file list should return empty results."""
        infos, folders, fallback, skipped = plan_moves(
            [], {}, Path("/out"), move_raw_to_orig=False,
        )

        assert infos == []
        assert folders == set()
        assert fallback == 0
        assert skipped == 0

    def test_filename_format(self):
        """Generated filename should be YYYY_MM_DD_HHMMSS_stem.ext."""
        files = [Path("/photos/DSC_1234.NEF")]
        dates = {"DSC_1234.NEF": "2024_03_20_091500"}

        infos, _, _, _ = plan_moves(
            files, dates, Path("/out"), move_raw_to_orig=False,
        )

        assert infos[0].new_filename == "2024_03_20_091500_DSC_1234.NEF"

    def test_preserves_original_extension_case(self):
        """Extension case should be preserved in the new filename."""
        files = [Path("/photos/IMG.CR3")]
        dates = {"IMG.CR3": "2024_01_15_143052"}

        infos, _, _, _ = plan_moves(
            files, dates, Path("/out"), move_raw_to_orig=False,
        )

        assert infos[0].new_filename.endswith(".CR3")

    def test_mixed_jpeg_and_raw_routing(self):
        """Mixed JPEG and RAW files should be routed correctly."""
        files = [
            Path("/photos/IMG.jpg"),
            Path("/photos/IMG.cr3"),
            Path("/photos/IMG.dng"),
        ]
        dates = {
            "IMG.jpg": "2024_01_15_143052",
            "IMG.cr3": "2024_01_15_143052",
            "IMG.dng": "2024_01_15_143052",
        }

        infos, _, _, _ = plan_moves(
            files, dates, Path("/out"), move_raw_to_orig=False,
        )

        # JPEG -> !orig
        assert infos[0].dest_folder == Path("/out/2024_01_15/!orig")
        # RAW -> root (no -r flag)
        assert infos[1].dest_folder == Path("/out/2024_01_15")
        assert infos[2].dest_folder == Path("/out/2024_01_15")

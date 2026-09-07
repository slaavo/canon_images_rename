"""Tests for file discovery and move operations."""

from __future__ import annotations

import errno
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from rename_and_move_files import (
    ScanError,
    find_files,
    move_single_file,
    ensure_folders_exist,
    RAW_EXTENSIONS,
    JPEG_EXTENSIONS,
    ALL_EXTENSIONS,
)


class TestFindFiles:
    """Tests for find_files function."""

    def test_finds_all_supported_extensions(self, sample_photos: Path):
        """Find files with all supported extensions."""
        files = find_files(sample_photos)

        filenames = {f.name for f in files}
        # JPEG
        assert "IMG_001.jpg" in filenames
        assert "IMG_002.JPG" in filenames
        assert "IMG_003.jpeg" in filenames
        # RAW
        assert "IMG_004.cr3" in filenames
        assert "IMG_005.CR3" in filenames
        assert "IMG_006.dng" in filenames
        assert "IMG_007.arw" in filenames
        assert "IMG_008.nef" in filenames
        assert "IMG_009.orf" in filenames
        assert "IMG_010.raf" in filenames
        assert "IMG_011.rw2" in filenames

    def test_ignores_unsupported_extensions(self, sample_photos: Path):
        """Ignore files with unsupported extensions."""
        files = find_files(sample_photos)

        filenames = {f.name for f in files}
        assert "document.pdf" not in filenames
        assert "notes.txt" not in filenames

    def test_finds_correct_count(self, sample_photos: Path):
        """Should find exactly 11 supported files (3 JPEG + 8 RAW)."""
        files = find_files(sample_photos)
        assert len(files) == 11

    def test_empty_directory(self, tmp_path: Path):
        """Empty directory returns empty list."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        files = find_files(empty_dir)
        assert files == []

    def test_directory_with_no_photos(self, tmp_path: Path):
        """Directory with no photos returns empty list."""
        no_photos = tmp_path / "documents"
        no_photos.mkdir()
        (no_photos / "readme.md").touch()
        (no_photos / "data.json").touch()

        files = find_files(no_photos)
        assert files == []

    def test_results_are_sorted(self, sample_photos: Path):
        """Results should be sorted by filename (case-insensitive)."""
        files = find_files(sample_photos)

        names = [f.name.casefold() for f in files]
        assert names == sorted(names)

    def test_ignores_subdirectories(self, sample_photos: Path):
        """Subdirectories should not be traversed."""
        subdir = sample_photos / "subdir"
        subdir.mkdir()
        (subdir / "hidden.jpg").touch()

        files = find_files(sample_photos)

        filenames = {f.name for f in files}
        assert "hidden.jpg" not in filenames

    def test_unreadable_directory_raises_scan_error_and_logs(self, tmp_path: Path):
        """A directory that cannot be read is an error, not "no photos"."""
        nonexistent = tmp_path / "does_not_exist"

        with patch("rename_and_move_files.log.error") as mock_error:
            with pytest.raises(ScanError):
                find_files(nonexistent)

        mock_error.assert_called_once()

    def test_skips_symlinks(self, tmp_path: Path):
        """Symbolic links are not treated as photos (moving them would break relative targets)."""
        photos = tmp_path / "photos"
        photos.mkdir()
        real = photos / "real.jpg"
        real.write_text("data")
        (photos / "link.jpg").symlink_to("real.jpg")

        with patch("rename_and_move_files.log.warning") as mock_warn:
            files = find_files(photos)

        assert [f.name for f in files] == ["real.jpg"]
        mock_warn.assert_called_once()
        assert "1 symbolic link" in mock_warn.call_args[0][0]

    def test_case_insensitive_extensions(self, tmp_path: Path):
        """Extension matching should be case-insensitive."""
        photos = tmp_path / "photos"
        photos.mkdir()

        # Various case combinations
        (photos / "a.jpg").touch()
        (photos / "b.JPG").touch()
        (photos / "c.JpG").touch()
        (photos / "d.CR3").touch()
        (photos / "e.cr3").touch()
        (photos / "f.Cr3").touch()

        files = find_files(photos)
        assert len(files) == 6

    def test_returns_paths(self, tmp_path: Path):
        """find_files returns plain Paths; no per-file metadata is gathered."""
        photos = tmp_path / "photos"
        photos.mkdir()
        (photos / "a.jpg").touch()

        files = find_files(photos)

        assert files == [photos / "a.jpg"]


class TestMoveSingleFile:
    """Tests for move_single_file function."""

    def test_successful_move(self, tmp_path: Path):
        """Successfully move a file."""
        source = tmp_path / "source.jpg"
        source.write_text("test content")
        dest = tmp_path / "dest.jpg"

        result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is True
        assert result.source_name == "source.jpg"
        assert result.dest_path == dest
        assert result.is_duplicate is False
        assert result.error is None
        assert not source.exists()
        assert dest.exists()
        assert dest.read_text() == "test content"

    def test_move_with_duplicate_flag(self, tmp_path: Path):
        """Move with duplicate flag should be recorded in result."""
        source = tmp_path / "source.jpg"
        source.touch()
        dest = tmp_path / "dest_2.jpg"

        result = move_single_file(source, dest, is_duplicate=True)

        assert result.success is True
        assert result.is_duplicate is True

    def test_move_to_subdirectory(self, tmp_path: Path):
        """Move file to a subdirectory."""
        source = tmp_path / "source.jpg"
        source.write_text("photo data")

        subdir = tmp_path / "2024_01_15" / "!orig"
        subdir.mkdir(parents=True)
        dest = subdir / "2024_01_15_143052_source.jpg"

        result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is True
        assert result.source_name == "source.jpg"
        assert result.dest_path == dest
        assert dest.exists()
        assert dest.read_text() == "photo data"

    def test_source_not_found(self, tmp_path: Path):
        """Moving nonexistent file should fail gracefully."""
        source = tmp_path / "nonexistent.jpg"
        dest = tmp_path / "dest.jpg"

        result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is False
        assert result.error is not None
        assert "nonexistent.jpg" in result.source_name

    def test_destination_directory_not_found(self, tmp_path: Path):
        """Moving to nonexistent directory should fail gracefully."""
        source = tmp_path / "source.jpg"
        source.touch()
        dest = tmp_path / "nonexistent_dir" / "dest.jpg"

        result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is False
        assert result.error is not None

    def test_cross_device_move_copies_exclusively(self, tmp_path: Path):
        """EXDEV from os.link → copy with exclusive create, then delete source."""
        source = tmp_path / "source.jpg"
        source.write_text("cross device content")
        dest = tmp_path / "dest.jpg"

        with patch(
            "rename_and_move_files.os.link",
            side_effect=OSError(errno.EXDEV, "Invalid cross-device link"),
        ):
            result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is True
        assert dest.exists()
        assert dest.read_text() == "cross device content"
        assert not source.exists()

    def test_cross_device_move_refuses_existing_dest(self, tmp_path: Path):
        """The cross-device copy must not overwrite either."""
        source = tmp_path / "source.jpg"
        source.write_text("new")
        dest = tmp_path / "dest.jpg"
        dest.write_text("precious original")

        with patch(
            "rename_and_move_files.os.link",
            side_effect=OSError(errno.EXDEV, "Invalid cross-device link"),
        ):
            result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is False
        assert "already exists" in result.error
        assert dest.read_text() == "precious original"
        assert source.exists()

    def test_claim_path_when_hard_links_unsupported(self, tmp_path: Path):
        """FAT-style EPERM from os.link → O_EXCL placeholder + replace."""
        source = tmp_path / "source.jpg"
        source.write_text("sd card content")
        dest = tmp_path / "dest.jpg"

        with patch(
            "rename_and_move_files.os.link",
            side_effect=OSError(errno.EPERM, "Operation not permitted"),
        ):
            result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is True
        assert dest.read_text() == "sd card content"
        assert not source.exists()

    def test_claim_path_refuses_existing_dest(self, tmp_path: Path):
        """Without hard links, an existing destination is still never replaced."""
        source = tmp_path / "source.jpg"
        source.write_text("new")
        dest = tmp_path / "dest.jpg"
        dest.write_text("precious original")

        with patch(
            "rename_and_move_files.os.link",
            side_effect=OSError(errno.EPERM, "Operation not permitted"),
        ):
            result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is False
        assert dest.read_text() == "precious original"
        assert source.exists()

    def test_link_rolled_back_when_source_unlink_fails(self, tmp_path: Path):
        """os.link succeeded but the source cannot be removed: no dest left behind."""
        source = tmp_path / "source.jpg"
        source.write_text("content")
        dest = tmp_path / "dest.jpg"
        real_unlink = os.unlink

        def unlink_fails_for_source(path, *args, **kwargs):
            if Path(path) == source:
                raise PermissionError(errno.EACCES, "Permission denied", str(path))
            return real_unlink(path, *args, **kwargs)

        with patch("rename_and_move_files.os.unlink", side_effect=unlink_fails_for_source):
            result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is False
        assert "Permission denied" in result.error
        assert not dest.exists()
        assert source.read_text() == "content"

    def test_cross_device_copy_rolled_back_when_source_unlink_fails(self, tmp_path: Path):
        """Same guarantee on the EXDEV copy path."""
        source = tmp_path / "source.jpg"
        source.write_text("content")
        dest = tmp_path / "dest.jpg"
        real_unlink = os.unlink

        def unlink_fails_for_source(path, *args, **kwargs):
            if Path(path) == source:
                raise PermissionError(errno.EACCES, "Permission denied", str(path))
            return real_unlink(path, *args, **kwargs)

        with patch(
            "rename_and_move_files.os.link",
            side_effect=OSError(errno.EXDEV, "Invalid cross-device link"),
        ):
            with patch("rename_and_move_files.os.unlink", side_effect=unlink_fails_for_source):
                result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is False
        assert not dest.exists()
        assert source.read_text() == "content"

    def test_refuses_to_overwrite_existing_destination(self, tmp_path: Path):
        """A file created at dest after the name scan must never be clobbered."""
        source = tmp_path / "source.jpg"
        source.write_text("new")
        dest = tmp_path / "dest.jpg"
        dest.write_text("precious original")

        result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is False
        assert "already exists" in result.error
        assert dest.read_text() == "precious original"
        assert source.exists()

    def test_directory_named_like_dest_is_error(self, tmp_path: Path):
        """A directory at the destination path is a collision, not a place to move into."""
        source = tmp_path / "source.jpg"
        source.write_text("photo")
        dest = tmp_path / "dest.jpg"
        dest.mkdir()

        result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is False
        assert source.exists()
        assert not (dest / "source.jpg").exists()

    def test_source_not_found_leaves_no_placeholder(self, tmp_path: Path):
        """A failed move must not leave an empty placeholder at the destination."""
        source = tmp_path / "nonexistent.jpg"
        dest = tmp_path / "dest.jpg"

        result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is False
        assert not dest.exists()


class TestEnsureFoldersExist:
    """Tests for ensure_folders_exist function."""

    def test_creates_date_folders(self, tmp_path: Path):
        """Create date folders with subfolders."""
        date_folders = {"2024_01_15", "2024_01_16"}

        ensure_folders_exist(tmp_path, date_folders)

        assert (tmp_path / "2024_01_15").is_dir()
        assert (tmp_path / "2024_01_15" / "!jpg").is_dir()
        assert (tmp_path / "2024_01_15" / "!orig").is_dir()
        assert (tmp_path / "2024_01_16").is_dir()
        assert (tmp_path / "2024_01_16" / "!jpg").is_dir()
        assert (tmp_path / "2024_01_16" / "!orig").is_dir()

    def test_idempotent(self, tmp_path: Path):
        """Creating existing folders should not raise."""
        date_folders = {"2024_01_15"}

        # Create twice
        ensure_folders_exist(tmp_path, date_folders)
        ensure_folders_exist(tmp_path, date_folders)

        assert (tmp_path / "2024_01_15").is_dir()

    def test_empty_set(self, tmp_path: Path):
        """Empty set should do nothing."""
        ensure_folders_exist(tmp_path, set())
        # Should not raise


class TestExtensionConstants:
    """Tests for extension constant definitions."""

    def test_raw_extensions_are_lowercase(self):
        """All RAW extensions should be lowercase."""
        for ext in RAW_EXTENSIONS:
            assert ext == ext.lower()
            assert ext.startswith(".")

    def test_jpeg_extensions_are_lowercase(self):
        """All JPEG extensions should be lowercase."""
        for ext in JPEG_EXTENSIONS:
            assert ext == ext.lower()
            assert ext.startswith(".")

    def test_all_extensions_is_union(self):
        """ALL_EXTENSIONS should be union of RAW and JPEG."""
        assert ALL_EXTENSIONS == RAW_EXTENSIONS | JPEG_EXTENSIONS

    def test_expected_raw_formats(self):
        """Common RAW formats should be included."""
        assert ".cr3" in RAW_EXTENSIONS  # Canon
        assert ".dng" in RAW_EXTENSIONS  # Adobe
        assert ".arw" in RAW_EXTENSIONS  # Sony
        assert ".nef" in RAW_EXTENSIONS  # Nikon

    def test_expected_jpeg_formats(self):
        """Common JPEG formats should be included."""
        assert ".jpg" in JPEG_EXTENSIONS
        assert ".jpeg" in JPEG_EXTENSIONS

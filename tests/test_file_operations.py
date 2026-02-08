"""Tests for file discovery and move operations."""

from __future__ import annotations

from pathlib import Path

from rename_and_move_files import (
    find_files,
    move_single_file,
    ensure_folders_exist,
    RAW_EXTENSIONS,
    JPEG_EXTENSIONS,
    ALL_EXTENSIONS,
)


class TestFindFiles:
    """Tests for find_files function."""

    def test_finds_supported_extensions(self, sample_photos: Path):
        """Find files with supported extensions."""
        files = find_files(sample_photos)

        filenames = {f.name for f in files}
        assert "IMG_001.jpg" in filenames
        assert "IMG_002.JPG" in filenames
        assert "IMG_003.cr3" in filenames
        assert "IMG_004.CR3" in filenames
        assert "IMG_005.dng" in filenames

    def test_ignores_unsupported_extensions(self, sample_photos: Path):
        """Ignore files with unsupported extensions."""
        files = find_files(sample_photos)

        filenames = {f.name for f in files}
        assert "document.pdf" not in filenames
        assert "notes.txt" not in filenames

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

    def test_nonexistent_directory(self, tmp_path: Path):
        """Nonexistent directory returns empty list."""
        nonexistent = tmp_path / "does_not_exist"

        files = find_files(nonexistent)
        assert files == []

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
        source.touch()

        subdir = tmp_path / "2024_01_15" / "!orig"
        subdir.mkdir(parents=True)
        dest = subdir / "photo.jpg"

        result = move_single_file(source, dest, is_duplicate=False)

        assert result.success is True
        assert dest.exists()

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

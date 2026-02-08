"""Tests for UniqueFilenameGenerator."""

from __future__ import annotations

from pathlib import Path

from rename_and_move_files import UniqueFilenameGenerator


class TestUniqueFilenameGenerator:
    """Tests for unique filename generation."""

    def test_no_conflict_returns_original(self, tmp_path: Path):
        """When no conflict exists, return the original filename."""
        gen = UniqueFilenameGenerator()
        result = gen.generate(tmp_path, "photo.jpg")
        assert result == "photo.jpg"

    def test_conflict_with_existing_file(self, tmp_path: Path):
        """When file exists on disk, append _2."""
        (tmp_path / "photo.jpg").touch()

        gen = UniqueFilenameGenerator()
        result = gen.generate(tmp_path, "photo.jpg")
        assert result == "photo_2.jpg"

    def test_multiple_conflicts(self, tmp_path: Path):
        """When multiple conflicts exist, increment counter."""
        (tmp_path / "photo.jpg").touch()
        (tmp_path / "photo_2.jpg").touch()
        (tmp_path / "photo_3.jpg").touch()

        gen = UniqueFilenameGenerator()
        result = gen.generate(tmp_path, "photo.jpg")
        assert result == "photo_4.jpg"

    def test_conflict_with_allocated_names(self, tmp_path: Path):
        """Track allocated names within session (for dry-run accuracy)."""
        gen = UniqueFilenameGenerator()

        # First allocation
        result1 = gen.generate(tmp_path, "photo.jpg")
        assert result1 == "photo.jpg"

        # Same name requested again - should get _2
        result2 = gen.generate(tmp_path, "photo.jpg")
        assert result2 == "photo_2.jpg"

        # Third time - should get _3
        result3 = gen.generate(tmp_path, "photo.jpg")
        assert result3 == "photo_3.jpg"

    def test_mixed_existing_and_allocated(self, tmp_path: Path):
        """Combine existing files and allocated names correctly."""
        (tmp_path / "photo.jpg").touch()
        (tmp_path / "photo_2.jpg").touch()

        gen = UniqueFilenameGenerator()

        # Allocate photo_3.jpg
        result1 = gen.generate(tmp_path, "photo.jpg")
        assert result1 == "photo_3.jpg"

        # Next should be _4
        result2 = gen.generate(tmp_path, "photo.jpg")
        assert result2 == "photo_4.jpg"

    def test_different_extensions(self, tmp_path: Path):
        """Different extensions should not conflict."""
        gen = UniqueFilenameGenerator()

        result1 = gen.generate(tmp_path, "photo.jpg")
        result2 = gen.generate(tmp_path, "photo.cr3")

        assert result1 == "photo.jpg"
        assert result2 == "photo.cr3"

    def test_different_folders(self, tmp_path: Path):
        """Same filename in different folders should not conflict."""
        folder1 = tmp_path / "2024_01_15"
        folder2 = tmp_path / "2024_01_16"
        folder1.mkdir()
        folder2.mkdir()

        gen = UniqueFilenameGenerator()

        result1 = gen.generate(folder1, "photo.jpg")
        result2 = gen.generate(folder2, "photo.jpg")

        assert result1 == "photo.jpg"
        assert result2 == "photo.jpg"

    def test_filename_without_extension(self, tmp_path: Path):
        """Handle filenames without extension."""
        (tmp_path / "README").touch()

        gen = UniqueFilenameGenerator()
        result = gen.generate(tmp_path, "README")
        assert result == "README_2"

    def test_hidden_file(self, tmp_path: Path):
        """Handle hidden files (starting with dot)."""
        (tmp_path / ".hidden").touch()

        gen = UniqueFilenameGenerator()
        result = gen.generate(tmp_path, ".hidden")
        assert result == ".hidden_2"

    def test_preserves_extension_case(self, tmp_path: Path):
        """Extension case should be preserved."""
        (tmp_path / "photo.JPG").touch()

        gen = UniqueFilenameGenerator()
        result = gen.generate(tmp_path, "photo.JPG")
        assert result == "photo_2.JPG"

    def test_nonexistent_folder(self, tmp_path: Path):
        """Handle nonexistent folder gracefully (for dry-run)."""
        nonexistent = tmp_path / "does_not_exist"

        gen = UniqueFilenameGenerator()
        result = gen.generate(nonexistent, "photo.jpg")
        assert result == "photo.jpg"

    def test_caching_existing_files(self, tmp_path: Path):
        """Existing files should be cached per folder."""
        (tmp_path / "photo.jpg").touch()

        gen = UniqueFilenameGenerator()

        # First call caches
        gen.generate(tmp_path, "other.jpg")

        # Create new file after cache
        (tmp_path / "new.jpg").touch()

        # Cache should still be used (new.jpg not seen)
        result = gen.generate(tmp_path, "new.jpg")
        assert result == "new.jpg"  # Would be new_2.jpg if cache refreshed

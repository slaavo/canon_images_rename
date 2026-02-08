"""Tests for main() CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from rename_and_move_files import main


class TestMain:
    """Tests for main() function and CLI argument parsing."""

    def test_nonexistent_input_folder(self, tmp_path: Path):
        """Return 1 when input folder does not exist."""
        fake_dir = str(tmp_path / "nonexistent")

        with patch.object(sys, "argv", ["prog", fake_dir]):
            result = main()

        assert result == 1

    def test_missing_exiftool(self, tmp_path: Path):
        """Return 1 when exiftool is not installed."""
        with patch.object(sys, "argv", ["prog", str(tmp_path)]):
            with patch("rename_and_move_files.check_exiftool", return_value=False):
                result = main()

        assert result == 1

    def test_invalid_paths(self, tmp_path: Path):
        """Return 1 when output is inside input."""
        input_dir = tmp_path / "photos"
        output_dir = input_dir / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        with patch.object(sys, "argv", ["prog", "-o", str(output_dir), str(input_dir)]):
            with patch("rename_and_move_files.check_exiftool", return_value=True):
                result = main()

        assert result == 1

    def test_successful_run_no_files(self, tmp_path: Path):
        """Return 0 when processing succeeds with no files."""
        with patch.object(sys, "argv", ["prog", str(tmp_path)]):
            with patch("rename_and_move_files.check_exiftool", return_value=True):
                result = main()

        assert result == 0

    def test_workers_too_low(self):
        """Workers < 1 should cause argument error (exit code 2)."""
        with patch.object(sys, "argv", ["prog", "-w", "0", "."]):
            try:
                main()
                assert False, "Should have raised SystemExit"
            except SystemExit as e:
                assert e.code == 2

    def test_workers_too_high(self):
        """Workers > MAX_WORKERS should cause argument error (exit code 2)."""
        with patch.object(sys, "argv", ["prog", "-w", "999", "."]):
            try:
                main()
                assert False, "Should have raised SystemExit"
            except SystemExit as e:
                assert e.code == 2

    def test_verbose_flag(self, tmp_path: Path):
        """Verbose flag should reconfigure logging without errors."""
        with patch.object(sys, "argv", ["prog", "-v", str(tmp_path)]):
            with patch("rename_and_move_files.check_exiftool", return_value=True):
                result = main()

        assert result == 0

    def test_dry_run_flag(self, tmp_path: Path):
        """Dry run flag should be passed through to process_files."""
        with patch.object(sys, "argv", ["prog", "-d", str(tmp_path)]):
            with patch("rename_and_move_files.check_exiftool", return_value=True):
                with patch("rename_and_move_files.process_files", return_value=(0, 0)) as mock_pf:
                    result = main()

        assert result == 0
        # dry_run should be True in the call
        _, kwargs = mock_pf.call_args
        # process_files is called with positional args
        call_args = mock_pf.call_args
        assert call_args[1].get("dry_run", call_args[0][3]) is True

    def test_output_folder_created(self, tmp_path: Path):
        """Output folder should be created if it doesn't exist."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "new_output"

        with patch.object(sys, "argv", ["prog", "-o", str(output_dir), str(input_dir)]):
            with patch("rename_and_move_files.check_exiftool", return_value=True):
                main()

        assert output_dir.is_dir()

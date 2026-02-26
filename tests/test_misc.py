"""Tests for InterruptHandler, print_progress, and ColorFormatter."""

from __future__ import annotations

import io
import logging
import signal
from unittest.mock import patch

from rename_and_move_files import (
    InterruptHandler,
    print_progress,
    ColorFormatter,
)


class TestInterruptHandler:
    """Tests for InterruptHandler context manager."""

    def test_initial_state(self):
        """Handler should start as not interrupted."""
        handler = InterruptHandler()
        assert handler.interrupted is False
        assert handler.processed_count == 0

    def test_sets_interrupted_flag(self):
        """Calling _handler should set interrupted flag."""
        handler = InterruptHandler()
        with handler:
            handler._handler(signal.SIGINT, None)
            assert handler.interrupted is True

    def test_restores_original_handler(self):
        """Original signal handler should be restored on exit."""
        original = signal.getsignal(signal.SIGINT)

        with InterruptHandler():
            # Inside context, handler is replaced
            current = signal.getsignal(signal.SIGINT)
            assert current != original

        # After exit, original is restored
        restored = signal.getsignal(signal.SIGINT)
        assert restored == original

    def test_context_manager_returns_self(self):
        """__enter__ should return the handler instance."""
        handler = InterruptHandler()
        with handler as h:
            assert h is handler

    def test_processed_count_tracking(self):
        """processed_count should be manually updatable."""
        handler = InterruptHandler()
        handler.processed_count = 42
        assert handler.processed_count == 42


class TestPrintProgress:
    """Tests for print_progress function."""

    def test_prints_at_100_percent(self, capsys):
        """Should always print at 100%."""
        print_progress(10, 10)
        captured = capsys.readouterr()
        assert "100%" in captured.out

    def test_prints_at_interval(self, capsys):
        """Should print when current matches update_interval."""
        print_progress(5, 100, update_interval=5)
        captured = capsys.readouterr()
        assert "5%" in captured.out

    def test_skips_between_intervals(self, capsys):
        """Should not print between intervals."""
        print_progress(3, 100, update_interval=5)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_progress_bar_format(self, capsys):
        """Output should contain progress bar elements."""
        print_progress(50, 100, update_interval=1)
        captured = capsys.readouterr()
        assert "Progress:" in captured.out
        assert "50/100" in captured.out


class TestColorFormatter:
    """Tests for ColorFormatter logging formatter."""

    def test_formats_with_color(self):
        """Log output should contain ANSI color codes."""
        formatter = ColorFormatter("%(levelname)s %(message)s")
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None,
        )

        result = formatter.format(record)

        assert "\033[0;32m" in result  # Green for INFO
        assert "\033[0m" in result     # Reset
        assert "test message" in result

    def test_error_uses_red(self):
        """ERROR level should use red color."""
        formatter = ColorFormatter("%(levelname)s %(message)s")
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="error msg", args=(), exc_info=None,
        )

        result = formatter.format(record)
        assert "\033[0;31m" in result  # Red

    def test_warning_uses_yellow(self):
        """WARNING level should use yellow color."""
        formatter = ColorFormatter("%(levelname)s %(message)s")
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0,
            msg="warn msg", args=(), exc_info=None,
        )

        result = formatter.format(record)
        assert "\033[1;33m" in result  # Yellow

    def test_does_not_mutate_original_record(self):
        """Formatting should not modify the original record."""
        formatter = ColorFormatter("%(levelname)s %(message)s")
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test", args=(), exc_info=None,
        )
        original_levelname = record.levelname

        formatter.format(record)

        assert record.levelname == original_levelname

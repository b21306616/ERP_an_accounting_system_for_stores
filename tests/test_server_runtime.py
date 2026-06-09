"""Tests for the Windows service API runtime."""

from __future__ import annotations

import sys
import unittest

import uvicorn


class ServerRuntimeLoggingTests(unittest.TestCase):
    """Validate uvicorn logging works in a headless Windows service context."""

    def test_uvicorn_logging_configures_without_console_streams(self) -> None:
        """Service processes have no stdout/stderr; logging must not call isatty()."""

        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = None  # type: ignore[assignment]
        sys.stderr = None  # type: ignore[assignment]
        try:
            config = uvicorn.Config(None, log_level="info", use_colors=False)
            config.configure_logging()
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr


if __name__ == "__main__":
    unittest.main()

"""Tests for the Windows service API runtime."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

import uvicorn

from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig
from server_app.core.network import PortCheckResult, PortCheckStatus
from server_app.server_runtime import ApiServiceRuntime


def make_config() -> AppConfig:
    """Return a minimal runtime config."""

    return AppConfig(
        database=DatabaseConfig(server="localhost", database="ERPAccounting"),
        api=ApiConfig(host="127.0.0.1", port=8123),
        jwt_secret="jwt-secret",
    )


def make_port_result(status: PortCheckStatus, message: str) -> PortCheckResult:
    """Return a representative port check result."""

    return PortCheckResult(
        host="127.0.0.1",
        port=8123,
        bind_host="127.0.0.1",
        status=status,
        message=message,
    )


class FakeConfigManager:
    """Return a fixed config to the runtime."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def load(self) -> AppConfig:
        return self.config


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

    def test_prepare_rejects_unavailable_port_before_database_work(self) -> None:
        """Service runtime should fail fast when the configured port cannot bind."""

        runtime = ApiServiceRuntime(FakeConfigManager(make_config()))  # type: ignore[arg-type]
        blocked = make_port_result(
            PortCheckStatus.ACCESS_DENIED_OR_RESERVED,
            "Windows denied access to port 8123 on 127.0.0.1.",
        )

        with (
            patch("server_app.server_runtime.check_tcp_port", return_value=blocked),
            patch("server_app.server_runtime.prepare_existing_database") as prepare_existing_database,
        ):
            with self.assertRaisesRegex(RuntimeError, "Windows denied access"):
                runtime.prepare()

        prepare_existing_database.assert_not_called()

    def test_run_converts_uvicorn_system_exit_to_runtime_error(self) -> None:
        """Uvicorn bind exits should become loggable service startup errors."""

        runtime = ApiServiceRuntime(FakeConfigManager(make_config()))  # type: ignore[arg-type]
        runtime.config = make_config()
        runtime.server = MagicMock()
        runtime.server.run.side_effect = SystemExit(1)
        available = make_port_result(
            PortCheckStatus.AVAILABLE,
            "Port 8123 is available on 127.0.0.1.",
        )

        with patch("server_app.server_runtime.check_tcp_port", return_value=available):
            with self.assertRaisesRegex(RuntimeError, "API server exited during startup"):
                runtime.run()


if __name__ == "__main__":
    unittest.main()

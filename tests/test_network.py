"""Tests for network port availability helpers."""

from __future__ import annotations

import socket
import unittest
from unittest.mock import MagicMock, patch

from server_app.core.network import (
    PortCheckStatus,
    check_tcp_port,
    format_port_unavailable_message,
    is_port_bind_error_message,
    is_tcp_port_available,
    normalize_bind_host,
)


def oserror_with_winerror(winerror: int, message: str) -> OSError:
    """Build a Windows-like socket error for cross-platform tests."""

    exc = OSError(message)
    exc.winerror = winerror  # type: ignore[attr-defined]
    return exc


class NetworkHelperTests(unittest.TestCase):
    """Validate port bind checks and user-facing messages."""

    def test_normalize_bind_host_maps_wildcard_to_empty(self) -> None:
        self.assertEqual(normalize_bind_host("0.0.0.0"), "")
        self.assertEqual(normalize_bind_host("::"), "::")
        self.assertEqual(normalize_bind_host(""), "")
        self.assertEqual(normalize_bind_host("127.0.0.1"), "127.0.0.1")

    def test_check_tcp_port_rejects_invalid_port(self) -> None:
        result = check_tcp_port("0.0.0.0", 70000)

        self.assertEqual(result.status, PortCheckStatus.INVALID_PORT)
        self.assertFalse(result.available)
        self.assertIn("between 1 and 65535", result.message)

    def test_check_tcp_port_rejects_invalid_host(self) -> None:
        with patch("server_app.core.network.socket.socket") as socket_ctor:
            sock = MagicMock()
            sock.bind.side_effect = socket.gaierror("name or service not known")
            socket_ctor.return_value = sock

            result = check_tcp_port("bad host name", 8000)

        self.assertEqual(result.status, PortCheckStatus.INVALID_HOST)
        self.assertIn("not a valid host", result.message)
        sock.close.assert_called_once()

    def test_check_tcp_port_rejects_unassigned_local_host(self) -> None:
        with patch("server_app.core.network.socket.socket") as socket_ctor:
            sock = MagicMock()
            sock.bind.side_effect = oserror_with_winerror(10049, "address is not valid")
            socket_ctor.return_value = sock

            result = check_tcp_port("192.0.2.55", 8000)

        self.assertEqual(result.status, PortCheckStatus.HOST_NOT_LOCAL)
        self.assertIn("not assigned to this PC", result.message)

    def test_check_tcp_port_reports_in_use(self) -> None:
        with patch("server_app.core.network.socket.socket") as socket_ctor:
            sock = MagicMock()
            sock.bind.side_effect = oserror_with_winerror(10048, "address already in use")
            socket_ctor.return_value = sock

            result = check_tcp_port("0.0.0.0", 8000)

        self.assertEqual(result.status, PortCheckStatus.IN_USE)
        self.assertIn("already in use", result.full_message)
        self.assertIn("netstat -ano | findstr :8000", result.full_message)

    def test_check_tcp_port_reports_access_denied_or_reserved(self) -> None:
        with patch("server_app.core.network.socket.socket") as socket_ctor:
            sock = MagicMock()
            sock.bind.side_effect = oserror_with_winerror(10013, "access denied")
            socket_ctor.return_value = sock

            result = check_tcp_port("0.0.0.0", 8000)

        self.assertEqual(result.status, PortCheckStatus.ACCESS_DENIED_OR_RESERVED)
        self.assertIn("Windows denied access", result.full_message)
        self.assertIn("netstat -ano | findstr :8000", result.full_message)

    def test_check_tcp_port_does_not_use_reuseaddr_for_preflight(self) -> None:
        with patch("server_app.core.network.socket.socket") as socket_ctor:
            sock = MagicMock()
            socket_ctor.return_value = sock

            result = check_tcp_port("127.0.0.1", 8000)

        self.assertEqual(result.status, PortCheckStatus.AVAILABLE)
        sock.setsockopt.assert_not_called()

    def test_is_tcp_port_available_returns_true_when_bind_succeeds(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        self.assertTrue(is_tcp_port_available("127.0.0.1", port))

    def test_format_port_unavailable_message_includes_diagnostic_for_port_failures(self) -> None:
        with patch("server_app.core.network.socket.socket") as socket_ctor:
            sock = MagicMock()
            sock.bind.side_effect = oserror_with_winerror(10048, "address already in use")
            socket_ctor.return_value = sock

            message = format_port_unavailable_message(8000, "0.0.0.0")

        self.assertIn("8000", message)
        self.assertIn("netstat -ano | findstr :8000", message)
        self.assertIn("5000", message)

    def test_is_port_bind_error_message_detects_known_bind_failures(self) -> None:
        self.assertTrue(is_port_bind_error_message("error while attempting to bind on address"))
        self.assertTrue(is_port_bind_error_message("[WinError 10048] address already in use"))
        self.assertFalse(is_port_bind_error_message("health endpoint timed out"))


if __name__ == "__main__":
    unittest.main()

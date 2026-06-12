"""Tests for endpoint-client core helpers."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from user_app.api.client import ApiClient
from user_app.core.config import ClientConfig, ClientConfigManager, normalize_server_url
from user_app.hardware.simulator import HardwareSimulator


class ClientCoreTests(unittest.TestCase):
    """Validate client config, API envelope parsing, and hardware simulation."""

    def test_normalize_server_url_adds_protocol_and_api_v1(self) -> None:
        """Server URLs should always target API v1."""

        self.assertEqual(normalize_server_url("127.0.0.1:8000"), "http://127.0.0.1:8000/api/v1")
        self.assertEqual(normalize_server_url("http://host:8000/api/v1"), "http://host:8000/api/v1")

    def test_config_manager_roundtrips_config(self) -> None:
        """Client config should save and load JSON."""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            manager = ClientConfigManager(path)
            manager.save(ClientConfig(server_url="http://server:8000/api/v1", language="tk"))

            loaded = manager.load()

        self.assertEqual(loaded.server_url, "http://server:8000/api/v1")
        self.assertEqual(loaded.language, "tk")

    def test_api_client_login_parses_envelope(self) -> None:
        """The API client should parse successful login envelopes."""

        client = ApiClient("server:8000")
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "data": {
                "session_token": "token",
                "expires_at": "2026-06-12T00:00:00+00:00",
                "user": {
                    "id": 1,
                    "username": "super_admin",
                    "full_name": "Super Admin",
                    "role_name": "Super Admin",
                    "permissions": ["admin.manage_users"],
                },
            },
            "error": None,
            "meta": None,
        }
        client.session.request = Mock(return_value=response)  # type: ignore[method-assign]

        user = client.login("super_admin", "secret")

        self.assertEqual(client.session_token, "token")
        self.assertEqual(user.username, "super_admin")
        self.assertEqual(user.permissions, ["admin.manage_users"])

    def test_hardware_simulator_records_operations(self) -> None:
        """Hardware simulator should behave predictably."""

        hardware = HardwareSimulator()

        self.assertEqual(hardware.scan("123"), "123")
        self.assertIn("Printed", hardware.print_receipt(["A", "B"]))
        self.assertEqual(hardware.open_drawer(), "Cash drawer opened.")
        self.assertEqual(hardware.read_weight(), Decimal("1.000"))
        self.assertIn("0.00", hardware.register_operation(Decimal("0.00")))
        self.assertEqual(len(hardware.printed_receipts), 1)
        self.assertEqual(hardware.drawer_open_count, 1)
        self.assertEqual(len(hardware.fiscal_operations), 1)


if __name__ == "__main__":
    unittest.main()

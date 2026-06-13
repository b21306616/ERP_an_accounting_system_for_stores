"""Tests for endpoint-client core helpers."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from user_app.api.client import ApiClient
from user_app.core.config import ClientConfig, ClientConfigManager, normalize_server_url
from user_app.core.i18n import TRANSLATIONS, Translator
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

    def test_config_manager_roundtrips_english_language(self) -> None:
        """English language preference should persist in config."""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            manager = ClientConfigManager(path)
            manager.save(ClientConfig(server_url="http://server:8000/api/v1", language="en"))

            loaded = manager.load()

        self.assertEqual(loaded.language, "en")

    def test_config_manager_rejects_invalid_language(self) -> None:
        """Unknown language codes should fall back to Russian."""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text('{"server_url": "http://server:8000/api/v1", "language": "fr"}', encoding="utf-8")
            loaded = ClientConfigManager(path).load()

        self.assertEqual(loaded.language, "ru")

    def test_translator_returns_english_strings(self) -> None:
        """Translator should return English labels when language is en."""

        translator = Translator("en")

        self.assertEqual(translator.text("login.title"), "Sign in")
        self.assertEqual(translator.text("nav.dashboard"), "Dashboard")

    def test_translator_switches_language(self) -> None:
        """Translator should update labels after set_language."""

        translator = Translator("ru")
        translator.set_language("en")

        self.assertEqual(translator.language, "en")
        self.assertEqual(translator.text("common.error"), "Error")

    def test_translation_key_parity_across_languages(self) -> None:
        """All supported languages should define the same translation keys."""

        ru_keys = set(TRANSLATIONS["ru"])
        tk_keys = set(TRANSLATIONS["tk"])
        en_keys = set(TRANSLATIONS["en"])

        self.assertEqual(ru_keys, tk_keys)
        self.assertEqual(ru_keys, en_keys)

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

    def test_api_client_catalog_helpers_use_envelopes(self) -> None:
        """Catalog helpers should return envelope data."""

        client = ApiClient("server:8000")
        client.session_token = "token"
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "data": [{"id": 1, "sku": "P-001", "name": "Sugar"}],
            "error": None,
            "meta": None,
        }
        client.session.request = Mock(return_value=response)  # type: ignore[method-assign]

        products = client.get_products("Sugar")

        self.assertEqual(products[0]["sku"], "P-001")
        called_url = client.session.request.call_args.args[1]
        self.assertIn("/products?search=Sugar", called_url)

    def test_api_client_warehouse_helpers_use_query_params(self) -> None:
        """Warehouse helpers should return envelope data and query by ids."""

        client = ApiClient("server:8000")
        client.session_token = "token"
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "data": [{"warehouse_id": 2, "product_id": 3, "quantity": "5.000"}],
            "error": None,
            "meta": None,
        }
        client.session.request = Mock(return_value=response)  # type: ignore[method-assign]

        balances = client.get_stock_balances(warehouse_id=2, product_id=3)

        self.assertEqual(balances[0]["quantity"], "5.000")
        called_url = client.session.request.call_args.args[1]
        self.assertIn("/stock/balances?warehouse_id=2&product_id=3", called_url)

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

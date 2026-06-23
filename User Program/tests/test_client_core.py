"""Tests for endpoint-client core helpers."""

from __future__ import annotations

from decimal import Decimal
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from user_app.api.client import ApiClient
from user_app.core.config import ClientConfig, ClientConfigManager, normalize_server_url
from user_app.core.i18n import TRANSLATIONS, Translator
from user_app.hardware.interfaces import BarcodeScanner, CashDrawer, FiscalDevice, ReceiptPrinter, ScaleDevice
from user_app.hardware.simulator import HardwareSimulator


class ClientCoreTests(unittest.TestCase):
    """Validate client config, API envelope parsing, and hardware simulation."""

    def test_normalize_server_url_adds_protocol_and_api_v1(self) -> None:
        """Server URLs should always target API v1."""

        self.assertEqual(normalize_server_url("127.0.0.1:8000"), "http://127.0.0.1:8000/api/v1")
        self.assertEqual(normalize_server_url("192.168.1.10:8000"), "http://192.168.1.10:8000/api/v1")
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

    def test_refreshed_ui_translation_keys_match_all_languages(self) -> None:
        """New admin UI translation keys should exist for every supported language."""

        prefixes = ("ui.", "field.", "report_code.", "debt_type.", "cashier.error.", "error.")
        for prefix in prefixes:
            grouped = {
                language: {key for key in values if key.startswith(prefix)}
                for language, values in TRANSLATIONS.items()
            }
            expected = set().union(*grouped.values())
            for language, keys in grouped.items():
                self.assertEqual(keys, expected, f"{language} is missing {prefix} keys")

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

    def test_api_client_purchase_helpers_use_envelopes(self) -> None:
        """Purchase and settlement helpers should return envelope data."""

        client = ApiClient("server:8000")
        client.session_token = "token"
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "data": [{"id": 5, "name": "Supplier", "payable_balance": "20.00"}],
            "error": None,
            "meta": None,
        }
        client.session.request = Mock(return_value=response)  # type: ignore[method-assign]

        counterparties = client.get_counterparties("Supplier", include_debt=True)

        self.assertEqual(counterparties[0]["payable_balance"], "20.00")
        called_url = client.session.request.call_args.args[1]
        self.assertIn("/counterparties?search=Supplier&include_debt=true", called_url)

        response.json.return_value = {
            "success": True,
            "data": {"id": 7, "status": "draft"},
            "error": None,
            "meta": None,
        }
        order = client.create_purchase_order({"counterparty_id": 5, "warehouse_id": 2, "lines": []})
        client.send_purchase_order(order["id"])
        client.cancel_purchase_order(order["id"])
        invoice = client.create_purchase_invoice({"counterparty_id": 5, "warehouse_id": 2, "lines": []})
        client.create_purchase_return({"counterparty_id": 5, "warehouse_id": 2, "lines": []})
        client.post_purchase_invoice(invoice["id"])
        client.cancel_purchase_invoice(invoice["id"])
        client.create_payment({"counterparty_id": 5, "amount_cur": "10.00"})

        requested_paths = [call.args[1] for call in client.session.request.call_args_list[-8:]]
        self.assertIn("/purchase-orders", requested_paths[0])
        self.assertIn("/purchase-orders/7/send", requested_paths[1])
        self.assertIn("/purchase-orders/7/cancel", requested_paths[2])
        self.assertIn("/purchase-invoices", requested_paths[3])
        self.assertIn("/purchase-invoices/return", requested_paths[4])
        self.assertIn("/purchase-invoices/7/post", requested_paths[5])
        self.assertIn("/purchase-invoices/7/cancel", requested_paths[6])
        self.assertIn("/payments", requested_paths[7])

    def test_api_client_counterparty_finance_helpers_use_envelopes(self) -> None:
        """Stage 4 counterparty finance helpers should target API v1 paths."""

        client = ApiClient("server:8000")
        client.session_token = "token"
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "data": {"counterparty_id": 7, "receivable_tmt": "10.00"},
            "error": None,
            "meta": None,
        }
        client.session.request = Mock(return_value=response)  # type: ignore[method-assign]

        client.get_counterparty_debt(7)
        client.get_counterparty_account_card(7, date_from="2026-01-01T00:00:00+00:00", contract_id=3)
        client.get_counterparty_reconciliation(7, date_to="2026-12-31T23:59:59+00:00", contract_id=3)

        response.json.return_value = {
            "success": True,
            "data": [{"id": 3, "number": "C-1"}],
            "error": None,
            "meta": None,
        }
        client.get_contracts(counterparty_id=7, active_only=True)

        response.json.return_value = {
            "success": True,
            "data": {"id": 3, "number": "C-1"},
            "error": None,
            "meta": None,
        }
        client.create_contract({"counterparty_id": 7, "number": "C-1"})
        client.update_contract(3, {"title": "Updated"})

        response.json.return_value = {
            "success": True,
            "data": [{"id": 10, "amount_tmt": "5.00"}],
            "error": None,
            "meta": None,
        }
        ledger = client.get_debt_ledger(counterparty_id=7, debt_type="receivable", contract_id=3)

        self.assertEqual(ledger[0]["amount_tmt"], "5.00")
        requested_paths = [call.args[1] for call in client.session.request.call_args_list[-7:]]
        self.assertIn("/counterparties/7/debt", requested_paths[0])
        self.assertIn("/counterparties/7/account-card?date_from=2026-01-01", requested_paths[1])
        self.assertIn("contract_id=3", requested_paths[1])
        self.assertIn("/counterparties/7/reconciliation?date_to=2026-12-31", requested_paths[2])
        self.assertIn("/contracts?counterparty_id=7&active_only=true", requested_paths[3])
        self.assertIn("/contracts", requested_paths[4])
        self.assertIn("/contracts/3", requested_paths[5])
        self.assertIn("/debt-ledger?counterparty_id=7&debt_type=receivable&contract_id=3", requested_paths[6])

    def test_api_client_sales_cashier_report_helpers_use_envelopes(self) -> None:
        """Sales, cashier, and report helpers should return envelope data."""

        client = ApiClient("server:8000")
        client.session_token = "token"
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "data": [{"id": 3, "status": "open"}],
            "error": None,
            "meta": None,
        }
        client.session.request = Mock(return_value=response)  # type: ignore[method-assign]

        shifts = client.get_cash_shifts("open")

        self.assertEqual(shifts[0]["status"], "open")
        called_url = client.session.request.call_args.args[1]
        self.assertIn("/cash-shifts?status=open", called_url)

        response.json.return_value = {
            "success": True,
            "data": {"id": 9, "doc_number": "SAL-000001"},
            "error": None,
            "meta": None,
        }
        sale = client.create_sale({"warehouse_id": 1, "currency_id": 1, "lines": []})
        client.post_sale(sale["id"])
        client.cancel_sale(sale["id"])
        sale_return = client.create_sale_return({"sale_id": sale["id"], "lines": []})
        client.post_sale_return(sale_return["id"])
        client.cancel_sale_return(sale_return["id"])
        client.create_cash_register({"name": "Register", "warehouse_id": 1})
        client.open_cash_shift({"cash_register_id": 1, "opening_amount": "0"})
        client.close_cash_shift(3, {"closing_amount": "0"})
        client.get_cash_shift_x_report(3)
        client.create_cash_shift_z_report(3, {"closing_amount": "0"})
        client.create_cash_operation({"cash_shift_id": 3, "cash_register_from_id": 1, "operation_type": "collection", "amount_tmt": "1.00"})

        response.json.return_value = {
            "success": True,
            "data": {"sales_total_tmt": "30.00"},
            "error": None,
            "meta": None,
        }
        report = client.get_sales_report()

        self.assertEqual(report["sales_total_tmt"], "30.00")
        requested_paths = [call.args[1] for call in client.session.request.call_args_list[-13:]]
        self.assertIn("/sales", requested_paths[0])
        self.assertIn("/sales/9/post", requested_paths[1])
        self.assertIn("/sales/9/cancel", requested_paths[2])
        self.assertIn("/sale-returns", requested_paths[3])
        self.assertIn("/sale-returns/9/post", requested_paths[4])
        self.assertIn("/sale-returns/9/cancel", requested_paths[5])
        self.assertIn("/cash-registers", requested_paths[6])
        self.assertIn("/cash-shifts/open", requested_paths[7])
        self.assertIn("/cash-shifts/3/close", requested_paths[8])
        self.assertIn("/cash-shifts/3/x-report", requested_paths[9])
        self.assertIn("/cash-shifts/3/z-report", requested_paths[10])
        self.assertIn("/cash-operations", requested_paths[11])
        self.assertIn("/reports/sales", requested_paths[12])

    def test_api_client_stage6_report_helpers_build_filter_and_export_paths(self) -> None:
        """Filtered reports, exports, and saved filter helpers should target API v1 paths."""

        client = ApiClient("server:8000")
        client.session_token = "token"
        response = Mock()
        response.ok = True
        response.status_code = 200

        def set_data(data: object) -> None:
            response.json.return_value = {"success": True, "data": data, "error": None, "meta": None}

        client.session.request = Mock(return_value=response)  # type: ignore[method-assign]

        set_data({"sales_total_tmt": "30.00"})
        client.get_sales_report({"warehouse_id": 2, "date_from": "2026-01-01"})
        client.get_purchases_report({"counterparty_id": 3})
        client.get_debts_report({"debt_type": "receivable"})
        client.get_cash_flow_report({"cash_shift_id": 5})
        client.get_profit_loss_report({"product_id": 4})

        set_data([{"product_id": 4}])
        client.get_stock_report({"product_id": 4})
        client.get_report_filters("sales")

        set_data({"report_code": "sales", "xlsx_base64": "UEs="})
        client.export_report("sales", {"warehouse_id": 2})
        client.create_report_filter({"report_code": "sales", "name": "By warehouse", "filters": {}})
        client.update_report_filter(8, {"name": "Updated"})
        client.delete_report_filter(8)

        requested_paths = [call.args[1] for call in client.session.request.call_args_list[-11:]]
        self.assertIn("/reports/sales?warehouse_id=2&date_from=2026-01-01", requested_paths[0])
        self.assertIn("/reports/purchases?counterparty_id=3", requested_paths[1])
        self.assertIn("/reports/debts?debt_type=receivable", requested_paths[2])
        self.assertIn("/reports/cash-flow?cash_shift_id=5", requested_paths[3])
        self.assertIn("/reports/profit-loss?product_id=4", requested_paths[4])
        self.assertIn("/reports/stock?product_id=4", requested_paths[5])
        self.assertIn("/report-filters?report_code=sales", requested_paths[6])
        self.assertIn("/reports/sales/export?warehouse_id=2", requested_paths[7])
        self.assertIn("/report-filters", requested_paths[8])
        self.assertIn("/report-filters/8", requested_paths[9])
        self.assertIn("/report-filters/8", requested_paths[10])

    def test_reference_selector_filters_and_selects_offscreen(self) -> None:
        """ReferenceSelectorDialog should filter rows and return the selected API row."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from user_app.ui.selectors import ReferenceSelectorDialog

        app = QApplication.instance() or QApplication([])
        dialog = ReferenceSelectorDialog(
            "Products",
            [
                {"id": 1, "sku": "A-1", "name": "Alpha"},
                {"id": 2, "sku": "B-2", "name": "Beta"},
            ],
            [("id", "ID"), ("sku", "SKU"), ("name", "Name")],
        )
        dialog.search.setText("beta")
        self.assertEqual(dialog.table.rowCount(), 1)
        dialog.table.selectRow(0)
        dialog._accept_current()

        self.assertEqual(dialog.selected_row()["id"], 2)
        dialog.close()
        app.processEvents()

    def test_main_window_disables_actions_by_permissions_offscreen(self) -> None:
        """Action buttons should be disabled when the role lacks create/post permissions."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication, QPushButton
        from user_app.ui.main_window import MainWindow

        class FakeApiClient:
            def __init__(self) -> None:
                self.current_user = SimpleNamespace(
                    full_name="Auditor",
                    role_name="Auditor",
                    permissions=["sale.view", "reports.view", "warehouse.view", "goods.view"],
                )

            def get_status(self) -> dict[str, str]:
                return {"status": "ok"}

        app = QApplication.instance() or QApplication([])
        window = MainWindow(FakeApiClient(), Translator("en"))  # type: ignore[arg-type]
        buttons = {str(button.property("textKey")): button for button in window.findChildren(QPushButton) if button.property("textKey")}

        self.assertFalse(buttons["sales.create_sale"].isEnabled())
        self.assertFalse(buttons["reports.export"].isEnabled())
        self.assertTrue(buttons["catalog.refresh"].isEnabled())
        window.close()
        app.processEvents()

    def test_users_page_renders_filters_and_empty_state_offscreen(self) -> None:
        """Users list should render KPIs, search, status, role filtering, and empty state."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from user_app.ui.main_window import MainWindow

        class FakeApiClient:
            def __init__(self) -> None:
                self.current_user = SimpleNamespace(full_name="Admin", role_name="Super Admin", permissions=["admin.manage_users"])
                self.users = [
                    {"id": 1, "username": "admin", "full_name": "Admin Person", "role_name": "Administrator", "is_active": True},
                    {"id": 2, "username": "cashier", "full_name": "Cashier Person", "role_name": "Cashier", "is_active": False},
                ]

            def get_status(self) -> dict[str, str]:
                return {"status": "ok"}

            def get_users(self) -> list[dict[str, object]]:
                return [dict(user) for user in self.users]

            def get_roles(self) -> list[dict[str, object]]:
                return [{"name": "Administrator"}, {"name": "Cashier"}]

        app = QApplication.instance() or QApplication([])
        window = MainWindow(FakeApiClient(), Translator("en"))  # type: ignore[arg-type]
        try:
            window.refresh_users()

            self.assertEqual(window.stat_total_val.text(), "2")
            self.assertEqual(window.stat_active_val.text(), "1")
            self.assertEqual(window.stat_inactive_val.text(), "1")
            self.assertEqual(window.users_table.rowCount(), 2)

            window.users_search.setText("cashier")
            self.assertEqual(window.users_table.rowCount(), 1)
            self.assertIn("cashier", window.users_table.item(0, 1).text())

            window.users_status_buttons["active"].click()
            self.assertEqual(window.users_table.rowCount(), 0)
            self.assertIs(window.users_table_stack.currentWidget(), window.users_empty_state)

            window.users_search.clear()
            window.users_status_buttons["all"].click()
            role_index = window.users_role_filter.findData("Administrator")
            window.users_role_filter.setCurrentIndex(role_index)
            self.assertEqual(window.users_table.rowCount(), 1)
            self.assertEqual(window.users_table.item(0, 1).text(), "admin")
        finally:
            window.close()
            app.processEvents()

    def test_users_page_switches_full_page_states_offscreen(self) -> None:
        """View, create, and edit wrappers should switch the Users internal stack."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from user_app.ui.main_window import MainWindow

        class FakeApiClient:
            def __init__(self) -> None:
                self.current_user = SimpleNamespace(full_name="Admin", role_name="Super Admin", permissions=["admin.manage_users"])

            def get_status(self) -> dict[str, str]:
                return {"status": "ok"}

            def get_users(self) -> list[dict[str, object]]:
                return []

            def get_roles(self) -> list[dict[str, object]]:
                return [{"name": "Administrator"}, {"name": "Cashier"}]

        app = QApplication.instance() or QApplication([])
        window = MainWindow(FakeApiClient(), Translator("en"))  # type: ignore[arg-type]
        row = {"id": 1, "username": "admin", "full_name": "Admin Person", "role_name": "Administrator", "is_active": True}
        try:
            window._show_user_details_dialog(row)
            self.assertIs(window.users_stack.currentWidget(), window.users_detail_page)

            window.edit_user_dialog(row)
            self.assertIs(window.users_stack.currentWidget(), window.users_edit_page)

            window.create_user_dialog()
            self.assertIs(window.users_stack.currentWidget(), window.users_create_page)
        finally:
            window.close()
            app.processEvents()

    def test_users_create_and_edit_validate_and_submit_payloads_offscreen(self) -> None:
        """Users forms should validate inline and submit existing API payload shapes."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from user_app.ui.main_window import MainWindow

        class FakeApiClient:
            def __init__(self) -> None:
                self.current_user = SimpleNamespace(full_name="Admin", role_name="Super Admin", permissions=["admin.manage_users"])
                self.users = [
                    {"id": 1, "username": "admin", "full_name": "Admin Person", "role_name": "Administrator", "is_active": True},
                ]
                self.created_payload: dict[str, object] | None = None
                self.updated_payload: dict[str, object] | None = None

            def get_status(self) -> dict[str, str]:
                return {"status": "ok"}

            def get_users(self) -> list[dict[str, object]]:
                return [dict(user) for user in self.users]

            def get_roles(self) -> list[dict[str, object]]:
                return [{"name": "Administrator"}, {"name": "Cashier"}]

            def create_user(self, payload: dict[str, object]) -> dict[str, object]:
                self.created_payload = dict(payload)
                created = {
                    "id": 2,
                    "username": payload["username"],
                    "full_name": payload["full_name"],
                    "role_name": payload["role_name"],
                    "is_active": payload["is_active"],
                }
                self.users.append(created)
                return dict(created)

            def update_user(self, user_id: int, payload: dict[str, object]) -> dict[str, object]:
                self.updated_payload = dict(payload)
                self.users[0].update(payload)
                return dict(self.users[0], id=user_id)

        app = QApplication.instance() or QApplication([])
        api_client = FakeApiClient()
        window = MainWindow(api_client, Translator("en"))  # type: ignore[arg-type]
        try:
            window.create_user_dialog()
            window.user_form_save_button.click()
            self.assertIsNone(api_client.created_payload)
            self.assertIn("Enter a username.", window.user_form_error_label.text())

            window.user_form_username.setText("cashier")
            window.user_form_full_name.setText("Cashier Person")
            window.user_form_password.setText("123")
            window.user_form_save_button.click()
            self.assertIsNone(api_client.created_payload)

            window.user_form_password.setText("secret1")
            window.user_form_role_combo.setCurrentIndex(window.user_form_role_combo.findData("Cashier"))
            window.user_form_active_check.setChecked(False)
            window.user_form_save_button.click()
            self.assertEqual(
                api_client.created_payload,
                {
                    "username": "cashier",
                    "full_name": "Cashier Person",
                    "password": "secret1",
                    "role_name": "Cashier",
                    "is_active": False,
                },
            )
            self.assertIs(window.users_stack.currentWidget(), window.users_detail_page)

            window.edit_user_dialog(api_client.users[0])
            window.user_form_full_name.setText("Admin Updated")
            window.user_form_password.setText("123")
            window.user_form_save_button.click()
            self.assertIsNone(api_client.updated_payload)

            window.user_form_password.setText("updated1")
            window.user_form_role_combo.setCurrentIndex(window.user_form_role_combo.findData("Cashier"))
            window.user_form_active_check.setChecked(False)
            window.user_form_save_button.click()
            self.assertEqual(
                api_client.updated_payload,
                {
                    "full_name": "Admin Updated",
                    "role_name": "Cashier",
                    "is_active": False,
                    "password": "updated1",
                },
            )
            self.assertIs(window.users_stack.currentWidget(), window.users_detail_page)
        finally:
            window.close()
            app.processEvents()

    def test_users_deactivate_uses_existing_api_action_offscreen(self) -> None:
        """Users deactivate action should call the existing API and refresh rows."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from user_app.ui.main_window import MainWindow

        class FakeApiClient:
            def __init__(self) -> None:
                self.current_user = SimpleNamespace(full_name="Admin", role_name="Super Admin", permissions=["admin.manage_users"])
                self.users = [
                    {"id": 1, "username": "admin", "full_name": "Admin Person", "role_name": "Administrator", "is_active": True},
                ]
                self.deactivated_user_id: int | None = None

            def get_status(self) -> dict[str, str]:
                return {"status": "ok"}

            def get_users(self) -> list[dict[str, object]]:
                return [dict(user) for user in self.users]

            def get_roles(self) -> list[dict[str, object]]:
                return [{"name": "Administrator"}]

            def update_user(self, user_id: int, payload: dict[str, object]) -> dict[str, object]:
                self.users[0].update(payload)
                return dict(self.users[0], id=user_id)

            def deactivate_user(self, user_id: int) -> dict[str, object]:
                self.deactivated_user_id = user_id
                self.users[0]["is_active"] = False
                return dict(self.users[0])

        app = QApplication.instance() or QApplication([])
        api_client = FakeApiClient()
        window = MainWindow(api_client, Translator("en"))  # type: ignore[arg-type]
        try:
            window.refresh_users()
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                window.deactivate_user_action(api_client.users[0])

            self.assertEqual(api_client.deactivated_user_id, 1)
            self.assertEqual(window.stat_inactive_val.text(), "1")
            self.assertEqual(window.users_table.item(0, 4).text(), "Inactive")
        finally:
            window.close()
            app.processEvents()

    def test_users_redesign_translation_keys_exist(self) -> None:
        """New Users UI labels should be translated in every supported language."""

        keys = [
            "users.subtitle",
            "users.search_placeholder",
            "users.stats.total",
            "users.stats.active",
            "users.stats.inactive",
            "users.filter.all",
            "users.filter.active",
            "users.filter.inactive",
            "users.filter.role_all",
            "users.status.active",
            "users.status.inactive",
            "users.details",
            "users.edit_title",
            "users.back_to_list",
            "users.save",
            "users.table.actions",
            "users.visible_count",
            "users.empty.title",
            "users.empty.body",
            "users.empty.no_users_title",
            "users.empty.no_users_body",
            "users.form.password_hint",
            "users.form.show_password",
            "users.form.hide_password",
            "users.validation.username_required",
            "users.validation.full_name_required",
            "users.validation.password_required",
            "users.validation.password_short",
        ]

        for language in ("ru", "tk", "en"):
            translator = Translator(language)  # type: ignore[arg-type]
            for key in keys:
                self.assertNotEqual(translator.text(key), key)

    def test_roles_redesign_paginates_filters_and_opens_drawer_offscreen(self) -> None:
        """Roles should paginate without a scrollbar and render selected permissions."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QPushButton
        from user_app.ui.main_window import MainWindow

        class FakeApiClient:
            def __init__(self) -> None:
                self.current_user = SimpleNamespace(
                    full_name="Admin",
                    role_name="Super Admin",
                    permissions=["admin.manage_users", "admin.manage_roles"],
                )
                self.fail_permission_metadata = False
                self.roles = [
                    {
                        "id": index,
                        "name": f"Role {index:02d}",
                        "description": (
                            "A long role description that should wrap cleanly "
                            "inside the responsive permissions summary."
                            if index == 1
                            else f"Description {index}"
                        ),
                        "permissions": [
                            "admin.view",
                            "reports.view",
                            *(["sale.create"] if index % 2 else []),
                        ],
                    }
                    for index in range(1, 18)
                ]

            def get_status(self) -> dict[str, str]:
                return {"status": "ok"}

            def get_roles(self) -> list[dict[str, object]]:
                return [dict(role) for role in self.roles]

            def get_permissions(self) -> list[dict[str, object]]:
                if self.fail_permission_metadata:
                    raise RuntimeError("metadata unavailable")
                return [
                    {
                        "id": 1,
                        "code": "admin.view",
                        "module": "admin",
                        "description": "View administration",
                    },
                    {
                        "id": 2,
                        "code": "reports.view",
                        "module": "reports",
                        "description": "View reports",
                    },
                    {
                        "id": 3,
                        "code": "sale.create",
                        "module": "sale",
                        "description": "Create sales",
                    },
                ]

        app = QApplication.instance() or QApplication([])
        api_client = FakeApiClient()
        window = MainWindow(api_client, Translator("en"))  # type: ignore[arg-type]
        try:
            window.resize(1440, 900)
            window.show()
            for index in range(window.nav.count()):
                if (
                    window.nav.item(index).data(Qt.ItemDataRole.UserRole)
                    == "roles"
                ):
                    window.nav.setCurrentRow(index)
                    break
            app.processEvents()

            self.assertEqual(window.roles_table.rowCount(), 10)
            self.assertEqual(
                window.roles_table.verticalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self.assertEqual(
                window.roles_permission_scroll.horizontalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self.assertEqual(window.roles_total_value.text(), "17")
            self.assertEqual(window.roles_available_permissions_value.text(), "3")

            window.roles_table.selectRow(0)
            QTest.qWait(220)
            app.processEvents()
            self.assertEqual(window.roles_drawer_title.text(), "Role 01")
            self.assertEqual(window.roles_drawer_avatar.text(), "R0")
            self.assertEqual(window.roles_drawer_count.text(), "3")
            self.assertTrue(window.roles_drawer_hero.isVisible())
            self.assertTrue(window.roles_drawer_description.wordWrap())
            self.assertIn(
                "should wrap cleanly",
                window.roles_drawer_description.text(),
            )
            self.assertEqual(
                window.roles_permission_results.text(),
                "Showing 3 of 3 permissions",
            )
            self.assertTrue(window.roles_permissions_drawer.isVisible())
            self.assertFalse(window.roles_narrow_mode)
            self.assertTrue(window.roles_permission_filters_horizontal)
            self.assertGreaterEqual(window.roles_permissions_drawer.width(), 500)
            self.assertLessEqual(window.roles_permissions_drawer.width(), 650)
            permission_cards = [
                frame
                for frame in window.roles_permission_cards_container.findChildren(QFrame)
                if frame.objectName() == "RolesPermissionCard"
            ]
            module_chips = [
                btn
                for btn in window.roles_permission_cards_container.findChildren(QPushButton)
                if btn.objectName() == "RolesModuleChip"
            ]
            self.assertEqual(len(module_chips), 3)
            self.assertGreaterEqual(len(permission_cards), 1)
            self.assertTrue(
                all(
                    card.focusPolicy() == Qt.FocusPolicy.StrongFocus
                    for card in permission_cards
                )
            )
            self.assertTrue(
                all(
                    card.findChild(QLabel, "RolesPermissionCheck") is not None
                    for card in permission_cards
                )
            )

            window.roles_table.selectRow(1)
            app.processEvents()
            self.assertEqual(window.roles_drawer_title.text(), "Role 02")
            self.assertEqual(window.roles_drawer_count.text(), "2")
            window.roles_table.selectRow(0)
            app.processEvents()

            window.roles_permission_search.setText("sales")
            app.processEvents()
            permission_cards = [
                frame
                for frame in window.roles_permission_cards_container.findChildren(QFrame)
                if frame.objectName() == "RolesPermissionCard"
            ]
            self.assertEqual(len(permission_cards), 1)
            self.assertEqual(
                window.roles_permission_results.text(),
                "Showing 1 of 3 permissions",
            )

            window.roles_permission_search.clear()
            app.processEvents()
            module_chips = [
                btn
                for btn in window.roles_permission_cards_container.findChildren(QPushButton)
                if btn.objectName() == "RolesModuleChip" and "reports" in btn.text().lower()
            ]
            self.assertTrue(len(module_chips) > 0)
            module_chips[0].click()
            app.processEvents()
            self.assertEqual(
                window.roles_permission_results.text(),
                "Showing 3 of 3 permissions",
            )
            permission_cards = [
                frame
                for frame in window.roles_permission_cards_container.findChildren(QFrame)
                if frame.objectName() == "RolesPermissionCard"
            ]
            self.assertEqual(len(permission_cards), 1)

            api_client.fail_permission_metadata = True
            window.refresh_roles()
            app.processEvents()
            self.assertEqual(window.roles_selected_role_id, 1)
            self.assertEqual(window.roles_available_permissions_value.text(), "3")

            window.roles_search.setText("Role 17")
            app.processEvents()
            self.assertEqual(len(window.roles_filtered_rows), 1)
            self.assertIsNone(window.roles_selected_role_id)

            window.roles_search.clear()
            window.roles_page_size_combo.setCurrentIndex(0)
            window._go_to_roles_page(2)
            app.processEvents()
            self.assertEqual(window.roles_table.item(0, 0).text(), "11")
            self.assertEqual(window.roles_table.item(0, 1).text(), "Role 11")

            window.resize(1100, 800)
            app.processEvents()
            window.roles_table.selectRow(0)
            app.processEvents()
            self.assertTrue(window.roles_narrow_mode)
            self.assertTrue(window.roles_permission_filters_horizontal)
            self.assertIs(
                window.roles_content_stack.currentWidget(),
                window.roles_narrow_detail_page,
            )
            window.roles_drawer_back.click()
            self.assertIs(
                window.roles_content_stack.currentWidget(),
                window.roles_desktop_page,
            )

            window.resize(980, 720)
            app.processEvents()
            window.roles_table.selectRow(1)
            app.processEvents()
            window.roles_permissions_drawer.setMaximumWidth(520)
            window.roles_permissions_drawer.resize(520, 680)
            app.processEvents()
            window._update_roles_drawer_compact_layout()
            self.assertTrue(window.roles_narrow_mode)
            self.assertTrue(window.roles_drawer_compact)
            self.assertFalse(window.roles_permission_filters_horizontal)
            self.assertTrue(window.roles_drawer_hero.isVisible())
            self.assertIs(
                window.roles_content_stack.currentWidget(),
                window.roles_narrow_detail_page,
            )
        finally:
            window.close()
            app.processEvents()

    def test_roles_redesign_translation_keys_exist(self) -> None:
        """Every new Roles surface label should exist in all three languages."""

        keys = [
            "roles.refresh",
            "roles.subtitle",
            "roles.search_placeholder",
            "roles.stats.total",
            "roles.stats.available_permissions",
            "roles.stats.selected_granted",
            "roles.visible_count",
            "roles.pagination.per_page",
            "roles.pagination.showing",
            "roles.empty.filtered_title",
            "roles.empty.filtered_body",
            "roles.empty.no_roles_title",
            "roles.empty.no_roles_body",
            "roles.back_to_roles",
            "roles.close_permissions",
            "roles.drawer.title",
            "roles.drawer.assigned",
            "roles.drawer.no_description",
            "roles.permissions.search_label",
            "roles.permissions.module_label",
            "roles.permissions.search_placeholder",
            "roles.permissions.all_modules",
            "roles.permissions.results",
            "roles.permissions.granted",
            "roles.permissions.granted_count",
            "roles.permissions.modules.admin",
            "roles.permissions.modules.audit",
            "roles.permissions.modules.cashier",
            "roles.permissions.modules.counterparty",
            "roles.permissions.modules.goods",
            "roles.permissions.modules.pricing",
            "roles.permissions.modules.purchase",
            "roles.permissions.modules.reports",
            "roles.permissions.modules.sale",
            "roles.permissions.modules.sale_return",
            "roles.permissions.modules.settings",
            "roles.permissions.modules.warehouse",
            "roles.permissions.no_assigned_title",
            "roles.permissions.no_assigned_body",
            "roles.permissions.no_matches_title",
            "roles.permissions.no_matches_body",
            "roles.permissions.empty_title",
            "roles.permissions.empty_body",
        ]
        for language in ("ru", "tk", "en"):
            translator = Translator(language)  # type: ignore[arg-type]
            for key in keys:
                self.assertNotEqual(translator.text(key), key)

    def test_roles_drawer_empty_states_and_live_translation_offscreen(self) -> None:
        """Drawer should distinguish empty causes and retranslate while open."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
        from user_app.ui.main_window import MainWindow

        class FakeApiClient:
            def __init__(self) -> None:
                self.current_user = SimpleNamespace(
                    full_name="Admin",
                    role_name="Super Admin",
                    permissions=["admin.manage_roles"],
                )
                self.roles = [
                    {
                        "id": 1,
                        "name": "Audit Review",
                        "description": "",
                        "permissions": [],
                    }
                ]

            def get_status(self) -> dict[str, str]:
                return {"status": "ok"}

            def get_roles(self) -> list[dict[str, object]]:
                return [dict(role) for role in self.roles]

            def get_permissions(self) -> list[dict[str, object]]:
                return [
                    {
                        "id": 1,
                        "code": "reports.view",
                        "module": "reports",
                        "description": "View reports",
                    }
                ]

        app = QApplication.instance() or QApplication([])
        translator = Translator("en")
        window = MainWindow(FakeApiClient(), translator)  # type: ignore[arg-type]
        try:
            window.resize(1440, 900)
            window.show()
            for index in range(window.nav.count()):
                if (
                    window.nav.item(index).data(Qt.ItemDataRole.UserRole)
                    == "roles"
                ):
                    window.nav.setCurrentRow(index)
                    break
            app.processEvents()
            window.roles_table.selectRow(0)
            app.processEvents()

            empty_texts = {
                label.text()
                for label in window.roles_permission_cards_container.findChildren(
                    QLabel
                )
            }
            self.assertIn("No permissions assigned yet", empty_texts)
            self.assertEqual(
                window.roles_permission_results.text(),
                "Showing 0 of 0 permissions",
            )
            self.assertEqual(
                window.roles_drawer_description.text(),
                "No description provided",
            )

            selected_role = window._selected_role()
            self.assertIsNotNone(selected_role)
            selected_role["permissions"] = ["reports.view"]  # type: ignore[index]
            window._render_role_permissions_header(selected_role)  # type: ignore[arg-type]
            window._populate_role_permission_module_filter(["reports.view"])
            window.roles_permission_search.setText("missing")
            app.processEvents()
            empty_texts = {
                label.text()
                for label in window.roles_permission_cards_container.findChildren(
                    QLabel
                )
            }
            self.assertIn("No matching permissions", empty_texts)
            self.assertEqual(
                window.roles_permission_results.text(),
                "Showing 0 of 1 permissions",
            )

            translator.set_language("ru")
            window.retranslate()
            app.processEvents()
            self.assertEqual(window.roles_drawer_eyebrow.text(), "Права роли")
            self.assertEqual(
                window.roles_permission_results.text(),
                "Показано 0 из 1 прав",
            )
            self.assertEqual(
                window.roles_drawer_description.text(),
                "Описание отсутствует",
            )
            window.roles_permission_search.clear()
            app.processEvents()
            module_chips = [
                button
                for button in window.roles_permission_cards_container.findChildren(
                    QPushButton
                )
                if button.objectName() == "RolesModuleChip"
            ]
            self.assertEqual(len(module_chips), 1)
            self.assertIn("Отчёты", module_chips[0].text())
            self.assertEqual(
                window.roles_drawer_count.toolTip(),
                "Назначено: 1",
            )
        finally:
            window.close()
            app.processEvents()

    def test_settings_page_uses_editable_form_offscreen(self) -> None:
        """Settings should render as editable fields and save key/value payloads."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from user_app.ui.main_window import MainWindow

        class FakeApiClient:
            def __init__(self) -> None:
                self.current_user = SimpleNamespace(full_name="Admin", role_name="Super Admin", permissions=["settings.view", "settings.edit"])
                self.saved_values: dict[str, object] | None = None

            def get_status(self) -> dict[str, str]:
                return {"status": "ok"}

            def get_settings(self) -> dict[str, object]:
                return {
                    "organization": {"name_ru": "Old Org", "base_currency": "TMT", "second_currency": None},
                    "feature_enabled": True,
                }

            def update_settings(self, values: dict[str, object]) -> dict[str, object]:
                self.saved_values = values
                return values

        app = QApplication.instance() or QApplication([])
        api_client = FakeApiClient()
        window = MainWindow(api_client, Translator("en"))  # type: ignore[arg-type]
        try:
            window.refresh_settings()
            self.assertFalse(window.settings_text.isVisible())
            window.settings_fields[("organization", "name_ru")].setText("Modern Org")
            window.settings_fields[("feature_enabled",)].setText("false")
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                window.save_settings()

            self.assertEqual(api_client.saved_values["organization"]["name_ru"], "Modern Org")  # type: ignore[index]
            self.assertFalse(api_client.saved_values["feature_enabled"])  # type: ignore[index]
        finally:
            window.close()
            app.processEvents()

    def test_reports_page_filters_export_and_save_offscreen(self) -> None:
        """The PyQt reports page should pass filters to report, export, and save helpers."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from user_app.ui.main_window import MainWindow

        class FakeApiClient:
            def __init__(self) -> None:
                self.current_user = SimpleNamespace(full_name="Reporter", role_name="Manager", permissions=["reports.view", "reports.export", "reports.filters_manage"])
                self.report_filters: dict[str, str] | None = None
                self.export_filters: dict[str, str] | None = None
                self.saved_filter: dict[str, object] | None = None

            def get_status(self) -> dict[str, str]:
                return {"status": "ok"}

            def get_report_filters(self, report_code: str | None = None) -> list[dict[str, object]]:
                return [{"id": 1, "report_code": report_code, "name": "Saved"}]

            def get_sales_report(self, filters: dict[str, str] | None = None) -> dict[str, object]:
                self.report_filters = filters
                return {"sales_total_tmt": "30.00", "rows": []}

            def export_report(self, report_code: str, filters: dict[str, str] | None = None) -> dict[str, object]:
                self.export_filters = filters
                return {"report_code": report_code, "filename": "sales.xlsx", "xlsx_base64": "UEs="}

            def create_report_filter(self, payload: dict[str, object]) -> dict[str, object]:
                self.saved_filter = payload
                return {"id": 2, **payload}

        app = QApplication.instance() or QApplication([])
        api_client = FakeApiClient()
        window = MainWindow(api_client, Translator("en"))  # type: ignore[arg-type]
        window.report_code.setCurrentIndex(window.report_code.findData("sales"))
        window.report_warehouse_id.setText("2")
        window.report_product_id.setText("4")
        window.report_filter_name.setText("Warehouse product")

        window.refresh_reports()
        window.export_current_report()
        self.assertIn("sales.xlsx", window.reports_text.toPlainText())
        window.save_current_report_filter()

        self.assertEqual(api_client.report_filters, {"warehouse_id": "2", "product_id": "4"})
        self.assertEqual(api_client.export_filters, {"warehouse_id": "2", "product_id": "4"})
        self.assertEqual(api_client.saved_filter["report_code"], "sales")
        self.assertEqual(api_client.saved_filter["filters"], {"warehouse_id": "2", "product_id": "4"})
        window.close()
        app.processEvents()

    def test_api_client_pricing_promotion_loyalty_helpers_use_envelopes(self) -> None:
        """Stage 3 pricing, promotion, and loyalty helpers should target API v1 paths."""

        client = ApiClient("server:8000")
        client.session_token = "token"
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "data": {"id": 4, "xlsx_base64": "UEs="},
            "error": None,
            "meta": None,
        }
        client.session.request = Mock(return_value=response)  # type: ignore[method-assign]

        client.export_price_list(4)
        client.import_price_list(4, {"rows": []})

        response.json.return_value = {
            "success": True,
            "data": [{"id": 6, "name": "Promo"}],
            "error": None,
            "meta": None,
        }
        client.get_promotions(active_only=True)

        response.json.return_value = {
            "success": True,
            "data": {"id": 6},
            "error": None,
            "meta": None,
        }
        client.create_promotion({"name": "Promo"})
        client.update_promotion(6, {"is_active": False})
        client.get_loyalty_settings()
        client.update_loyalty_settings({"earn_rate_percent": "1", "redemption_limit_percent": "50", "is_active": True})

        response.json.return_value = {
            "success": True,
            "data": [{"id": 8, "card_number": "LC-1"}],
            "error": None,
            "meta": None,
        }
        client.get_loyalty_cards("LC", active_only=True)

        response.json.return_value = {
            "success": True,
            "data": {"id": 8, "card_number": "LC-1"},
            "error": None,
            "meta": None,
        }
        client.create_loyalty_card({"card_number": "LC-1"})
        client.update_loyalty_card(8, {"owner_name": "Customer"})
        client.adjust_loyalty_card(8, {"amount_tmt": "1.00"})

        response.json.return_value = {
            "success": True,
            "data": [{"id": 9, "transaction_type": "manual_adjustment"}],
            "error": None,
            "meta": None,
        }
        transactions = client.get_loyalty_transactions(8)

        self.assertEqual(transactions[0]["transaction_type"], "manual_adjustment")
        requested_paths = [call.args[1] for call in client.session.request.call_args_list[-13:]]
        self.assertIn("/price-lists/4/export", requested_paths[0])
        self.assertIn("/price-lists/4/import", requested_paths[1])
        self.assertIn("/promotions?active_only=true", requested_paths[2])
        self.assertIn("/promotions", requested_paths[3])
        self.assertIn("/promotions/6", requested_paths[4])
        self.assertIn("/loyalty-settings", requested_paths[5])
        self.assertIn("/loyalty-settings", requested_paths[6])
        self.assertIn("/loyalty-cards?search=LC&active_only=true", requested_paths[7])
        self.assertIn("/loyalty-cards", requested_paths[8])
        self.assertIn("/loyalty-cards/8", requested_paths[9])
        self.assertIn("/loyalty-cards/8/adjust", requested_paths[10])
        self.assertIn("/loyalty-cards/8/transactions", requested_paths[11])

    def test_cashier_cart_posts_sale_and_previews_receipt_offscreen(self) -> None:
        """The PyQt cashier cart should build a sale payload and receipt preview."""

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from user_app.ui.main_window import MainWindow

        class FakeApiClient:
            def __init__(self) -> None:
                self.current_user = SimpleNamespace(
                    full_name="Cashier",
                    role_name="Cashier",
                    permissions=[
                        "cashier.view",
                        "sale.view",
                        "warehouse.view",
                        "reports.view",
                    ],
                )
                self.created_sale_payload: dict[str, object] | None = None

            def get_status(self) -> dict[str, str]:
                return {"status": "ok"}

            def get_currencies(self) -> list[dict[str, object]]:
                return [{"id": 1, "code": "TMT"}]

            def create_sale(self, payload: dict[str, object]) -> dict[str, object]:
                self.created_sale_payload = payload
                return {"id": 9}

            def post_sale(self, sale_id: int) -> dict[str, object]:
                return {
                    "id": sale_id,
                    "doc_number": "SAL-TEST",
                    "total_amount_tmt": "18.00",
                    "payment_type": "cash",
                    "lines": [
                        {
                            "product_name": "Sugar",
                            "quantity": "2.0000",
                            "amount_tmt": "18.00",
                        }
                    ],
                }

            def get_sales(self, status: str | None = None) -> list[dict[str, object]]:
                return []

            def get_debt_ledger(self, **_: object) -> list[dict[str, object]]:
                return []

            def get_cash_shifts(self, status: str | None = None) -> list[dict[str, object]]:
                return []

            def get_cash_flow_report(self) -> dict[str, str]:
                return {"net_cash_flow_tmt": "0.00"}

            def get_stock_balances(self, **_: object) -> list[dict[str, object]]:
                return []

            def get_stock_movements(self, **_: object) -> list[dict[str, object]]:
                return []

        app = QApplication.instance() or QApplication([])
        window = MainWindow(FakeApiClient(), Translator("en"))
        try:
            window.cashier_product_id_input.setText("5")
            window.cashier_product_name_input.setText("Sugar")
            window.cashier_quantity_input.setText("2")
            window.cashier_price_input.setText("10")
            window.cashier_discount_input.setText("10")
            window.cashier_add_item_from_inputs()
            window.cashier_register_id_input.setText("1")
            window.cashier_shift_id_input.setText("3")
            window.cashier_warehouse_id_input.setText("2")
            window.cashier_currency_id_input.setText("1")
            window.cashier_payment_type_combo.setCurrentText("cash")

            window.cashier_checkout()

            fake = window.api_client
            self.assertEqual(fake.created_sale_payload["warehouse_id"], 2)
            self.assertEqual(fake.created_sale_payload["lines"][0]["product_id"], 5)
            self.assertIn("SAL-TEST", window.cashier_receipt_preview.toPlainText())
            self.assertEqual(window.hardware.drawer_open_count, 1)
            self.assertEqual(window.hardware.fiscal_operations[-1], Decimal("18.00"))
        finally:
            window.close()
            app.processEvents()

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
        self.assertIsInstance(hardware, BarcodeScanner)
        self.assertIsInstance(hardware, ReceiptPrinter)
        self.assertIsInstance(hardware, CashDrawer)
        self.assertIsInstance(hardware, ScaleDevice)
        self.assertIsInstance(hardware, FiscalDevice)


if __name__ == "__main__":
    unittest.main()

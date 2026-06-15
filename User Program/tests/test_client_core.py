"""Tests for endpoint-client core helpers."""

from __future__ import annotations

from decimal import Decimal
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

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
        window.report_code.setCurrentText("sales")
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

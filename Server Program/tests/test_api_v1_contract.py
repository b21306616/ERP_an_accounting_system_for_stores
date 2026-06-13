"""Smoke tests for the strict /api/v1 client contract."""

from __future__ import annotations

import socket
import threading
import time
import unittest

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import uvicorn

from server_app.api.app import create_app
from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig
from server_app.core.constants import SUPER_ADMIN_FULL_NAME, SUPER_ADMIN_ROLE, SUPER_ADMIN_USERNAME
from server_app.core.security import hash_password
from server_app.db.base import Base
from server_app.db.bootstrap import seed_foundation_data
from server_app.db.models import User


class ApiV1ContractTests(unittest.TestCase):
    """Validate the documented envelope/session-token contract."""

    def setUp(self) -> None:
        """Create a fresh in-memory API server."""

        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        with self.session_factory() as session:
            roles = seed_foundation_data(session)
            session.add(
                User(
                    username=SUPER_ADMIN_USERNAME,
                    full_name=SUPER_ADMIN_FULL_NAME,
                    password_hash=hash_password("password123"),
                    role=roles[SUPER_ADMIN_ROLE],
                    is_active=True,
                )
            )
            session.commit()

        self.port = self._find_free_port()
        config = AppConfig(
            database=DatabaseConfig(server="test", database="test"),
            api=ApiConfig(host="127.0.0.1", port=self.port),
            jwt_secret="test-secret",
        )
        app = create_app(config, self.session_factory)
        uvicorn_config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="critical")
        self.server = uvicorn.Server(uvicorn_config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.port}/api/v1"
        self._wait_for_server()

    def tearDown(self) -> None:
        """Stop server and dispose DB."""

        self.server.should_exit = True
        self.thread.join(timeout=5)
        self.engine.dispose()

    @staticmethod
    def _find_free_port() -> int:
        """Ask Windows for a free local TCP port."""

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def _wait_for_server(self) -> None:
        """Wait until uvicorn answers health checks."""

        deadline = time.time() + 5
        last_error: Exception | None = None
        health_url = self.base_url.replace("/api/v1", "/health")
        while time.time() < deadline:
            try:
                response = requests.get(health_url, timeout=0.5)
                if response.status_code == 200:
                    return
            except Exception as exc:
                last_error = exc
            time.sleep(0.05)
        raise RuntimeError(f"API test server did not start: {last_error}")

    def _login(self) -> str:
        """Return a session token."""

        response = requests.post(
            f"{self.base_url}/auth/login",
            json={"username": SUPER_ADMIN_USERNAME, "password": "password123"},
            timeout=2,
        )
        self.assertEqual(response.status_code, 200)
        envelope = response.json()
        self.assertTrue(envelope["success"])
        self.assertIsNone(envelope["error"])
        self.assertIn("session_token", envelope["data"])
        self.assertIn("permissions", envelope["data"]["user"])
        return str(envelope["data"]["session_token"])

    def test_login_me_and_logout_use_envelope_and_session_header(self) -> None:
        """Login should issue an X-Session-Token-compatible token."""

        token = self._login()
        response = requests.get(f"{self.base_url}/auth/me", headers={"X-Session-Token": token}, timeout=2)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(response.json()["data"]["username"], SUPER_ADMIN_USERNAME)

        logout = requests.post(f"{self.base_url}/auth/logout", headers={"X-Session-Token": token}, timeout=2)
        self.assertEqual(logout.status_code, 200)
        self.assertTrue(logout.json()["success"])

        denied = requests.get(f"{self.base_url}/auth/me", headers={"X-Session-Token": token}, timeout=2)
        self.assertEqual(denied.status_code, 401)
        self.assertFalse(denied.json()["success"])

    def test_admin_foundation_endpoints_return_envelopes(self) -> None:
        """Foundation admin endpoints should use the v1 envelope."""

        token = self._login()
        headers = {"X-Session-Token": token}

        roles = requests.get(f"{self.base_url}/roles", headers=headers, timeout=2)
        self.assertEqual(roles.status_code, 200)
        self.assertTrue(roles.json()["success"])
        self.assertTrue(any(role["name"] == SUPER_ADMIN_ROLE for role in roles.json()["data"]))

        created = requests.post(
            f"{self.base_url}/users",
            json={
                "username": "cashier1",
                "full_name": "Cashier One",
                "password": "password123",
                "role_name": "Cashier",
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["success"])
        self.assertEqual(created.json()["data"]["username"], "cashier1")

    def test_catalog_endpoints_create_products_services_and_barcodes(self) -> None:
        """Catalog endpoints should create and find products/services."""

        token = self._login()
        headers = {"X-Session-Token": token}

        uoms = requests.get(f"{self.base_url}/unit-of-measures", headers=headers, timeout=2)
        self.assertEqual(uoms.status_code, 200)
        self.assertTrue(any(row["code"] == "pcs" for row in uoms.json()["data"]))

        group = requests.post(
            f"{self.base_url}/product-groups",
            json={"code": "G-FOOD", "name_ru": "Food", "name_tk": "Iymit"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(group.status_code, 201)
        group_id = group.json()["data"]["id"]

        product = requests.post(
            f"{self.base_url}/products",
            json={
                "sku": "P-001",
                "name": "Sugar",
                "name_tk": "Seker",
                "group_id": group_id,
                "retail_price": "12.50",
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(product.status_code, 201)
        product_id = product.json()["data"]["id"]

        barcode = requests.post(
            f"{self.base_url}/products/{product_id}/barcodes",
            json={"barcode": "4600000000017"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(barcode.status_code, 201)

        found = requests.get(
            f"{self.base_url}/products/by-barcode/4600000000017",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()["data"]["sku"], "P-001")

        category = requests.post(
            f"{self.base_url}/expense-categories",
            json={"code": "EXP-OPS", "name_ru": "Operations"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(category.status_code, 201)

        service = requests.post(
            f"{self.base_url}/services",
            json={"code": "S-DELIVERY", "name_ru": "Delivery", "default_price": "5.00"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(service.status_code, 201)

    def test_warehouse_endpoints_post_inventory_transfer_and_writeoff(self) -> None:
        """Warehouse endpoints should maintain balances through posted documents."""

        token = self._login()
        headers = {"X-Session-Token": token}

        source = requests.post(
            f"{self.base_url}/warehouses",
            json={"code": "WH-SRC", "name": "Source warehouse"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(source.status_code, 201)
        source_id = source.json()["data"]["id"]

        target = requests.post(
            f"{self.base_url}/warehouses",
            json={"code": "WH-DST", "name": "Target warehouse"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(target.status_code, 201)
        target_id = target.json()["data"]["id"]

        product = requests.post(
            f"{self.base_url}/products",
            json={"sku": "P-WH-001", "name": "Warehouse Item"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(product.status_code, 201)
        product_id = product.json()["data"]["id"]

        inventory = requests.post(
            f"{self.base_url}/inventories",
            json={
                "warehouse_id": source_id,
                "lines": [{"product_id": product_id, "qty_actual": "10.000", "unit_cost_tmt": "2.50"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(inventory.status_code, 201)
        inventory_id = inventory.json()["data"]["id"]

        posted_inventory = requests.post(
            f"{self.base_url}/inventories/{inventory_id}/post",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(posted_inventory.status_code, 200)
        self.assertEqual(posted_inventory.json()["data"]["status"], "posted")

        balances = requests.get(
            f"{self.base_url}/stock/balances",
            params={"warehouse_id": source_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(balances.status_code, 200)
        self.assertEqual(balances.json()["data"][0]["quantity"], "10.000")
        self.assertEqual(balances.json()["data"][0]["avg_cost_tmt"], "2.50")

        transfer = requests.post(
            f"{self.base_url}/stock-transfers",
            json={
                "source_warehouse_id": source_id,
                "target_warehouse_id": target_id,
                "lines": [{"product_id": product_id, "quantity": "4.000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(transfer.status_code, 201)
        transfer_id = transfer.json()["data"]["id"]

        sent = requests.post(f"{self.base_url}/stock-transfers/{transfer_id}/send", headers=headers, timeout=2)
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(sent.json()["data"]["status"], "in_transit")

        received = requests.post(f"{self.base_url}/stock-transfers/{transfer_id}/receive", headers=headers, timeout=2)
        self.assertEqual(received.status_code, 200)
        self.assertEqual(received.json()["data"]["status"], "received")

        source_balance = requests.get(
            f"{self.base_url}/stock/balances",
            params={"warehouse_id": source_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        target_balance = requests.get(
            f"{self.base_url}/stock/balances",
            params={"warehouse_id": target_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(source_balance.json()["data"][0]["quantity"], "6.000")
        self.assertEqual(target_balance.json()["data"][0]["quantity"], "4.000")

        writeoff = requests.post(
            f"{self.base_url}/stock-writeoffs",
            json={
                "warehouse_id": target_id,
                "reason_code": "damage",
                "lines": [{"product_id": product_id, "quantity": "2.000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(writeoff.status_code, 201)
        posted_writeoff = requests.post(
            f"{self.base_url}/stock-writeoffs/{writeoff.json()['data']['id']}/post",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(posted_writeoff.status_code, 200)
        self.assertEqual(posted_writeoff.json()["data"]["status"], "posted")

        failing_writeoff = requests.post(
            f"{self.base_url}/stock-writeoffs",
            json={
                "warehouse_id": target_id,
                "reason_code": "damage",
                "lines": [{"product_id": product_id, "quantity": "99.000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(failing_writeoff.status_code, 201)
        rejected = requests.post(
            f"{self.base_url}/stock-writeoffs/{failing_writeoff.json()['data']['id']}/post",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.json()["error"]["code"], "INSUFFICIENT_STOCK")

    def test_business_endpoints_price_purchase_and_payable_debt(self) -> None:
        """Pricing, purchase posting, and payable debt should work together."""

        token = self._login()
        headers = {"X-Session-Token": token}

        currencies = requests.get(f"{self.base_url}/currencies", headers=headers, timeout=2)
        self.assertEqual(currencies.status_code, 200)
        tmt = next(row for row in currencies.json()["data"] if row["code"] == "TMT")
        currency_id = tmt["id"]

        warehouse = requests.post(
            f"{self.base_url}/warehouses",
            json={"code": "WH-PUR", "name": "Purchase warehouse"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(warehouse.status_code, 201)
        warehouse_id = warehouse.json()["data"]["id"]

        product = requests.post(
            f"{self.base_url}/products",
            json={"sku": "P-BIZ-001", "name": "Purchased Item"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(product.status_code, 201)
        product_id = product.json()["data"]["id"]

        supplier = requests.post(
            f"{self.base_url}/counterparties",
            json={"code": "SUP-001", "name": "Supplier One", "role_flags": 1, "counterparty_type": "supplier"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(supplier.status_code, 201)
        supplier_id = supplier.json()["data"]["id"]

        price_list = requests.post(
            f"{self.base_url}/price-lists",
            json={"name_ru": "Retail", "currency_id": currency_id, "is_default": True},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(price_list.status_code, 201)
        price_list_id = price_list.json()["data"]["id"]

        price_item = requests.post(
            f"{self.base_url}/price-lists/{price_list_id}/items",
            json={"product_id": product_id, "price_tmt": "7.5000", "valid_from": "2026-01-01"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(price_item.status_code, 201)

        current_price = requests.get(
            f"{self.base_url}/prices/current",
            params={"product_id": product_id, "on_date": "2026-06-13"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(current_price.status_code, 200)
        self.assertEqual(current_price.json()["data"]["price_tmt"], "7.5000")

        invoice = requests.post(
            f"{self.base_url}/purchase-invoices",
            json={
                "counterparty_id": supplier_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "currency_rate": "1",
                "lines": [{"product_id": product_id, "quantity": "3.0000", "price_cur": "10.0000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(invoice.status_code, 201)
        invoice_id = invoice.json()["data"]["id"]
        self.assertEqual(invoice.json()["data"]["total_amount_tmt"], "30.00")

        posted = requests.post(f"{self.base_url}/purchase-invoices/{invoice_id}/post", headers=headers, timeout=2)
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["data"]["status"], "posted")

        balances = requests.get(
            f"{self.base_url}/stock/balances",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(balances.status_code, 200)
        self.assertEqual(balances.json()["data"][0]["quantity"], "3.000")
        self.assertEqual(balances.json()["data"][0]["avg_cost_tmt"], "10.00")

        debt = requests.get(
            f"{self.base_url}/counterparties/{supplier_id}/debt-summary",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(debt.status_code, 200)
        self.assertEqual(debt.json()["data"]["payable"], "30.00")

        payment = requests.post(
            f"{self.base_url}/payments",
            json={
                "counterparty_id": supplier_id,
                "direction": "outgoing",
                "payment_method": "cash",
                "amount_tmt": "10.00",
                "allocations": [
                    {"doc_type": "purchase_invoice", "doc_id": invoice_id, "allocated_amount": "10.00"}
                ],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(payment.status_code, 201)

        after_payment = requests.get(
            f"{self.base_url}/counterparties/{supplier_id}/debt-summary",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(after_payment.status_code, 200)
        self.assertEqual(after_payment.json()["data"]["payable"], "20.00")

        refreshed_invoice = requests.get(f"{self.base_url}/purchase-invoices/{invoice_id}", headers=headers, timeout=2)
        self.assertEqual(refreshed_invoice.status_code, 200)
        self.assertEqual(refreshed_invoice.json()["data"]["payment_status"], "partial")

    def test_sales_cashier_and_reports_workflow(self) -> None:
        """Sales posting should update stock, receivables, cashier shifts, and reports."""

        token = self._login()
        headers = {"X-Session-Token": token}

        currencies = requests.get(f"{self.base_url}/currencies", headers=headers, timeout=2)
        self.assertEqual(currencies.status_code, 200)
        currency_id = next(row for row in currencies.json()["data"] if row["code"] == "TMT")["id"]

        warehouse = requests.post(
            f"{self.base_url}/warehouses",
            json={"code": "WH-SALE", "name": "Sale warehouse"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(warehouse.status_code, 201)
        warehouse_id = warehouse.json()["data"]["id"]

        register = requests.post(
            f"{self.base_url}/cash-registers",
            json={"name": "Cash Register 1", "warehouse_id": warehouse_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(register.status_code, 201)
        register_id = register.json()["data"]["id"]

        shift = requests.post(
            f"{self.base_url}/cash-shifts/open",
            json={"cash_register_id": register_id, "opening_amount": "5.00"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(shift.status_code, 201)
        shift_id = shift.json()["data"]["id"]
        self.assertEqual(shift.json()["data"]["status"], "open")

        product = requests.post(
            f"{self.base_url}/products",
            json={"sku": "P-SALE-001", "name": "Sale Item"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(product.status_code, 201)
        product_id = product.json()["data"]["id"]

        supplier = requests.post(
            f"{self.base_url}/counterparties",
            json={"code": "SUP-SALE", "name": "Sale Supplier", "role_flags": 1, "counterparty_type": "supplier"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(supplier.status_code, 201)
        supplier_id = supplier.json()["data"]["id"]

        purchase = requests.post(
            f"{self.base_url}/purchase-invoices",
            json={
                "counterparty_id": supplier_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "currency_rate": "1",
                "lines": [{"product_id": product_id, "quantity": "5.0000", "price_cur": "10.0000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(purchase.status_code, 201)
        posted_purchase = requests.post(
            f"{self.base_url}/purchase-invoices/{purchase.json()['data']['id']}/post",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(posted_purchase.status_code, 200)

        customer = requests.post(
            f"{self.base_url}/counterparties",
            json={"code": "CUS-SALE", "name": "Sale Customer", "role_flags": 2, "counterparty_type": "customer"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(customer.status_code, 201)
        customer_id = customer.json()["data"]["id"]

        sale = requests.post(
            f"{self.base_url}/sales",
            json={
                "sale_type": "retail",
                "cash_register_id": register_id,
                "cash_shift_id": shift_id,
                "counterparty_id": customer_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "payment_type": "mixed",
                "paid_cash_tmt": "10.00",
                "debt_amount_tmt": "20.00",
                "lines": [{"product_id": product_id, "quantity": "2.0000", "price_final": "15.0000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(sale.status_code, 201)
        sale_id = sale.json()["data"]["id"]
        self.assertEqual(sale.json()["data"]["total_amount_tmt"], "30.00")

        posted_sale = requests.post(f"{self.base_url}/sales/{sale_id}/post", headers=headers, timeout=2)
        self.assertEqual(posted_sale.status_code, 200)
        self.assertEqual(posted_sale.json()["data"]["status"], "posted")
        self.assertEqual(posted_sale.json()["data"]["lines"][0]["avg_cost_tmt"], "10.0000")

        balances = requests.get(
            f"{self.base_url}/stock/balances",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(balances.status_code, 200)
        self.assertEqual(balances.json()["data"][0]["quantity"], "3.000")
        self.assertEqual(balances.json()["data"][0]["avg_cost_tmt"], "10.00")

        customer_debt = requests.get(
            f"{self.base_url}/counterparties/{customer_id}/debt-summary",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(customer_debt.status_code, 200)
        self.assertEqual(customer_debt.json()["data"]["receivable"], "20.00")

        customer_payment = requests.post(
            f"{self.base_url}/payments",
            json={
                "counterparty_id": customer_id,
                "direction": "incoming",
                "payment_method": "cash",
                "amount_tmt": "5.00",
                "cash_shift_id": shift_id,
                "allocations": [{"doc_type": "sale", "doc_id": sale_id, "allocated_amount": "5.00"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(customer_payment.status_code, 201)

        after_payment = requests.get(
            f"{self.base_url}/counterparties/{customer_id}/debt-summary",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(after_payment.status_code, 200)
        self.assertEqual(after_payment.json()["data"]["receivable"], "15.00")

        collection = requests.post(
            f"{self.base_url}/cash-operations",
            json={
                "cash_shift_id": shift_id,
                "cash_register_from_id": register_id,
                "operation_type": "collection",
                "amount_tmt": "3.00",
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(collection.status_code, 201)

        closed = requests.post(
            f"{self.base_url}/cash-shifts/{shift_id}/close",
            json={"closing_amount": "17.00"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["data"]["status"], "closed")

        sales_report = requests.get(f"{self.base_url}/reports/sales", headers=headers, timeout=2)
        self.assertEqual(sales_report.status_code, 200)
        self.assertEqual(sales_report.json()["data"]["sales_total_tmt"], "30.00")
        self.assertEqual(sales_report.json()["data"]["cash_tmt"], "10.00")
        self.assertEqual(sales_report.json()["data"]["debt_tmt"], "20.00")

        debts_report = requests.get(f"{self.base_url}/reports/debts", headers=headers, timeout=2)
        self.assertEqual(debts_report.status_code, 200)
        self.assertEqual(debts_report.json()["data"]["total_receivable_tmt"], "15.00")
        self.assertEqual(debts_report.json()["data"]["total_payable_tmt"], "50.00")

        cash_flow = requests.get(f"{self.base_url}/reports/cash-flow", headers=headers, timeout=2)
        self.assertEqual(cash_flow.status_code, 200)
        self.assertEqual(cash_flow.json()["data"]["sale_cash_tmt"], "10.00")
        self.assertEqual(cash_flow.json()["data"]["incoming_payments_tmt"], "5.00")
        self.assertEqual(cash_flow.json()["data"]["collections_tmt"], "3.00")
        self.assertEqual(cash_flow.json()["data"]["net_cash_flow_tmt"], "12.00")

        dashboard = requests.get(f"{self.base_url}/reports/dashboard", headers=headers, timeout=2)
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()["data"]["sales_total_tmt"], "30.00")
        self.assertEqual(dashboard.json()["data"]["purchase_total_tmt"], "50.00")
        self.assertEqual(dashboard.json()["data"]["receivable_tmt"], "15.00")
        self.assertEqual(dashboard.json()["data"]["open_shift_count"], 0)

        audit = requests.get(f"{self.base_url}/audit-log", headers=headers, timeout=2)
        self.assertEqual(audit.status_code, 200)
        audit_rows = audit.json()["data"]
        audit_pairs = {(row["module"], row["action"], row["entity_name"]) for row in audit_rows}
        self.assertIn(("cashier", "open", "cash-shifts"), audit_pairs)
        self.assertIn(("purchase", "post", "purchase-invoices"), audit_pairs)
        self.assertIn(("sale", "create", "sales"), audit_pairs)
        self.assertIn(("sale", "post", "sales"), audit_pairs)
        self.assertIn(("counterparty", "create", "payments"), audit_pairs)
        self.assertIn(("cashier", "close", "cash-shifts"), audit_pairs)
        self.assertTrue(all(row["user_id"] is not None for row in audit_rows))


if __name__ == "__main__":
    unittest.main()

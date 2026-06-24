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

    def test_counterparty_finance_contracts_allocations_reconciliation_and_credit_limits(self) -> None:
        """Contracts, payment allocations, account cards, and credit warnings should work together."""

        token = self._login()
        headers = {"X-Session-Token": token}

        currencies = requests.get(f"{self.base_url}/currencies", headers=headers, timeout=2)
        self.assertEqual(currencies.status_code, 200)
        currency_id = next(row for row in currencies.json()["data"] if row["code"] == "TMT")["id"]

        warehouse = requests.post(
            f"{self.base_url}/warehouses",
            json={"code": "WH-FIN", "name": "Finance warehouse"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(warehouse.status_code, 201)
        warehouse_id = warehouse.json()["data"]["id"]

        product = requests.post(
            f"{self.base_url}/products",
            json={"sku": "P-FIN-001", "name": "Finance Item"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(product.status_code, 201)
        product_id = product.json()["data"]["id"]

        supplier = requests.post(
            f"{self.base_url}/counterparties",
            json={"code": "SUP-FIN", "name": "Finance Supplier", "role_flags": 1, "counterparty_type": "supplier"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(supplier.status_code, 201)
        supplier_id = supplier.json()["data"]["id"]

        supplier_contract = requests.post(
            f"{self.base_url}/contracts",
            json={"counterparty_id": supplier_id, "currency_id": currency_id, "number": "SUP-FIN-1", "title": "Supply contract"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(supplier_contract.status_code, 201)
        supplier_contract_id = supplier_contract.json()["data"]["id"]

        invoice = requests.post(
            f"{self.base_url}/purchase-invoices",
            json={
                "counterparty_id": supplier_id,
                "contract_id": supplier_contract_id,
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
        self.assertEqual(invoice.json()["data"]["contract_id"], supplier_contract_id)

        posted_invoice = requests.post(f"{self.base_url}/purchase-invoices/{invoice_id}/post", headers=headers, timeout=2)
        self.assertEqual(posted_invoice.status_code, 200)
        self.assertEqual(posted_invoice.json()["data"]["status"], "posted")

        first_supplier_payment = requests.post(
            f"{self.base_url}/payments",
            json={
                "counterparty_id": supplier_id,
                "contract_id": supplier_contract_id,
                "direction": "outgoing",
                "payment_method": "cash",
                "amount_tmt": "10.00",
                "allocations": [{"doc_type": "purchase_invoice", "doc_id": invoice_id, "allocated_amount": "10.00"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(first_supplier_payment.status_code, 201)
        self.assertEqual(first_supplier_payment.json()["data"]["contract_id"], supplier_contract_id)

        partial_invoice = requests.get(f"{self.base_url}/purchase-invoices/{invoice_id}", headers=headers, timeout=2)
        self.assertEqual(partial_invoice.status_code, 200)
        self.assertEqual(partial_invoice.json()["data"]["payment_status"], "partial")

        excessive_supplier_payment = requests.post(
            f"{self.base_url}/payments",
            json={
                "counterparty_id": supplier_id,
                "contract_id": supplier_contract_id,
                "direction": "outgoing",
                "payment_method": "cash",
                "amount_tmt": "25.00",
                "allocations": [{"doc_type": "purchase_invoice", "doc_id": invoice_id, "allocated_amount": "25.00"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(excessive_supplier_payment.status_code, 400)
        self.assertEqual(excessive_supplier_payment.json()["error"]["code"], "ALLOCATION_EXCEEDS_DOCUMENT_BALANCE")
        self.assertEqual(excessive_supplier_payment.json()["error"]["details"]["remaining_tmt"], "20.00")

        final_supplier_payment = requests.post(
            f"{self.base_url}/payments",
            json={
                "counterparty_id": supplier_id,
                "contract_id": supplier_contract_id,
                "direction": "outgoing",
                "payment_method": "cash",
                "amount_tmt": "20.00",
                "allocations": [{"doc_type": "purchase_invoice", "doc_id": invoice_id, "allocated_amount": "20.00"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(final_supplier_payment.status_code, 201)

        paid_invoice = requests.get(f"{self.base_url}/purchase-invoices/{invoice_id}", headers=headers, timeout=2)
        self.assertEqual(paid_invoice.status_code, 200)
        self.assertEqual(paid_invoice.json()["data"]["payment_status"], "paid")

        supplier_debt = requests.get(f"{self.base_url}/counterparties/{supplier_id}/debt", headers=headers, timeout=2)
        self.assertEqual(supplier_debt.status_code, 200)
        self.assertEqual(supplier_debt.json()["data"]["payable_tmt"], "0.00")

        supplier_card = requests.get(
            f"{self.base_url}/counterparties/{supplier_id}/account-card",
            params={"contract_id": supplier_contract_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(supplier_card.status_code, 200)
        supplier_card_data = supplier_card.json()["data"]
        self.assertEqual(supplier_card_data["debit_total_tmt"], "30.00")
        self.assertEqual(supplier_card_data["credit_total_tmt"], "30.00")
        self.assertEqual(supplier_card_data["closing_balance_tmt"], "0.00")
        self.assertTrue(all(row["contract_id"] == supplier_contract_id for row in supplier_card_data["rows"]))

        supplier_reconciliation = requests.get(
            f"{self.base_url}/counterparties/{supplier_id}/reconciliation",
            params={"contract_id": supplier_contract_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(supplier_reconciliation.status_code, 200)
        self.assertEqual(supplier_reconciliation.json()["data"]["closing_balance_tmt"], "0.00")

        supplier_ledger = requests.get(
            f"{self.base_url}/debt-ledger",
            params={"counterparty_id": supplier_id, "contract_id": supplier_contract_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(supplier_ledger.status_code, 200)
        self.assertTrue(all(row["contract_id"] == supplier_contract_id for row in supplier_ledger.json()["data"]))

        customer = requests.post(
            f"{self.base_url}/counterparties",
            json={
                "code": "CUS-FIN",
                "name": "Finance Customer",
                "role_flags": 2,
                "counterparty_type": "customer",
                "credit_limit_tmt": "5.00",
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(customer.status_code, 201)
        customer_id = customer.json()["data"]["id"]

        customer_contract = requests.post(
            f"{self.base_url}/contracts",
            json={"counterparty_id": customer_id, "currency_id": currency_id, "number": "CUS-FIN-1", "title": "Customer contract"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(customer_contract.status_code, 201)
        customer_contract_id = customer_contract.json()["data"]["id"]

        sale = requests.post(
            f"{self.base_url}/sales",
            json={
                "sale_type": "wholesale",
                "counterparty_id": customer_id,
                "contract_id": customer_contract_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "payment_type": "debt",
                "debt_amount_tmt": "10.00",
                "lines": [{"product_id": product_id, "quantity": "1.0000", "price_final": "10.0000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(sale.status_code, 201)
        sale_payload = sale.json()
        self.assertEqual(sale_payload["data"]["contract_id"], customer_contract_id)
        self.assertEqual(sale_payload["meta"]["warnings"][0]["code"], "CREDIT_LIMIT_EXCEEDED")
        sale_id = sale_payload["data"]["id"]

        posted_sale = requests.post(f"{self.base_url}/sales/{sale_id}/post", headers=headers, timeout=2)
        self.assertEqual(posted_sale.status_code, 200)
        self.assertEqual(posted_sale.json()["data"]["status"], "posted")

        customer_debt = requests.get(f"{self.base_url}/counterparties/{customer_id}/debt", headers=headers, timeout=2)
        self.assertEqual(customer_debt.status_code, 200)
        self.assertEqual(customer_debt.json()["data"]["receivable_tmt"], "10.00")
        self.assertTrue(customer_debt.json()["data"]["credit_limit_exceeded"])
        self.assertEqual(customer_debt.json()["data"]["credit_limit_excess_tmt"], "5.00")

        customer_payment = requests.post(
            f"{self.base_url}/payments",
            json={
                "counterparty_id": customer_id,
                "contract_id": customer_contract_id,
                "direction": "incoming",
                "payment_method": "cash",
                "amount_tmt": "5.00",
                "allocations": [{"doc_type": "sale", "doc_id": sale_id, "allocated_amount": "5.00"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(customer_payment.status_code, 201)

        excessive_customer_payment = requests.post(
            f"{self.base_url}/payments",
            json={
                "counterparty_id": customer_id,
                "contract_id": customer_contract_id,
                "direction": "incoming",
                "payment_method": "cash",
                "amount_tmt": "6.00",
                "allocations": [{"doc_type": "sale", "doc_id": sale_id, "allocated_amount": "6.00"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(excessive_customer_payment.status_code, 400)
        self.assertEqual(excessive_customer_payment.json()["error"]["code"], "ALLOCATION_EXCEEDS_DOCUMENT_BALANCE")
        self.assertEqual(excessive_customer_payment.json()["error"]["details"]["remaining_tmt"], "5.00")

        customer_card = requests.get(
            f"{self.base_url}/counterparties/{customer_id}/account-card",
            params={"contract_id": customer_contract_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(customer_card.status_code, 200)
        customer_card_data = customer_card.json()["data"]
        self.assertEqual(customer_card_data["debit_total_tmt"], "10.00")
        self.assertEqual(customer_card_data["credit_total_tmt"], "5.00")
        self.assertEqual(customer_card_data["closing_balance_tmt"], "5.00")
        self.assertTrue(all(row["contract_id"] == customer_contract_id for row in customer_card_data["rows"]))

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

        x_report = requests.get(f"{self.base_url}/cash-shifts/{shift_id}/x-report", headers=headers, timeout=2)
        self.assertEqual(x_report.status_code, 200)
        self.assertEqual(x_report.json()["data"]["report_type"], "X")
        self.assertEqual(x_report.json()["data"]["shift_status"], "open")
        self.assertEqual(x_report.json()["data"]["expected_cash_tmt"], "17.00")
        self.assertEqual(x_report.json()["data"]["sale_cash_tmt"], "10.00")
        self.assertEqual(x_report.json()["data"]["incoming_cash_payments_tmt"], "5.00")
        self.assertEqual(x_report.json()["data"]["collections_tmt"], "3.00")

        closed = requests.post(
            f"{self.base_url}/cash-shifts/{shift_id}/close",
            json={"closing_amount": "17.00"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["data"]["status"], "closed")

        z_report = requests.post(f"{self.base_url}/cash-shifts/{shift_id}/z-report", json={}, headers=headers, timeout=2)
        self.assertEqual(z_report.status_code, 200)
        self.assertEqual(z_report.json()["data"]["report_type"], "Z")
        self.assertEqual(z_report.json()["data"]["shift_status"], "closed")
        self.assertEqual(z_report.json()["data"]["actual_cash_tmt"], "17.00")
        self.assertEqual(z_report.json()["data"]["variance_tmt"], "0.00")

        sales_report = requests.get(f"{self.base_url}/reports/sales", headers=headers, timeout=2)
        self.assertEqual(sales_report.status_code, 200)
        self.assertEqual(sales_report.json()["data"]["sales_total_tmt"], "30.00")
        self.assertEqual(sales_report.json()["data"]["cash_tmt"], "10.00")
        self.assertEqual(sales_report.json()["data"]["debt_tmt"], "20.00")
        self.assertEqual(len(sales_report.json()["data"]["rows"]), 1)
        self.assertEqual(sales_report.json()["data"]["rows"][0]["signed_amount_tmt"], "30.00")
        chart_points = sales_report.json()["data"]["chart_points"]
        self.assertEqual(len(chart_points), 1)
        self.assertEqual(chart_points[0]["sales_total_tmt"], "30.00")
        self.assertEqual(chart_points[0]["returns_total_tmt"], "0.00")
        self.assertEqual(chart_points[0]["net_amount_tmt"], "30.00")
        self.assertEqual(chart_points[0]["document_count"], 1)
        self.assertEqual(chart_points[0]["cash_tmt"], "10.00")
        self.assertEqual(chart_points[0]["debt_tmt"], "20.00")

        filtered_sales = requests.get(
            f"{self.base_url}/reports/sales",
            params={"warehouse_id": warehouse_id, "counterparty_id": customer_id, "product_id": product_id, "cash_shift_id": shift_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(filtered_sales.status_code, 200)
        self.assertEqual(filtered_sales.json()["data"]["document_count"], 1)
        self.assertEqual(filtered_sales.json()["data"]["rows"][0]["warehouse_id"], warehouse_id)

        stock_report = requests.get(
            f"{self.base_url}/reports/stock",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(stock_report.status_code, 200)
        self.assertEqual(stock_report.json()["data"][0]["quantity"], "3.000")

        purchases_report = requests.get(
            f"{self.base_url}/reports/purchases",
            params={"warehouse_id": warehouse_id, "counterparty_id": supplier_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(purchases_report.status_code, 200)
        self.assertEqual(purchases_report.json()["data"]["purchase_total_tmt"], "50.00")
        self.assertEqual(purchases_report.json()["data"]["net_purchase_tmt"], "50.00")
        self.assertEqual(len(purchases_report.json()["data"]["rows"]), 1)

        profit_loss = requests.get(
            f"{self.base_url}/reports/profit-loss",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(profit_loss.status_code, 200)
        self.assertEqual(profit_loss.json()["data"]["net_revenue_tmt"], "30.00")
        self.assertEqual(profit_loss.json()["data"]["net_cogs_tmt"], "20.00")
        self.assertEqual(profit_loss.json()["data"]["gross_profit_tmt"], "10.00")

        exported_sales = requests.get(
            f"{self.base_url}/reports/sales/export",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(exported_sales.status_code, 200)
        self.assertEqual(exported_sales.json()["data"]["report_code"], "sales")
        self.assertEqual(exported_sales.json()["data"]["row_count"], 1)
        self.assertTrue(exported_sales.json()["data"]["xlsx_base64"].startswith("UEs"))

        saved_filter = requests.post(
            f"{self.base_url}/report-filters",
            json={
                "report_code": "sales",
                "name": "Sale warehouse product",
                "filters": {"warehouse_id": warehouse_id, "product_id": product_id},
                "is_shared": True,
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(saved_filter.status_code, 201)
        filter_id = saved_filter.json()["data"]["id"]
        self.assertEqual(saved_filter.json()["data"]["filters"]["product_id"], product_id)

        listed_filters = requests.get(f"{self.base_url}/report-filters", params={"report_code": "sales"}, headers=headers, timeout=2)
        self.assertEqual(listed_filters.status_code, 200)
        self.assertTrue(any(row["id"] == filter_id for row in listed_filters.json()["data"]))

        patched_filter = requests.patch(
            f"{self.base_url}/report-filters/{filter_id}",
            json={"name": "Sale product export"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(patched_filter.status_code, 200)
        self.assertEqual(patched_filter.json()["data"]["name"], "Sale product export")

        deleted_filter = requests.delete(f"{self.base_url}/report-filters/{filter_id}", headers=headers, timeout=2)
        self.assertEqual(deleted_filter.status_code, 200)
        self.assertTrue(deleted_filter.json()["data"]["deleted"])

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

    def test_document_lifecycle_orders_returns_and_storno(self) -> None:
        """Purchase orders, supplier returns, sale returns, and storno should stay consistent."""

        token = self._login()
        headers = {"X-Session-Token": token}

        currencies = requests.get(f"{self.base_url}/currencies", headers=headers, timeout=2)
        self.assertEqual(currencies.status_code, 200)
        currency_id = next(row for row in currencies.json()["data"] if row["code"] == "TMT")["id"]

        warehouse = requests.post(
            f"{self.base_url}/warehouses",
            json={"code": "WH-LIFE", "name": "Lifecycle warehouse"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(warehouse.status_code, 201)
        warehouse_id = warehouse.json()["data"]["id"]

        register = requests.post(
            f"{self.base_url}/cash-registers",
            json={"name": "Lifecycle Register", "warehouse_id": warehouse_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(register.status_code, 201)
        register_id = register.json()["data"]["id"]

        shift = requests.post(
            f"{self.base_url}/cash-shifts/open",
            json={"cash_register_id": register_id, "opening_amount": "0.00"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(shift.status_code, 201)
        shift_id = shift.json()["data"]["id"]

        product = requests.post(
            f"{self.base_url}/products",
            json={"sku": "P-LIFE-001", "name": "Lifecycle Item"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(product.status_code, 201)
        product_id = product.json()["data"]["id"]

        supplier = requests.post(
            f"{self.base_url}/counterparties",
            json={"code": "SUP-LIFE", "name": "Lifecycle Supplier", "role_flags": 1, "counterparty_type": "supplier"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(supplier.status_code, 201)
        supplier_id = supplier.json()["data"]["id"]

        customer = requests.post(
            f"{self.base_url}/counterparties",
            json={"code": "CUS-LIFE", "name": "Lifecycle Customer", "role_flags": 2, "counterparty_type": "customer"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(customer.status_code, 201)
        customer_id = customer.json()["data"]["id"]

        order = requests.post(
            f"{self.base_url}/purchase-orders",
            json={
                "counterparty_id": supplier_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "currency_rate": "1",
                "lines": [{"product_id": product_id, "quantity": "5.0000", "price_cur": "4.0000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(order.status_code, 201)
        order_id = order.json()["data"]["id"]
        order_line_id = order.json()["data"]["lines"][0]["id"]
        self.assertEqual(order.json()["data"]["status"], "draft")

        sent_order = requests.post(f"{self.base_url}/purchase-orders/{order_id}/send", headers=headers, timeout=2)
        self.assertEqual(sent_order.status_code, 200)
        self.assertEqual(sent_order.json()["data"]["status"], "sent")

        first_invoice = requests.post(
            f"{self.base_url}/purchase-invoices",
            json={
                "purchase_order_id": order_id,
                "counterparty_id": supplier_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "currency_rate": "1",
                "lines": [
                    {
                        "purchase_order_line_id": order_line_id,
                        "product_id": product_id,
                        "quantity": "3.0000",
                        "price_cur": "4.0000",
                    }
                ],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(first_invoice.status_code, 201)
        first_invoice_id = first_invoice.json()["data"]["id"]
        posted_first = requests.post(f"{self.base_url}/purchase-invoices/{first_invoice_id}/post", headers=headers, timeout=2)
        self.assertEqual(posted_first.status_code, 200)

        partial_order = requests.get(f"{self.base_url}/purchase-orders/{order_id}", headers=headers, timeout=2)
        self.assertEqual(partial_order.status_code, 200)
        self.assertEqual(partial_order.json()["data"]["status"], "partial")
        self.assertEqual(partial_order.json()["data"]["lines"][0]["quantity_received"], "3.0000")

        second_invoice = requests.post(
            f"{self.base_url}/purchase-invoices",
            json={
                "purchase_order_id": order_id,
                "counterparty_id": supplier_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "currency_rate": "1",
                "lines": [
                    {
                        "purchase_order_line_id": order_line_id,
                        "product_id": product_id,
                        "quantity": "2.0000",
                        "price_cur": "4.0000",
                    }
                ],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(second_invoice.status_code, 201)
        posted_second = requests.post(
            f"{self.base_url}/purchase-invoices/{second_invoice.json()['data']['id']}/post",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(posted_second.status_code, 200)

        received_order = requests.get(f"{self.base_url}/purchase-orders/{order_id}", headers=headers, timeout=2)
        self.assertEqual(received_order.status_code, 200)
        self.assertEqual(received_order.json()["data"]["status"], "received")
        self.assertEqual(received_order.json()["data"]["lines"][0]["quantity_received"], "5.0000")

        supplier_return = requests.post(
            f"{self.base_url}/purchase-invoices/return",
            json={
                "purchase_order_id": order_id,
                "return_invoice_id": first_invoice_id,
                "counterparty_id": supplier_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "currency_rate": "1",
                "lines": [
                    {
                        "purchase_order_line_id": order_line_id,
                        "product_id": product_id,
                        "quantity": "1.0000",
                        "price_cur": "4.0000",
                    }
                ],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(supplier_return.status_code, 201)
        self.assertTrue(supplier_return.json()["data"]["is_return"])
        posted_supplier_return = requests.post(
            f"{self.base_url}/purchase-invoices/{supplier_return.json()['data']['id']}/post",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(posted_supplier_return.status_code, 200)

        returned_order = requests.get(f"{self.base_url}/purchase-orders/{order_id}", headers=headers, timeout=2)
        self.assertEqual(returned_order.json()["data"]["status"], "partial")
        self.assertEqual(returned_order.json()["data"]["lines"][0]["quantity_received"], "4.0000")

        supplier_debt = requests.get(f"{self.base_url}/counterparties/{supplier_id}/debt-summary", headers=headers, timeout=2)
        self.assertEqual(supplier_debt.status_code, 200)
        self.assertEqual(supplier_debt.json()["data"]["payable"], "16.00")

        stock_after_purchase_return = requests.get(
            f"{self.base_url}/stock/balances",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(stock_after_purchase_return.json()["data"][0]["quantity"], "4.000")

        sale = requests.post(
            f"{self.base_url}/sales",
            json={
                "sale_type": "retail",
                "cash_register_id": register_id,
                "cash_shift_id": shift_id,
                "counterparty_id": customer_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "payment_type": "debt",
                "lines": [{"product_id": product_id, "quantity": "2.0000", "price_final": "10.0000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(sale.status_code, 201)
        sale_id = sale.json()["data"]["id"]
        posted_sale = requests.post(f"{self.base_url}/sales/{sale_id}/post", headers=headers, timeout=2)
        self.assertEqual(posted_sale.status_code, 200)
        sale_line_id = posted_sale.json()["data"]["lines"][0]["id"]

        sale_return = requests.post(
            f"{self.base_url}/sale-returns",
            json={
                "sale_id": sale_id,
                "cash_register_id": register_id,
                "cash_shift_id": shift_id,
                "refund_method": "debt_correction",
                "lines": [{"source_sale_line_id": sale_line_id, "quantity": "1.0000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(sale_return.status_code, 201)
        sale_return_id = sale_return.json()["data"]["id"]
        self.assertEqual(sale_return.json()["data"]["receivable_correction_tmt"], "10.00")

        posted_return = requests.post(f"{self.base_url}/sale-returns/{sale_return_id}/post", headers=headers, timeout=2)
        self.assertEqual(posted_return.status_code, 200)
        self.assertEqual(posted_return.json()["data"]["status"], "posted")

        customer_debt = requests.get(f"{self.base_url}/counterparties/{customer_id}/debt-summary", headers=headers, timeout=2)
        self.assertEqual(customer_debt.status_code, 200)
        self.assertEqual(customer_debt.json()["data"]["receivable"], "10.00")

        stock_after_sale_return = requests.get(
            f"{self.base_url}/stock/balances",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(stock_after_sale_return.json()["data"][0]["quantity"], "3.000")

        excessive_return = requests.post(
            f"{self.base_url}/sale-returns",
            json={
                "sale_id": sale_id,
                "cash_register_id": register_id,
                "cash_shift_id": shift_id,
                "refund_method": "debt_correction",
                "lines": [{"source_sale_line_id": sale_line_id, "quantity": "2.0000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(excessive_return.status_code, 400)
        self.assertEqual(excessive_return.json()["error"]["code"], "RETURN_EXCEEDS_SALE")

        blocked_sale_cancel = requests.post(f"{self.base_url}/sales/{sale_id}/cancel", headers=headers, timeout=2)
        self.assertEqual(blocked_sale_cancel.status_code, 400)
        self.assertEqual(blocked_sale_cancel.json()["error"]["code"], "SALE_HAS_RETURNS")

        sales_report = requests.get(f"{self.base_url}/reports/sales", headers=headers, timeout=2)
        self.assertEqual(sales_report.status_code, 200)
        self.assertEqual(sales_report.json()["data"]["returns_amount_tmt"], "10.00")
        self.assertEqual(sales_report.json()["data"]["net_amount_tmt"], "10.00")
        chart_points = sales_report.json()["data"]["chart_points"]
        self.assertEqual(len(chart_points), 1)
        self.assertEqual(chart_points[0]["sales_total_tmt"], "20.00")
        self.assertEqual(chart_points[0]["returns_total_tmt"], "10.00")
        self.assertEqual(chart_points[0]["net_amount_tmt"], "10.00")
        self.assertEqual(chart_points[0]["document_count"], 1)
        self.assertEqual(chart_points[0]["returns_count"], 1)
        self.assertEqual(chart_points[0]["debt_tmt"], "10.00")

        cancelled_return = requests.post(f"{self.base_url}/sale-returns/{sale_return_id}/cancel", headers=headers, timeout=2)
        self.assertEqual(cancelled_return.status_code, 200)
        self.assertEqual(cancelled_return.json()["data"]["status"], "cancelled")

        sale_cancel = requests.post(f"{self.base_url}/sales/{sale_id}/cancel", headers=headers, timeout=2)
        self.assertEqual(sale_cancel.status_code, 200)
        self.assertEqual(sale_cancel.json()["data"]["status"], "cancelled")

        final_stock = requests.get(
            f"{self.base_url}/stock/balances",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(final_stock.json()["data"][0]["quantity"], "4.000")

        final_customer_debt = requests.get(f"{self.base_url}/counterparties/{customer_id}/debt-summary", headers=headers, timeout=2)
        self.assertEqual(final_customer_debt.json()["data"]["receivable"], "0.00")


    def test_promotions_loyalty_and_price_list_import_export(self) -> None:
        """Promotions, XLSX-friendly price import/export, and loyalty postings should work together."""

        token = self._login()
        headers = {"X-Session-Token": token}

        currencies = requests.get(f"{self.base_url}/currencies", headers=headers, timeout=2)
        self.assertEqual(currencies.status_code, 200)
        currency_id = next(row for row in currencies.json()["data"] if row["code"] == "TMT")["id"]

        warehouse = requests.post(
            f"{self.base_url}/warehouses",
            json={"code": "WH-PROMO", "name": "Promo warehouse"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(warehouse.status_code, 201)
        warehouse_id = warehouse.json()["data"]["id"]

        register = requests.post(
            f"{self.base_url}/cash-registers",
            json={"name": "Promo Register", "warehouse_id": warehouse_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(register.status_code, 201)
        register_id = register.json()["data"]["id"]

        shift = requests.post(
            f"{self.base_url}/cash-shifts/open",
            json={"cash_register_id": register_id, "opening_amount": "0.00"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(shift.status_code, 201)
        shift_id = shift.json()["data"]["id"]

        product = requests.post(
            f"{self.base_url}/products",
            json={"sku": "P-PROMO-001", "name": "Promo Item"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(product.status_code, 201)
        product_id = product.json()["data"]["id"]

        gift = requests.post(
            f"{self.base_url}/products",
            json={"sku": "P-GIFT-001", "name": "Gift Item"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(gift.status_code, 201)
        gift_id = gift.json()["data"]["id"]

        inventory = requests.post(
            f"{self.base_url}/inventories",
            json={
                "warehouse_id": warehouse_id,
                "lines": [
                    {"product_id": product_id, "qty_actual": "10.000", "unit_cost_tmt": "5.00"},
                    {"product_id": gift_id, "qty_actual": "10.000", "unit_cost_tmt": "1.00"},
                ],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(inventory.status_code, 201)
        posted_inventory = requests.post(
            f"{self.base_url}/inventories/{inventory.json()['data']['id']}/post",
            headers=headers,
            timeout=2,
        )
        self.assertEqual(posted_inventory.status_code, 200)

        price_list = requests.post(
            f"{self.base_url}/price-lists",
            json={"name_ru": "Promo Retail", "currency_id": currency_id, "is_default": True},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(price_list.status_code, 201)
        price_list_id = price_list.json()["data"]["id"]

        price_item = requests.post(
            f"{self.base_url}/price-lists/{price_list_id}/items",
            json={"product_id": product_id, "price_tmt": "10.0000", "valid_from": "2026-01-01"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(price_item.status_code, 201)

        exported = requests.get(f"{self.base_url}/price-lists/{price_list_id}/export", headers=headers, timeout=2)
        self.assertEqual(exported.status_code, 200)
        self.assertTrue(exported.json()["data"]["xlsx_base64"])
        self.assertEqual(len(exported.json()["data"]["rows"]), 1)

        imported = requests.post(
            f"{self.base_url}/price-lists/{price_list_id}/import",
            json={
                "duplicate_mode": "update",
                "rows": [
                    {"product_sku": "P-PROMO-001", "price_tmt": "12.0000", "valid_from": "2026-01-01"}
                ],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["data"]["updated"], 1)

        current_price = requests.get(
            f"{self.base_url}/prices/current",
            params={"product_id": product_id, "on_date": "2026-06-13"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(current_price.status_code, 200)
        self.assertEqual(current_price.json()["data"]["price_tmt"], "12.0000")

        discount = requests.post(
            f"{self.base_url}/promotions",
            json={
                "name": "Ten percent off",
                "promotion_type": "discount",
                "target_type": "product",
                "product_id": product_id,
                "discount_type": "percent",
                "discount_value": "10",
                "min_quantity": "1",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": "2026-12-31T23:59:59+00:00",
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(discount.status_code, 201)

        gift_promo = requests.post(
            f"{self.base_url}/promotions",
            json={
                "name": "Buy two get gift",
                "promotion_type": "gift",
                "target_type": "product",
                "product_id": product_id,
                "min_quantity": "2",
                "gift_product_id": gift_id,
                "gift_quantity": "1",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": "2026-12-31T23:59:59+00:00",
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(gift_promo.status_code, 201)

        settings = requests.put(
            f"{self.base_url}/loyalty-settings",
            json={"earn_rate_percent": "10", "redemption_limit_percent": "50", "is_active": True},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(settings.status_code, 200)

        customer = requests.post(
            f"{self.base_url}/counterparties",
            json={"code": "CUS-PROMO", "name": "Promo Customer", "role_flags": 2, "counterparty_type": "customer"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(customer.status_code, 201)
        customer_id = customer.json()["data"]["id"]

        card = requests.post(
            f"{self.base_url}/loyalty-cards",
            json={"card_number": "LC-PROMO-001", "counterparty_id": customer_id, "balance_tmt": "20.00"},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(card.status_code, 201)
        card_id = card.json()["data"]["id"]
        self.assertEqual(card.json()["data"]["balance_tmt"], "20.00")

        sale = requests.post(
            f"{self.base_url}/sales",
            json={
                "doc_date": "2026-06-13T12:00:00+00:00",
                "sale_type": "retail",
                "cash_register_id": register_id,
                "cash_shift_id": shift_id,
                "counterparty_id": customer_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "payment_type": "mixed",
                "paid_cash_tmt": "16.00",
                "paid_bonus_tmt": "2.00",
                "loyalty_card_id": card_id,
                "lines": [{"product_id": product_id, "quantity": "2.0000", "price_final": "10.0000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(sale.status_code, 201)
        self.assertEqual(sale.json()["data"]["total_amount_tmt"], "18.00")
        sale_lines = sale.json()["data"]["lines"]
        product_line = next(line for line in sale_lines if line["line_type"] == "product")
        gift_line = next(line for line in sale_lines if line["line_type"] == "promo_gift")
        self.assertEqual(product_line["price_final"], "9.0000")
        self.assertEqual(product_line["amount_tmt"], "18.00")
        self.assertEqual(gift_line["product_id"], gift_id)
        self.assertEqual(gift_line["quantity"], "1.0000")
        sale_id = sale.json()["data"]["id"]

        posted_sale = requests.post(f"{self.base_url}/sales/{sale_id}/post", headers=headers, timeout=2)
        self.assertEqual(posted_sale.status_code, 200)
        self.assertEqual(posted_sale.json()["data"]["status"], "posted")

        product_balance = requests.get(
            f"{self.base_url}/stock/balances",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=headers,
            timeout=2,
        )
        gift_balance = requests.get(
            f"{self.base_url}/stock/balances",
            params={"warehouse_id": warehouse_id, "product_id": gift_id},
            headers=headers,
            timeout=2,
        )
        self.assertEqual(product_balance.json()["data"][0]["quantity"], "8.000")
        self.assertEqual(gift_balance.json()["data"][0]["quantity"], "9.000")

        card_after_sale = requests.get(f"{self.base_url}/loyalty-cards?search=LC-PROMO-001", headers=headers, timeout=2)
        self.assertEqual(card_after_sale.status_code, 200)
        self.assertEqual(card_after_sale.json()["data"][0]["balance_tmt"], "19.60")

        sale_return = requests.post(
            f"{self.base_url}/sale-returns",
            json={
                "sale_id": sale_id,
                "cash_register_id": register_id,
                "cash_shift_id": shift_id,
                "refund_method": "bonus",
                "refund_bonus_tmt": "9.00",
                "lines": [{"source_sale_line_id": product_line["id"], "quantity": "1.0000"}],
            },
            headers=headers,
            timeout=2,
        )
        self.assertEqual(sale_return.status_code, 201)
        self.assertEqual(sale_return.json()["data"]["total_amount_tmt"], "9.00")
        self.assertEqual(sale_return.json()["data"]["refund_bonus_tmt"], "9.00")
        sale_return_id = sale_return.json()["data"]["id"]

        posted_return = requests.post(f"{self.base_url}/sale-returns/{sale_return_id}/post", headers=headers, timeout=2)
        self.assertEqual(posted_return.status_code, 200)
        self.assertEqual(posted_return.json()["data"]["status"], "posted")

        card_after_return = requests.get(f"{self.base_url}/loyalty-cards?search=LC-PROMO-001", headers=headers, timeout=2)
        self.assertEqual(card_after_return.json()["data"][0]["balance_tmt"], "28.80")

        sales_report = requests.get(f"{self.base_url}/reports/sales", headers=headers, timeout=2)
        self.assertEqual(sales_report.status_code, 200)
        self.assertEqual(sales_report.json()["data"]["bonus_tmt"], "2.00")
        self.assertEqual(sales_report.json()["data"]["return_bonus_tmt"], "9.00")

        cancelled_return = requests.post(f"{self.base_url}/sale-returns/{sale_return_id}/cancel", headers=headers, timeout=2)
        self.assertEqual(cancelled_return.status_code, 200)
        card_after_return_cancel = requests.get(f"{self.base_url}/loyalty-cards?search=LC-PROMO-001", headers=headers, timeout=2)
        self.assertEqual(card_after_return_cancel.json()["data"][0]["balance_tmt"], "19.60")

        cancelled_sale = requests.post(f"{self.base_url}/sales/{sale_id}/cancel", headers=headers, timeout=2)
        self.assertEqual(cancelled_sale.status_code, 200)
        card_after_sale_cancel = requests.get(f"{self.base_url}/loyalty-cards?search=LC-PROMO-001", headers=headers, timeout=2)
        self.assertEqual(card_after_sale_cancel.json()["data"][0]["balance_tmt"], "20.00")

        transactions = requests.get(f"{self.base_url}/loyalty-cards/{card_id}/transactions", headers=headers, timeout=2)
        self.assertEqual(transactions.status_code, 200)
        transaction_types = {row["transaction_type"] for row in transactions.json()["data"]}
        self.assertTrue({"opening_balance", "redemption", "accrual", "return_refund", "return_redemption_reversal", "return_accrual_reversal", "return_cancellation", "cancellation"}.issubset(transaction_types))



if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

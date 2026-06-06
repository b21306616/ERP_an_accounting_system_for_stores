"""FastAPI smoke tests with an in-memory SQLite database."""

from __future__ import annotations

import unittest
import socket
import threading
import time

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import uvicorn

from server_app.api.app import create_app
from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig
from server_app.core.constants import BUILTIN_ROLES
from server_app.core.security import hash_password
from server_app.db.base import Base
from server_app.db.models import Role, User


class ApiSmokeTests(unittest.TestCase):
    """Validate core API behavior without requiring MSSQL."""

    def setUp(self) -> None:
        """Create a fresh in-memory database and FastAPI test client."""

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
            roles = {name: Role(name=name) for name in BUILTIN_ROLES}
            session.add_all(roles.values())
            session.add(
                User(
                    username="owner",
                    full_name="Owner",
                    password_hash=hash_password("password123"),
                    role=roles["Owner"],
                    is_active=True,
                )
            )
            session.add(
                User(
                    username="cashier",
                    full_name="Cashier",
                    password_hash=hash_password("password123"),
                    role=roles["Cashier"],
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
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._wait_for_server()

    def tearDown(self) -> None:
        """Dispose the in-memory database."""

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
        while time.time() < deadline:
            try:
                response = requests.get(f"{self.base_url}/health", timeout=0.5)
                if response.status_code == 200:
                    return
            except Exception as exc:
                last_error = exc
            time.sleep(0.05)
        raise RuntimeError(f"API test server did not start: {last_error}")

    def _login(self, username: str) -> str:
        """Return an access token for a seeded user."""

        response = requests.post(
            f"{self.base_url}/auth/login",
            json={"username": username, "password": "password123"},
            timeout=2,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def test_health(self) -> None:
        """Health endpoint should report ok when DB is reachable."""

        response = requests.get(f"{self.base_url}/health", timeout=2)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_login_and_me(self) -> None:
        """Login token should authorize the current-user endpoint."""

        token = self._login("owner")
        response = requests.get(
            f"{self.base_url}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "owner")
        self.assertEqual(response.json()["role"], "Owner")

    def test_protected_endpoint_rejects_missing_token(self) -> None:
        """Protected endpoints should reject unauthenticated calls."""

        response = requests.get(f"{self.base_url}/reference/currencies", timeout=2)

        self.assertEqual(response.status_code, 401)

    def test_owner_can_create_currency(self) -> None:
        """Owner role should be allowed to create reference data."""

        token = self._login("owner")
        response = requests.post(
            f"{self.base_url}/reference/currencies",
            json={"code": "USD", "name": "US Dollar", "symbol": "$"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["code"], "USD")

    def test_cashier_cannot_create_currency(self) -> None:
        """Non-owner roles should not pass Owner-only dependency checks."""

        token = self._login("cashier")
        response = requests.post(
            f"{self.base_url}/reference/currencies",
            json={"code": "USD", "name": "US Dollar", "symbol": "$"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()

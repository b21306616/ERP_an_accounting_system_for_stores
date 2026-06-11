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
from server_app.core.constants import (
    BUILTIN_ROLES,
    SUPER_ADMIN_FULL_NAME,
    SUPER_ADMIN_ROLE,
    SUPER_ADMIN_USERNAME,
)
from server_app.core.security import hash_password, verify_password
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
                    username=SUPER_ADMIN_USERNAME,
                    full_name=SUPER_ADMIN_FULL_NAME,
                    password_hash=hash_password("password123"),
                    role=roles[SUPER_ADMIN_ROLE],
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

    def _super_admin_id(self, token: str) -> int:
        """Return the seeded Super Admin user id."""

        response = requests.get(
            f"{self.base_url}/users",
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )
        self.assertEqual(response.status_code, 200)
        for user in response.json():
            if user["username"] == SUPER_ADMIN_USERNAME:
                return int(user["id"])
        raise AssertionError("Seeded super_admin user was not returned by /users")

    def test_health(self) -> None:
        """Health endpoint should report ok when DB is reachable."""

        response = requests.get(f"{self.base_url}/health", timeout=2)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_login_and_me(self) -> None:
        """Login token should authorize the current-user endpoint."""

        token = self._login(SUPER_ADMIN_USERNAME)
        response = requests.get(
            f"{self.base_url}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], SUPER_ADMIN_USERNAME)
        self.assertEqual(response.json()["role"], SUPER_ADMIN_ROLE)

    def test_protected_endpoint_rejects_missing_token(self) -> None:
        """Protected endpoints should reject unauthenticated calls."""

        response = requests.get(f"{self.base_url}/reference/currencies", timeout=2)

        self.assertEqual(response.status_code, 401)

    def test_super_admin_can_create_currency(self) -> None:
        """Super Admin role should be allowed to create reference data."""

        token = self._login(SUPER_ADMIN_USERNAME)
        response = requests.post(
            f"{self.base_url}/reference/currencies",
            json={"code": "USD", "name": "US Dollar", "symbol": "$"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["code"], "USD")

    def test_cashier_cannot_create_currency(self) -> None:
        """Non-super-admin roles should not pass Super Admin dependency checks."""

        token = self._login("cashier")
        response = requests.post(
            f"{self.base_url}/reference/currencies",
            json={"code": "USD", "name": "US Dollar", "symbol": "$"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 403)

    def test_user_api_blocks_super_admin_role_assignment(self) -> None:
        """The reserved Super Admin role should not be assigned to regular users."""

        token = self._login(SUPER_ADMIN_USERNAME)
        response = requests.post(
            f"{self.base_url}/users",
            json={
                "username": "extra_admin",
                "full_name": "Extra Admin",
                "password": "password123",
                "role_name": SUPER_ADMIN_ROLE,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 400)

    def test_user_api_blocks_duplicate_super_admin_creation(self) -> None:
        """The fixed super_admin username should not be created through the API."""

        token = self._login(SUPER_ADMIN_USERNAME)
        response = requests.post(
            f"{self.base_url}/users",
            json={
                "username": SUPER_ADMIN_USERNAME,
                "full_name": SUPER_ADMIN_FULL_NAME,
                "password": "password123",
                "role_name": "Cashier",
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 400)

    def test_user_api_blocks_super_admin_profile_changes(self) -> None:
        """The fixed Super Admin identity fields should not be editable."""

        token = self._login(SUPER_ADMIN_USERNAME)
        user_id = self._super_admin_id(token)
        response = requests.patch(
            f"{self.base_url}/users/{user_id}",
            json={"full_name": "Changed Name"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 400)

    def test_user_api_blocks_super_admin_role_changes(self) -> None:
        """The fixed Super Admin role should not be editable."""

        token = self._login(SUPER_ADMIN_USERNAME)
        user_id = self._super_admin_id(token)
        response = requests.patch(
            f"{self.base_url}/users/{user_id}",
            json={"role_name": "Cashier"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 400)

    def test_user_api_changes_super_admin_password_with_current_password(self) -> None:
        """Super Admin password changes should require the current password."""

        token = self._login(SUPER_ADMIN_USERNAME)
        user_id = self._super_admin_id(token)
        response = requests.patch(
            f"{self.base_url}/users/{user_id}",
            json={"password": "changed123", "current_password": "password123"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 200)

        with self.session_factory() as session:
            user = session.get(User, user_id)
            self.assertIsNotNone(user)
            assert user is not None
            self.assertTrue(verify_password("changed123", user.password_hash))

    def test_user_api_rejects_wrong_super_admin_current_password(self) -> None:
        """The old password must match before changing the Super Admin password."""

        token = self._login(SUPER_ADMIN_USERNAME)
        user_id = self._super_admin_id(token)
        response = requests.patch(
            f"{self.base_url}/users/{user_id}",
            json={"password": "changed123", "current_password": "wrong-password"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 403)

    def test_user_api_blocks_super_admin_deactivation(self) -> None:
        """The fixed Super Admin account should always remain active."""

        token = self._login(SUPER_ADMIN_USERNAME)
        user_id = self._super_admin_id(token)
        response = requests.delete(
            f"{self.base_url}/users/{user_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

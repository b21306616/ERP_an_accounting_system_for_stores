"""HTTP client for the documented ERP server API v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from user_app.core.config import normalize_server_url


class ApiClientError(RuntimeError):
    """Raised when the server returns an API or transport error."""


@dataclass(slots=True)
class AuthenticatedUser:
    """Current user data returned by API v1."""

    id: int
    username: str
    full_name: str
    role_name: str
    permissions: list[str]


class ApiClient:
    """Small requests-based client for the LAN server."""

    def __init__(self, base_url: str, timeout_seconds: float = 8.0) -> None:
        self.base_url = normalize_server_url(base_url)
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session_token: str | None = None
        self.current_user: AuthenticatedUser | None = None

    def set_base_url(self, base_url: str) -> None:
        """Update the server base URL."""

        self.base_url = normalize_server_url(base_url)

    def login(
        self,
        username: str,
        password: str,
        client_name: str = "PyQt user client",
        client_version: str = "0.1.0",
    ) -> AuthenticatedUser:
        """Open an API v1 session."""

        data = self._request(
            "POST",
            "/auth/login",
            json={
                "username": username,
                "password": password,
                "client_name": client_name,
                "client_version": client_version,
            },
            authenticated=False,
        )
        token = str(data["session_token"])
        user = self._parse_user(data["user"])
        self.session_token = token
        self.current_user = user
        return user

    def logout(self) -> None:
        """Close the current API v1 session."""

        if self.session_token:
            try:
                self._request("POST", "/auth/logout")
            finally:
                self.session_token = None
                self.current_user = None

    def get_status(self) -> dict[str, Any]:
        """Return server status."""

        return dict(self._request("GET", "/system/status"))

    def get_users(self) -> list[dict[str, Any]]:
        """Return users visible to the current account."""

        return list(self._request("GET", "/users"))

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a user."""

        return dict(self._request("POST", "/users", json=payload))

    def get_roles(self) -> list[dict[str, Any]]:
        """Return roles visible to the current account."""

        return list(self._request("GET", "/roles"))

    def get_permissions(self) -> list[dict[str, Any]]:
        """Return permissions visible to the current account."""

        return list(self._request("GET", "/permissions"))

    def get_settings(self) -> dict[str, Any]:
        """Return settings."""

        return dict(self._request("GET", "/settings"))

    def update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        """Update settings."""

        return dict(self._request("PUT", "/settings", json={"values": values}))

    def get_workplaces(self) -> list[dict[str, Any]]:
        """Return workplaces."""

        return list(self._request("GET", "/workplaces"))

    def create_workplace(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a workplace."""

        return dict(self._request("POST", "/workplaces", json=payload))

    def get_product_groups(self) -> list[dict[str, Any]]:
        """Return product groups."""

        return list(self._request("GET", "/product-groups"))

    def create_product_group(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a product group."""

        return dict(self._request("POST", "/product-groups", json=payload))

    def get_products(self, search: str | None = None) -> list[dict[str, Any]]:
        """Return products."""

        path = "/products"
        if search:
            path = f"{path}?search={requests.utils.quote(search)}"
        return list(self._request("GET", path))

    def create_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a product."""

        return dict(self._request("POST", "/products", json=payload))

    def add_product_barcode(self, product_id: int, barcode: str) -> dict[str, Any]:
        """Add a barcode to a product."""

        return dict(self._request("POST", f"/products/{product_id}/barcodes", json={"barcode": barcode}))

    def find_product_by_barcode(self, barcode: str) -> dict[str, Any]:
        """Find a product by barcode."""

        return dict(self._request("GET", f"/products/by-barcode/{requests.utils.quote(barcode)}"))

    def get_services(self, search: str | None = None) -> list[dict[str, Any]]:
        """Return services."""

        path = "/services"
        if search:
            path = f"{path}?search={requests.utils.quote(search)}"
        return list(self._request("GET", path))

    def create_service(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a service."""

        return dict(self._request("POST", "/services", json=payload))

    def get_expense_categories(self) -> list[dict[str, Any]]:
        """Return expense categories."""

        return list(self._request("GET", "/expense-categories"))

    def get_warehouses(self) -> list[dict[str, Any]]:
        """Return warehouses."""

        return list(self._request("GET", "/warehouses"))

    def create_warehouse(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a warehouse."""

        return dict(self._request("POST", "/warehouses", json=payload))

    def get_stock_balances(
        self,
        warehouse_id: int | None = None,
        product_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return stock balances."""

        return list(
            self._request(
                "GET",
                self._path_with_params(
                    "/stock/balances",
                    {"warehouse_id": warehouse_id, "product_id": product_id},
                ),
            )
        )

    def get_stock_movements(
        self,
        warehouse_id: int | None = None,
        product_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent stock movements."""

        return list(
            self._request(
                "GET",
                self._path_with_params(
                    "/stock/movements",
                    {"warehouse_id": warehouse_id, "product_id": product_id},
                ),
            )
        )

    def create_inventory(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create an inventory document."""

        return dict(self._request("POST", "/inventories", json=payload))

    def replace_inventory_lines(self, inventory_id: int, lines: list[dict[str, Any]]) -> dict[str, Any]:
        """Replace counted inventory lines."""

        return dict(self._request("PUT", f"/inventories/{inventory_id}/lines", json={"lines": lines}))

    def post_inventory(self, inventory_id: int) -> dict[str, Any]:
        """Post an inventory document."""

        return dict(self._request("POST", f"/inventories/{inventory_id}/post"))

    def create_stock_transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a stock transfer."""

        return dict(self._request("POST", "/stock-transfers", json=payload))

    def send_stock_transfer(self, transfer_id: int) -> dict[str, Any]:
        """Send a stock transfer."""

        return dict(self._request("POST", f"/stock-transfers/{transfer_id}/send"))

    def receive_stock_transfer(self, transfer_id: int) -> dict[str, Any]:
        """Receive a stock transfer."""

        return dict(self._request("POST", f"/stock-transfers/{transfer_id}/receive"))

    def reject_stock_transfer(self, transfer_id: int) -> dict[str, Any]:
        """Reject a stock transfer."""

        return dict(self._request("POST", f"/stock-transfers/{transfer_id}/reject"))

    def create_stock_writeoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a stock write-off."""

        return dict(self._request("POST", "/stock-writeoffs", json=payload))

    def post_stock_writeoff(self, writeoff_id: int) -> dict[str, Any]:
        """Post a stock write-off."""

        return dict(self._request("POST", f"/stock-writeoffs/{writeoff_id}/post"))

    def cancel_stock_writeoff(self, writeoff_id: int) -> dict[str, Any]:
        """Cancel a stock write-off."""

        return dict(self._request("POST", f"/stock-writeoffs/{writeoff_id}/cancel"))

    def _path_with_params(self, path: str, params: dict[str, Any]) -> str:
        """Append URL query parameters, skipping empty values."""

        clean = {key: value for key, value in params.items() if value is not None and value != ""}
        if not clean:
            return path
        return f"{path}?{requests.compat.urlencode(clean)}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Any:
        """Send one request and return envelope data."""

        headers: dict[str, str] = {}
        if authenticated:
            if not self.session_token:
                raise ApiClientError("No active session token.")
            headers["X-Session-Token"] = self.session_token

        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(
                method,
                url,
                json=json,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise ApiClientError(f"Could not connect to server: {exc}") from exc

        try:
            envelope = response.json()
        except ValueError as exc:
            raise ApiClientError(f"Server returned non-JSON response: HTTP {response.status_code}") from exc

        if not isinstance(envelope, dict) or "success" not in envelope:
            raise ApiClientError("Server response is not an API v1 envelope.")

        if not response.ok or not envelope.get("success"):
            error = envelope.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else None
            raise ApiClientError(str(message or f"HTTP {response.status_code}"))

        return envelope.get("data")

    def _parse_user(self, data: dict[str, Any]) -> AuthenticatedUser:
        """Convert user payload into a typed object."""

        return AuthenticatedUser(
            id=int(data["id"]),
            username=str(data["username"]),
            full_name=str(data["full_name"]),
            role_name=str(data["role_name"]),
            permissions=[str(item) for item in data.get("permissions", [])],
        )

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

    def get_currencies(self) -> list[dict[str, Any]]:
        """Return currencies."""

        return list(self._request("GET", "/currencies"))

    def get_counterparties(self, search: str | None = None, include_debt: bool = False) -> list[dict[str, Any]]:
        """Return counterparties."""

        return list(
            self._request(
                "GET",
                self._path_with_params("/counterparties", {"search": search, "include_debt": str(include_debt).lower()}),
            )
        )

    def create_counterparty(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a counterparty."""

        return dict(self._request("POST", "/counterparties", json=payload))

    def get_debt_summary(self, counterparty_id: int) -> dict[str, Any]:
        """Return debt balances for one counterparty."""

        return dict(self._request("GET", f"/counterparties/{counterparty_id}/debt-summary"))

    def get_counterparty_debt(self, counterparty_id: int) -> dict[str, Any]:
        """Return documented counterparty debt balances and credit-limit state."""

        return dict(self._request("GET", f"/counterparties/{counterparty_id}/debt"))

    def get_debt_ledger(
        self,
        counterparty_id: int | None = None,
        debt_type: str | None = None,
        contract_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return debt ledger rows."""

        return list(
            self._request(
                "GET",
                self._path_with_params(
                    "/debt-ledger",
                    {
                        "counterparty_id": counterparty_id,
                        "debt_type": debt_type,
                        "contract_id": contract_id,
                        "date_from": date_from,
                        "date_to": date_to,
                    },
                ),
            )
        )

    def get_contracts(self, counterparty_id: int | None = None, active_only: bool = False) -> list[dict[str, Any]]:
        """Return counterparty contracts."""

        return list(self._request("GET", self._path_with_params("/contracts", {"counterparty_id": counterparty_id, "active_only": str(active_only).lower()})))

    def create_contract(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a counterparty contract."""

        return dict(self._request("POST", "/contracts", json=payload))

    def update_contract(self, contract_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Patch a counterparty contract."""

        return dict(self._request("PATCH", f"/contracts/{contract_id}", json=payload))

    def get_counterparty_account_card(
        self,
        counterparty_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
        debt_type: str | None = None,
        contract_id: int | None = None,
    ) -> dict[str, Any]:
        """Return account-card movements for one counterparty."""

        return dict(
            self._request(
                "GET",
                self._path_with_params(
                    f"/counterparties/{counterparty_id}/account-card",
                    {"date_from": date_from, "date_to": date_to, "debt_type": debt_type, "contract_id": contract_id},
                ),
            )
        )

    def get_counterparty_reconciliation(
        self,
        counterparty_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
        contract_id: int | None = None,
    ) -> dict[str, Any]:
        """Return reconciliation statement data for one counterparty."""

        return dict(
            self._request(
                "GET",
                self._path_with_params(
                    f"/counterparties/{counterparty_id}/reconciliation",
                    {"date_from": date_from, "date_to": date_to, "contract_id": contract_id},
                ),
            )
        )

    def get_price_lists(self) -> list[dict[str, Any]]:
        """Return price lists."""

        return list(self._request("GET", "/price-lists"))

    def create_price_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a price list."""

        return dict(self._request("POST", "/price-lists", json=payload))

    def add_price_list_item(self, price_list_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Add a versioned price-list item."""

        return dict(self._request("POST", f"/price-lists/{price_list_id}/items", json=payload))

    def export_price_list(self, price_list_id: int) -> dict[str, Any]:
        """Export a price list as rows and base64 XLSX data."""

        return dict(self._request("GET", f"/price-lists/{price_list_id}/export"))

    def import_price_list(self, price_list_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Import price rows into a price list."""

        return dict(self._request("POST", f"/price-lists/{price_list_id}/import", json=payload))

    def get_promotions(self, active_only: bool = False) -> list[dict[str, Any]]:
        """Return sale promotion rules."""

        return list(self._request("GET", self._path_with_params("/promotions", {"active_only": str(active_only).lower()})))

    def create_promotion(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a sale promotion rule."""

        return dict(self._request("POST", "/promotions", json=payload))

    def update_promotion(self, promotion_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Patch a sale promotion rule."""

        return dict(self._request("PATCH", f"/promotions/{promotion_id}", json=payload))

    def get_loyalty_settings(self) -> dict[str, Any]:
        """Return global loyalty settings."""

        return dict(self._request("GET", "/loyalty-settings"))

    def update_loyalty_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Update global loyalty settings."""

        return dict(self._request("PUT", "/loyalty-settings", json=payload))

    def get_loyalty_cards(self, search: str | None = None, active_only: bool = False) -> list[dict[str, Any]]:
        """Return loyalty cards."""

        return list(self._request("GET", self._path_with_params("/loyalty-cards", {"search": search, "active_only": str(active_only).lower()})))

    def create_loyalty_card(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a loyalty card."""

        return dict(self._request("POST", "/loyalty-cards", json=payload))

    def update_loyalty_card(self, card_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Patch loyalty card metadata."""

        return dict(self._request("PATCH", f"/loyalty-cards/{card_id}", json=payload))

    def get_loyalty_transactions(self, card_id: int) -> list[dict[str, Any]]:
        """Return loyalty movements for one card."""

        return list(self._request("GET", f"/loyalty-cards/{card_id}/transactions"))

    def adjust_loyalty_card(self, card_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Post a manual loyalty-card adjustment."""

        return dict(self._request("POST", f"/loyalty-cards/{card_id}/adjust", json=payload))

    def get_current_price(self, product_id: int, price_list_id: int | None = None) -> dict[str, Any]:
        """Return the current product price."""

        return dict(
            self._request(
                "GET",
                self._path_with_params("/prices/current", {"product_id": product_id, "price_list_id": price_list_id}),
            )
        )

    def get_purchase_orders(self) -> list[dict[str, Any]]:
        """Return purchase orders."""

        return list(self._request("GET", "/purchase-orders"))

    def create_purchase_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a purchase order."""

        return dict(self._request("POST", "/purchase-orders", json=payload))

    def update_purchase_order(self, order_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Update a purchase order."""

        return dict(self._request("PUT", f"/purchase-orders/{order_id}", json=payload))

    def send_purchase_order(self, order_id: int) -> dict[str, Any]:
        """Mark a purchase order as sent."""

        return dict(self._request("POST", f"/purchase-orders/{order_id}/send"))

    def cancel_purchase_order(self, order_id: int) -> dict[str, Any]:
        """Cancel a purchase order."""

        return dict(self._request("POST", f"/purchase-orders/{order_id}/cancel"))

    def get_purchase_invoices(self) -> list[dict[str, Any]]:
        """Return purchase invoices."""

        return list(self._request("GET", "/purchase-invoices"))

    def create_purchase_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a purchase invoice."""

        return dict(self._request("POST", "/purchase-invoices", json=payload))

    def create_purchase_return(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a supplier return invoice."""

        return dict(self._request("POST", "/purchase-invoices/return", json=payload))

    def post_purchase_invoice(self, invoice_id: int) -> dict[str, Any]:
        """Post a purchase invoice."""

        return dict(self._request("POST", f"/purchase-invoices/{invoice_id}/post"))

    def cancel_purchase_invoice(self, invoice_id: int) -> dict[str, Any]:
        """Cancel a purchase invoice."""

        return dict(self._request("POST", f"/purchase-invoices/{invoice_id}/cancel"))

    def create_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a payment document."""

        return dict(self._request("POST", "/payments", json=payload))

    def get_cash_registers(self) -> list[dict[str, Any]]:
        """Return cash registers."""

        return list(self._request("GET", "/cash-registers"))

    def create_cash_register(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a cash register."""

        return dict(self._request("POST", "/cash-registers", json=payload))

    def get_cash_shifts(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return cash shifts."""

        return list(self._request("GET", self._path_with_params("/cash-shifts", {"status": status})))

    def open_cash_shift(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Open a cash shift."""

        return dict(self._request("POST", "/cash-shifts/open", json=payload))

    def close_cash_shift(self, shift_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Close a cash shift."""

        return dict(self._request("POST", f"/cash-shifts/{shift_id}/close", json=payload))

    def create_cash_operation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a cash operation."""

        return dict(self._request("POST", "/cash-operations", json=payload))

    def get_sales(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return sales."""

        return list(self._request("GET", self._path_with_params("/sales", {"status": status})))

    def create_sale(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a sale."""

        return dict(self._request("POST", "/sales", json=payload))

    def post_sale(self, sale_id: int) -> dict[str, Any]:
        """Post a sale."""

        return dict(self._request("POST", f"/sales/{sale_id}/post"))

    def cancel_sale(self, sale_id: int) -> dict[str, Any]:
        """Cancel a sale."""

        return dict(self._request("POST", f"/sales/{sale_id}/cancel"))

    def get_sale_returns(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return sale returns."""

        return list(self._request("GET", self._path_with_params("/sale-returns", {"status": status})))

    def create_sale_return(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a sale return."""

        return dict(self._request("POST", "/sale-returns", json=payload))

    def post_sale_return(self, sale_return_id: int) -> dict[str, Any]:
        """Post a sale return."""

        return dict(self._request("POST", f"/sale-returns/{sale_return_id}/post"))

    def cancel_sale_return(self, sale_return_id: int) -> dict[str, Any]:
        """Cancel a sale return."""

        return dict(self._request("POST", f"/sale-returns/{sale_return_id}/cancel"))

    def get_dashboard_report(self) -> dict[str, Any]:
        """Return dashboard report totals."""

        return dict(self._request("GET", "/reports/dashboard"))

    def get_stock_report(self) -> list[dict[str, Any]]:
        """Return stock report rows."""

        return list(self._request("GET", "/reports/stock"))

    def get_sales_report(self) -> dict[str, Any]:
        """Return sales report totals."""

        return dict(self._request("GET", "/reports/sales"))

    def get_purchases_report(self) -> dict[str, Any]:
        """Return purchases report totals."""

        return dict(self._request("GET", "/reports/purchases"))

    def get_debts_report(self) -> dict[str, Any]:
        """Return debt report totals."""

        return dict(self._request("GET", "/reports/debts"))

    def get_cash_flow_report(self) -> dict[str, Any]:
        """Return cash-flow report totals."""

        return dict(self._request("GET", "/reports/cash-flow"))

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

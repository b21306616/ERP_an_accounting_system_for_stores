"""Application-wide constants kept in one place."""

from __future__ import annotations


# A human-readable application name used by windows, folders, and API status.
APP_NAME = "ERP Accounting Server"

# Local application data folder name for saved configuration and secrets.
APP_DATA_DIR_NAME = "ERPAccountingServer"

# Config file name stored inside the local app data directory.
CONFIG_FILE_NAME = "config.json"

# Fixed privileged account used to administer the whole program.
SUPER_ADMIN_USERNAME = "super_admin"
SUPER_ADMIN_FULL_NAME = "Super Admin"
SUPER_ADMIN_ROLE = "Super Admin"

# Built-in roles from the Russian business definition supplied by the user.
BUILTIN_ROLES = (SUPER_ADMIN_ROLE, "Accountant", "Manager", "Cashier", "Auditor")

# Built-in action permissions used by the first strict /api/v1 contract layer.
BUILTIN_PERMISSIONS = (
    "admin.view",
    "admin.manage_users",
    "admin.manage_roles",
    "settings.view",
    "settings.edit",
    "audit.view",
    "goods.view",
    "goods.create",
    "goods.edit",
    "goods.delete",
    "warehouse.view",
    "warehouse.create",
    "warehouse.edit",
    "warehouse.post",
    "warehouse.transfer_create",
    "warehouse.transfer_send",
    "warehouse.transfer_receive",
    "warehouse.writeoff_create",
    "warehouse.writeoff_post",
    "warehouse.writeoff_cancel",
    "warehouse.inventory_create",
    "warehouse.inventory_post",
    "warehouse.inventory_cancel",
    "warehouse.settings",
    "warehouse.export",
    "purchase.view",
    "purchase.create",
    "purchase.post",
    "purchase.order_create",
    "purchase.order_edit",
    "purchase.order_cancel",
    "purchase.order_print",
    "purchase.invoice_create",
    "purchase.invoice_edit",
    "purchase.cancel",
    "purchase.return",
    "purchase.print",
    "purchase.export",
    "purchase.price_update",
    "pricing.view",
    "pricing.edit",
    "pricing.price_list_create",
    "pricing.price_list_edit",
    "pricing.price_list_copy",
    "pricing.price_list_import",
    "pricing.price_list_export",
    "pricing.promo_manage",
    "pricing.loyalty_manage",
    "pricing.loyalty_adjust",
    "sale.view",
    "sale.create",
    "sale.edit",
    "sale.post",
    "sale.cancel",
    "sale.print",
    "sale.export",
    "sale.discount",
    "sale.price_override",
    "sale.gift_add",
    "sale.wholesale",
    "sale_return.create",
    "sale_return.post",
    "sale_return.cancel",
    "sale_return.print",
    "cashier.view",
    "cashier.register_manage",
    "cashier.shift",
    "cashier.shift_open",
    "cashier.shift_close",
    "cashier.cash_operation",
    "cashier.print",
    "counterparty.view",
    "counterparty.create",
    "counterparty.edit",
    "counterparty.delete",
    "counterparty.category_manage",
    "counterparty.debt_view",
    "counterparty.payment_create",
    "counterparty.payment_cancel",
    "counterparty.reconciliation",
    "counterparty.loyalty_manage",
    "counterparty.loyalty_adjust",
    "counterparty.export",
    "reports.view",
    "reports.stock",
    "reports.sales",
    "reports.purchases",
    "reports.finance",
    "reports.export",
    "reports.filters_manage",
)

# Default permission matrix for the fixed roles. More granular permissions can
# later be exposed through the role administration screens.
DEFAULT_ROLE_PERMISSIONS = {
    SUPER_ADMIN_ROLE: set(BUILTIN_PERMISSIONS),
    "Accountant": {
        "settings.view",
        "goods.view",
        "warehouse.view",
        "warehouse.export",
        "purchase.view",
        "purchase.create",
        "purchase.post",
        "purchase.invoice_create",
        "purchase.invoice_edit",
        "purchase.cancel",
        "purchase.return",
        "purchase.export",
        "purchase.price_update",
        "pricing.view",
        "pricing.edit",
        "pricing.price_list_create",
        "pricing.price_list_edit",
        "pricing.price_list_export",
        "sale.view",
        "sale.export",
        "counterparty.view",
        "counterparty.edit",
        "counterparty.debt_view",
        "counterparty.payment_create",
        "counterparty.reconciliation",
        "counterparty.export",
        "reports.view",
        "reports.stock",
        "reports.sales",
        "reports.purchases",
        "reports.finance",
        "reports.export",
    },
    "Manager": {
        "goods.view",
        "warehouse.view",
        "warehouse.transfer_create",
        "warehouse.transfer_send",
        "warehouse.transfer_receive",
        "warehouse.writeoff_create",
        "warehouse.writeoff_post",
        "warehouse.inventory_create",
        "purchase.view",
        "purchase.create",
        "purchase.post",
        "purchase.invoice_create",
        "purchase.invoice_edit",
        "pricing.view",
        "pricing.edit",
        "pricing.price_list_create",
        "pricing.price_list_edit",
        "sale.view",
        "sale.create",
        "sale.edit",
        "sale.post",
        "sale.cancel",
        "sale.discount",
        "sale.wholesale",
        "cashier.view",
        "cashier.register_manage",
        "cashier.shift_open",
        "cashier.shift_close",
        "cashier.cash_operation",
        "counterparty.view",
        "counterparty.create",
        "counterparty.edit",
        "counterparty.debt_view",
        "counterparty.payment_create",
        "reports.view",
        "reports.stock",
        "reports.sales",
        "reports.purchases",
        "reports.finance",
    },
    "Cashier": {
        "goods.view",
        "pricing.view",
        "sale.view",
        "sale.create",
        "sale.post",
        "sale.cancel",
        "sale.print",
        "sale.discount",
        "cashier.view",
        "cashier.shift",
        "cashier.shift_open",
        "cashier.shift_close",
        "cashier.cash_operation",
        "cashier.print",
    },
    "Auditor": {
        "goods.view",
        "warehouse.view",
        "warehouse.inventory_create",
        "warehouse.inventory_post",
        "warehouse.inventory_cancel",
        "warehouse.export",
        "purchase.view",
        "counterparty.view",
        "counterparty.debt_view",
        "reports.view",
        "reports.stock",
        "reports.sales",
        "reports.purchases",
        "reports.finance",
        "reports.export",
    },
}

# The default MSSQL ODBC driver installed on the user's machine.
DEFAULT_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

# Default API host listens on every network interface for LAN clients.
DEFAULT_API_HOST = "0.0.0.0"

# Default FastAPI port for the local network server.
DEFAULT_API_PORT = 8000

# JWT-compatible bearer token algorithm used by the internal token helper.
TOKEN_ALGORITHM = "HS256"

# Token lifetime chosen for a LAN desktop environment.
ACCESS_TOKEN_EXPIRE_MINUTES = 8 * 60

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
    "purchase.view",
    "purchase.create",
    "purchase.post",
    "pricing.view",
    "pricing.edit",
    "sale.view",
    "sale.create",
    "sale.post",
    "sale.cancel",
    "sale.price_override",
    "cashier.view",
    "cashier.shift",
    "cashier.print",
    "counterparty.view",
    "counterparty.edit",
    "reports.view",
    "reports.export",
)

# Default permission matrix for the fixed roles. More granular permissions can
# later be exposed through the role administration screens.
DEFAULT_ROLE_PERMISSIONS = {
    SUPER_ADMIN_ROLE: set(BUILTIN_PERMISSIONS),
    "Accountant": {
        "settings.view",
        "goods.view",
        "warehouse.view",
        "purchase.view",
        "pricing.view",
        "sale.view",
        "counterparty.view",
        "counterparty.edit",
        "reports.view",
        "reports.export",
    },
    "Manager": {
        "goods.view",
        "warehouse.view",
        "purchase.view",
        "pricing.view",
        "sale.view",
        "sale.create",
        "sale.post",
        "counterparty.view",
        "counterparty.edit",
        "reports.view",
    },
    "Cashier": {
        "goods.view",
        "pricing.view",
        "sale.view",
        "sale.create",
        "sale.post",
        "cashier.view",
        "cashier.shift",
        "cashier.print",
    },
    "Auditor": {
        "goods.view",
        "warehouse.view",
        "reports.view",
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

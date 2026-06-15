"""LAN smoke check for an installed or source-run ERP user client."""

from __future__ import annotations

import argparse
import getpass
import sys

from user_app.api.client import ApiClient, ApiClientError


def parse_args() -> argparse.Namespace:
    """Return CLI arguments for the LAN smoke check."""

    parser = argparse.ArgumentParser(description="Check a LAN ERP server URL from an endpoint client machine.")
    parser.add_argument("--server", required=True, help="Server URL, for example http://192.168.1.10:8000 or 192.168.1.10:8000")
    parser.add_argument("--username", default="super_admin", help="API username to use for the smoke check")
    parser.add_argument("--password", help="API password. If omitted, a hidden prompt is shown.")
    return parser.parse_args()


def main() -> int:
    """Run a login, status, reference, and dashboard smoke check."""

    args = parse_args()
    password = args.password or getpass.getpass("Password: ")
    client = ApiClient(args.server, timeout_seconds=8)
    try:
        user = client.login(args.username, password, client_name="LAN smoke", client_version="stage7")
        status = client.get_status()
        currencies = client.get_currencies()
        dashboard = client.get_dashboard_report()
    except ApiClientError as exc:
        print(f"[FAIL] {exc}")
        return 1
    finally:
        try:
            client.logout()
        except Exception:
            pass

    print(f"[OK] Connected to {client.base_url}")
    print(f"[OK] Authenticated as {user.username} ({user.role_name})")
    print(f"[OK] Status: {status.get('status', 'unknown')}")
    print(f"[OK] Currencies visible: {len(currencies)}")
    print(f"[OK] Dashboard keys: {', '.join(sorted(dashboard.keys()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

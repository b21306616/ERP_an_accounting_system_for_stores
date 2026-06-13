"""Audit helpers for API v1 mutations."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from server_app.core.security import hash_session_token
from server_app.db.models import AuditLog, UserSession


_ACTION_SEGMENTS = {
    "post": "post",
    "cancel": "cancel",
    "send": "send",
    "receive": "receive",
    "reject": "reject",
    "open": "open",
    "close": "close",
    "deactivate": "deactivate",
    "logout": "logout",
}
_METHOD_ACTIONS = {
    "POST": "create",
    "PUT": "edit",
    "PATCH": "edit",
    "DELETE": "delete",
}
_MODULE_SEGMENTS = {
    "auth": "auth",
    "users": "users",
    "roles": "users",
    "permissions": "users",
    "workplaces": "settings",
    "settings": "settings",
    "audit-log": "audit",
    "product-groups": "goods",
    "unit-of-measures": "goods",
    "products": "goods",
    "services": "goods",
    "expense-categories": "goods",
    "warehouses": "warehouse",
    "stock": "warehouse",
    "stock-transfers": "warehouse",
    "stock-writeoffs": "warehouse",
    "inventories": "warehouse",
    "currencies": "pricing",
    "price-lists": "pricing",
    "prices": "pricing",
    "promotions": "pricing",
    "loyalty-settings": "pricing",
    "loyalty-cards": "loyalty",
    "counterparty-categories": "counterparty",
    "counterparties": "counterparty",
    "debt-ledger": "counterparty",
    "payments": "counterparty",
    "purchase-orders": "purchase",
    "purchase-invoices": "purchase",
    "cash-registers": "cashier",
    "cash-shifts": "cashier",
    "cash-operations": "cashier",
    "sales": "sale",
    "sale-returns": "sale_return",
    "reports": "reports",
    "system": "system",
}
_SKIP_PREFIXES = ("/api/v1/auth/login", "/api/v1/auth/verify-admin-password")


def _segments(path: str) -> list[str]:
    """Return meaningful API v1 path segments."""

    parts = [part for part in path.strip("/").split("/") if part]
    return parts[2:] if len(parts) >= 2 and parts[:2] == ["api", "v1"] else parts


def infer_audit_action(method: str, path: str) -> str:
    """Infer an audit action from HTTP method and route shape."""

    segments = _segments(path)
    for segment in reversed(segments):
        if segment in _ACTION_SEGMENTS:
            return _ACTION_SEGMENTS[segment]
    return _METHOD_ACTIONS.get(method.upper(), method.lower())


def infer_audit_module(path: str) -> str | None:
    """Infer the business module from the first API v1 route segment."""

    segments = _segments(path)
    return _MODULE_SEGMENTS.get(segments[0]) if segments else None


def infer_entity_id(path: str) -> str | None:
    """Return the first numeric route segment as the entity id."""

    for segment in _segments(path):
        if segment.isdigit():
            return segment
    return None


def _user_id_for_session_token(session: Session, session_token: str | None) -> int | None:
    """Resolve an API v1 session token to a user id when possible."""

    if not session_token:
        return None
    row = session.query(UserSession).filter(UserSession.token_hash == hash_session_token(session_token)).one_or_none()
    return row.user_id if row is not None else None


def log_api_mutation(
    session_factory: sessionmaker[Session],
    *,
    method: str,
    path: str,
    status_code: int,
    session_token: str | None,
    ip_address: str | None,
) -> None:
    """Append one audit row for a successful mutating API v1 request.

    Audit failures must never break the original business request, so errors are
    intentionally swallowed after rolling back the audit session.
    """

    if not path.startswith("/api/v1/") or any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return

    with session_factory() as session:
        try:
            details: dict[str, Any] = {"method": method.upper(), "path": path, "status_code": status_code}
            row = AuditLog(
                user_id=_user_id_for_session_token(session, session_token),
                action=infer_audit_action(method, path),
                module=infer_audit_module(path),
                entity_name=_segments(path)[0] if _segments(path) else None,
                entity_id=infer_entity_id(path),
                details=json.dumps(details, ensure_ascii=False, separators=(",", ":")),
                ip_address=ip_address,
            )
            session.add(row)
            session.commit()
        except Exception:
            session.rollback()

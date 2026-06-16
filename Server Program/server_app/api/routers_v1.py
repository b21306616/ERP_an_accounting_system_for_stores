"""Strict documented API v1 routes for endpoint clients."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session, selectinload

from server_app.api.dependencies import get_db
from server_app.core.constants import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    APP_NAME,
    BUILTIN_ROLES,
    SUPER_ADMIN_FULL_NAME,
    SUPER_ADMIN_ROLE,
    SUPER_ADMIN_USERNAME,
)
from server_app.core.security import generate_session_token, hash_password, hash_session_token, verify_password
from server_app.db.models import (
    AuditLog,
    Permission,
    Role,
    RolePermission,
    Setting,
    User,
    UserSession,
    Workplace,
)
from server_app.schemas.api_v1 import (
    V1AdminPasswordRequest,
    V1LoginRequest,
    V1RoleCreate,
    V1RoleUpdate,
    V1SettingsUpdate,
    V1UserCreate,
    V1UserUpdate,
    V1WorkplaceCreate,
)
from server_app.services.auth import authenticate_user, permission_codes_for_user, role_name_for_user


router = APIRouter(prefix="/api/v1", tags=["api-v1"])


def success_response(
    data: Any = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a standard successful API v1 envelope."""

    return {"success": True, "data": data, "error": None, "meta": meta}


def error_detail(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a structured error object for HTTPException.detail."""

    return {"code": code, "message": message, "details": details or {}}


def _now() -> datetime:
    """Return timezone-aware UTC now."""

    return datetime.now(timezone.utc)


def _is_expired(expires_at: datetime) -> bool:
    """Return whether an expiry timestamp is in the past."""

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= _now()


def _permissions_for_role(role: Role | None) -> list[str]:
    """Return sorted permission codes for a role."""

    if role is None:
        return []
    return sorted(
        {
            role_permission.permission.code
            for role_permission in role.role_permissions
            if role_permission.permission is not None
        }
    )


def _user_payload(user: User) -> dict[str, Any]:
    """Return a client-facing user payload."""

    workplace = user.workplace
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role_id": user.role_id,
        "role_name": role_name_for_user(user),
        "workplace_id": user.workplace_id,
        "workplace_type": workplace.workplace_type if workplace else None,
        "cash_register_id": None,
        "permissions": permission_codes_for_user(user),
        "is_active": user.is_active,
    }


def _role_payload(role: Role) -> dict[str, Any]:
    """Return a client-facing role payload."""

    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "permissions": _permissions_for_role(role),
    }


def _permission_payload(permission: Permission) -> dict[str, Any]:
    """Return a client-facing permission payload."""

    return {
        "id": permission.id,
        "code": permission.code,
        "module": permission.module,
        "description": permission.description,
    }


def _permission_rows_for_codes(session: Session, permission_codes: list[str]) -> list[Permission]:
    """Return permission rows for the supplied codes or raise a v1 error."""

    clean_codes = sorted({code.strip() for code in permission_codes if code.strip()})
    if not clean_codes:
        return []
    rows = session.query(Permission).filter(Permission.code.in_(clean_codes)).all()
    found = {row.code for row in rows}
    missing = [code for code in clean_codes if code not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("UNKNOWN_PERMISSION", "Unknown permission code.", {"permissions": missing}),
        )
    return sorted(rows, key=lambda row: row.code)


def _replace_role_permissions(session: Session, role: Role, permission_codes: list[str]) -> None:
    """Replace a role's permission assignments."""

    role.role_permissions.clear()
    session.flush()
    for permission in _permission_rows_for_codes(session, permission_codes):
        role.role_permissions.append(RolePermission(permission=permission))


def _workplace_payload(workplace: Workplace) -> dict[str, Any]:
    """Return a client-facing workplace payload."""

    return {
        "id": workplace.id,
        "code": workplace.code,
        "name": workplace.name,
        "workplace_type": workplace.workplace_type,
        "is_active": workplace.is_active,
    }


def _audit_payload(row: AuditLog) -> dict[str, Any]:
    """Return a client-facing audit-log payload."""

    return {
        "id": row.id,
        "user_id": row.user_id,
        "action": row.action,
        "module": row.module,
        "entity_name": row.entity_name,
        "entity_id": row.entity_id,
        "details": row.details,
        "old_values": row.old_values,
        "new_values": row.new_values,
        "ip_address": row.ip_address,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _get_role(session: Session, role_name: str) -> Role:
    """Return a role by name or raise a client-contract error."""

    role = session.query(Role).filter(Role.name == role_name).one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("UNKNOWN_ROLE", f"Unknown role: {role_name}"),
        )
    return role


def _get_workplace(session: Session, workplace_id: int | None) -> Workplace | None:
    """Return a workplace when an id is supplied."""

    if workplace_id is None:
        return None
    workplace = session.get(Workplace, workplace_id)
    if workplace is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("UNKNOWN_WORKPLACE", f"Unknown workplace: {workplace_id}"),
        )
    return workplace


def _is_super_admin_username(username: str) -> bool:
    """Return whether a username targets the fixed Super Admin account."""

    return username.casefold() == SUPER_ADMIN_USERNAME.casefold()


def get_current_v1_session(
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    session: Session = Depends(get_db),
) -> UserSession:
    """Authenticate a client request using the documented session token."""

    if not x_session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("UNAUTHORIZED", "Missing X-Session-Token header."),
        )

    token_hash = hash_session_token(x_session_token)
    user_session = (
        session.query(UserSession)
        .options(
            selectinload(UserSession.user)
            .selectinload(User.role)
            .selectinload(Role.role_permissions)
            .selectinload(RolePermission.permission),
            selectinload(UserSession.user).selectinload(User.workplace),
        )
        .filter(UserSession.token_hash == token_hash)
        .one_or_none()
    )
    if (
        user_session is None
        or user_session.revoked_at is not None
        or _is_expired(user_session.expires_at)
        or not user_session.user.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("UNAUTHORIZED", "Session token is invalid or expired."),
        )
    return user_session


def get_current_v1_user(user_session: UserSession = Depends(get_current_v1_session)) -> User:
    """Return the authenticated API v1 user."""

    return user_session.user


def require_v1_super_admin(current_user: User = Depends(get_current_v1_user)) -> User:
    """Require the fixed Super Admin role for API v1 admin operations."""

    if role_name_for_user(current_user) != SUPER_ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail("FORBIDDEN", "Super Admin role is required."),
        )
    return current_user


def require_v1_permission(permission_code: str):
    """Return a dependency that requires one permission code."""

    def dependency(current_user: User = Depends(get_current_v1_user)) -> User:
        if permission_code not in permission_codes_for_user(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_detail("FORBIDDEN", f"Permission is required: {permission_code}"),
            )
        return current_user

    return dependency


@router.post("/auth/login")
def login(payload: V1LoginRequest, request: Request, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Open a documented client session."""

    user = authenticate_user(session, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("INVALID_CREDENTIALS", "Invalid username or password."),
        )

    token = generate_session_token()
    expires_at = _now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    user_session = UserSession(
        user=user,
        token_hash=hash_session_token(token),
        expires_at=expires_at,
        client_name=payload.client_name,
        client_version=payload.client_version,
        ip_address=request.client.host if request.client else None,
    )
    session.add(user_session)
    session.commit()
    session.refresh(user)

    return success_response(
        {
            "session_token": token,
            "expires_at": expires_at.isoformat(),
            "user": _user_payload(user),
        }
    )


@router.post("/auth/logout")
def logout(
    user_session: UserSession = Depends(get_current_v1_session),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Close the current documented client session."""

    user_session.revoked_at = _now()
    session.commit()
    return success_response(None)


@router.get("/auth/me")
def read_me(current_user: User = Depends(get_current_v1_user)) -> dict[str, Any]:
    """Return the current authenticated client user."""

    return success_response(_user_payload(current_user))


@router.post("/auth/verify-admin-password")
def verify_admin_password(
    payload: V1AdminPasswordRequest,
    _: User = Depends(get_current_v1_user),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Verify the fixed Super Admin password for override workflows."""

    super_admin = session.query(User).filter(User.username == SUPER_ADMIN_USERNAME).one_or_none()
    verified = bool(super_admin and verify_password(payload.password, super_admin.password_hash))
    return success_response({"verified": verified})


@router.get("/system/status")
def system_status(current_user: User = Depends(get_current_v1_user)) -> dict[str, Any]:
    """Return server status for the endpoint client."""

    return success_response(
        {
            "application": APP_NAME,
            "status": "running",
            "server_time": _now().isoformat(),
            "current_user_id": current_user.id,
            "current_username": current_user.username,
        }
    )


@router.get("/roles")
def list_roles(_: User = Depends(require_v1_super_admin), session: Session = Depends(get_db)) -> dict[str, Any]:
    """List roles with their permission codes."""

    roles = (
        session.query(Role)
        .options(selectinload(Role.role_permissions).selectinload(RolePermission.permission))
        .order_by(Role.name)
        .all()
    )
    return success_response([_role_payload(role) for role in roles])


@router.get("/permissions")
def list_permissions(_: User = Depends(require_v1_super_admin), session: Session = Depends(get_db)) -> dict[str, Any]:
    """List all known permission actions."""

    permissions = session.query(Permission).order_by(Permission.module, Permission.code).all()
    return success_response([_permission_payload(permission) for permission in permissions])


@router.post("/roles", status_code=status.HTTP_201_CREATED)
def create_role(
    payload: V1RoleCreate,
    _: User = Depends(require_v1_super_admin),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a custom role with explicit permissions."""

    role_name = payload.name.strip()
    if role_name in BUILTIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("BUILTIN_ROLE", "Built-in roles already exist and cannot be recreated."),
        )
    if session.query(Role).filter(Role.name == role_name).one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail("DUPLICATE_ROLE", "Role name already exists."),
        )
    role = Role(name=role_name, description=payload.description)
    session.add(role)
    session.flush()
    _replace_role_permissions(session, role, payload.permissions)
    session.commit()
    session.refresh(role)
    return success_response(_role_payload(role))


@router.patch("/roles/{role_id}")
def update_role(
    role_id: int,
    payload: V1RoleUpdate,
    _: User = Depends(require_v1_super_admin),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a role description and permission assignments."""

    role = (
        session.query(Role)
        .options(selectinload(Role.role_permissions).selectinload(RolePermission.permission))
        .filter(Role.id == role_id)
        .one_or_none()
    )
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("NOT_FOUND", "Role not found."),
        )
    if payload.description is not None:
        role.description = payload.description
    if payload.permissions is not None:
        _replace_role_permissions(session, role, payload.permissions)
    session.commit()
    session.refresh(role)
    return success_response(_role_payload(role))


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: int,
    _: User = Depends(require_v1_super_admin),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Delete an unused custom role."""

    role = session.get(Role, role_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("NOT_FOUND", "Role not found."),
        )
    if role.name in BUILTIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("BUILTIN_ROLE", "Built-in roles cannot be deleted."),
        )
    assigned_users = session.query(User).filter(User.role_id == role.id).count()
    if assigned_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("ROLE_IN_USE", "Role is assigned to users and cannot be deleted."),
        )
    session.delete(role)
    session.commit()
    return success_response({"deleted": True, "id": role_id})


@router.get("/users")
def list_users(_: User = Depends(require_v1_super_admin), session: Session = Depends(get_db)) -> dict[str, Any]:
    """List application users."""

    users = (
        session.query(User)
        .options(
            selectinload(User.role).selectinload(Role.role_permissions).selectinload(RolePermission.permission),
            selectinload(User.workplace),
        )
        .order_by(User.username)
        .all()
    )
    return success_response([_user_payload(user) for user in users])


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: V1UserCreate,
    _: User = Depends(require_v1_super_admin),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a user for endpoint access."""

    if _is_super_admin_username(payload.username) or payload.role_name == SUPER_ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("RESERVED_SUPER_ADMIN", "Super Admin is reserved for the fixed account."),
        )
    if session.query(User).filter(User.username == payload.username).one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail("DUPLICATE_USERNAME", "Username already exists."),
        )

    role = _get_role(session, payload.role_name)
    workplace = _get_workplace(session, payload.workplace_id)
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=role,
        workplace=workplace,
        is_active=payload.is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return success_response(_user_payload(user))


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    payload: V1UserUpdate,
    _: User = Depends(require_v1_super_admin),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a user through the documented contract."""

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("NOT_FOUND", "User not found."),
        )

    if _is_super_admin_username(user.username):
        if (
            payload.full_name is not None
            or payload.role_name is not None
            or payload.workplace_id is not None
            or payload.is_active is not None
            or payload.password is None
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail("RESERVED_SUPER_ADMIN", "Only the Super Admin password can be changed."),
            )
        if not payload.current_password or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_detail("INVALID_ADMIN_PASSWORD", "Current Super Admin password is incorrect."),
            )
        user.full_name = SUPER_ADMIN_FULL_NAME
        user.password_hash = hash_password(payload.password)
        user.role = _get_role(session, SUPER_ADMIN_ROLE)
        user.workplace = None
        user.is_active = True
    else:
        if payload.role_name == SUPER_ADMIN_ROLE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail("RESERVED_SUPER_ADMIN", "Super Admin role is reserved for the fixed account."),
            )
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.password is not None:
            user.password_hash = hash_password(payload.password)
        if payload.role_name is not None:
            user.role = _get_role(session, payload.role_name)
        if payload.workplace_id is not None:
            user.workplace = _get_workplace(session, payload.workplace_id)
        if payload.is_active is not None:
            user.is_active = payload.is_active

    session.commit()
    session.refresh(user)
    return success_response(_user_payload(user))


@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    _: User = Depends(require_v1_super_admin),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Deactivate a user without deleting audit history."""

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("NOT_FOUND", "User not found."),
        )
    if _is_super_admin_username(user.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("RESERVED_SUPER_ADMIN", "Super Admin cannot be deactivated."),
        )
    user.is_active = False
    session.commit()
    return success_response(_user_payload(user))


@router.get("/workplaces")
def list_workplaces(_: User = Depends(require_v1_super_admin), session: Session = Depends(get_db)) -> dict[str, Any]:
    """List endpoint workplaces."""

    workplaces = session.query(Workplace).order_by(Workplace.code).all()
    return success_response([_workplace_payload(workplace) for workplace in workplaces])


@router.post("/workplaces", status_code=status.HTTP_201_CREATED)
def create_workplace(
    payload: V1WorkplaceCreate,
    _: User = Depends(require_v1_super_admin),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create an endpoint workplace."""

    if session.query(Workplace).filter(Workplace.code == payload.code).one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail("DUPLICATE_WORKPLACE", "Workplace code already exists."),
        )
    workplace = Workplace(**payload.model_dump())
    session.add(workplace)
    session.commit()
    session.refresh(workplace)
    return success_response(_workplace_payload(workplace))


@router.get("/settings")
def get_settings(_: User = Depends(require_v1_super_admin), session: Session = Depends(get_db)) -> dict[str, Any]:
    """Return settings as a key/value object."""

    values: dict[str, Any] = {}
    for setting in session.query(Setting).order_by(Setting.key).all():
        try:
            values[setting.key] = json.loads(setting.value_json)
        except json.JSONDecodeError:
            values[setting.key] = setting.value_json
    return success_response(values)


@router.put("/settings")
def update_settings(
    payload: V1SettingsUpdate,
    _: User = Depends(require_v1_super_admin),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update settings by key."""

    for key, value in payload.values.items():
        setting = session.query(Setting).filter(Setting.key == key).one_or_none()
        value_json = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if setting is None:
            session.add(Setting(key=key, value_json=value_json))
        else:
            setting.value_json = value_json
    session.commit()
    return get_settings(_, session)


@router.get("/audit-log")
def list_audit_log(_: User = Depends(require_v1_super_admin), session: Session = Depends(get_db)) -> dict[str, Any]:
    """List recent audit-log rows."""

    rows = session.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return success_response([_audit_payload(row) for row in rows])

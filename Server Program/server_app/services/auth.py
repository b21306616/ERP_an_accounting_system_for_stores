"""Authentication and role-check service functions."""

from __future__ import annotations

from sqlalchemy.orm import Session

from server_app.core.security import verify_password
from server_app.db.models import Role, User


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    """Return an active user when the username/password pair is valid."""

    user = session.query(User).join(Role).filter(User.username == username).one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def role_name_for_user(user: User) -> str:
    """Return the user's role name without leaking ORM relationship details."""

    return user.role.name if user.role else ""


def user_has_role(user: User, allowed_roles: set[str]) -> bool:
    """Return whether a user has one of the allowed role names."""

    return role_name_for_user(user) in allowed_roles


def permission_codes_for_user(user: User) -> list[str]:
    """Return sorted permission codes assigned through the user's role."""

    if user.role is None:
        return []

    codes = [
        role_permission.permission.code
        for role_permission in user.role.role_permissions
        if role_permission.permission is not None
    ]
    return sorted(set(codes))

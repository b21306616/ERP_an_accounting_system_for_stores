"""Owner-only user administration API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from server_app.api.dependencies import get_db, require_owner
from server_app.core.security import hash_password
from server_app.db.models import Role, User
from server_app.schemas.users import UserCreate, UserRead, UserUpdate
from server_app.services.auth import role_name_for_user


router = APIRouter(prefix="/users", tags=["users"])


def _to_user_read(user: User) -> UserRead:
    """Convert a SQLAlchemy User into an API response schema."""

    return UserRead(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role_name=role_name_for_user(user),
        is_active=user.is_active,
    )


def _get_role(session: Session, role_name: str) -> Role:
    """Look up a role or raise an HTTP 400 response."""

    role = session.query(Role).filter(Role.name == role_name).one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown role: {role_name}",
        )
    return role


@router.get("", response_model=list[UserRead])
def list_users(
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> list[UserRead]:
    """List all users."""

    users = session.query(User).join(Role).order_by(User.username).all()
    return [_to_user_read(user) for user in users]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> UserRead:
    """Create a user with a built-in role."""

    existing = session.query(User).filter(User.username == payload.username).one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists.",
        )

    role = _get_role(session, payload.role_name)
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=payload.is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _to_user_read(user)


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> UserRead:
    """Return one user by id."""

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return _to_user_read(user)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> UserRead:
    """Update selected user fields."""

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.role_name is not None:
        user.role = _get_role(session, payload.role_name)
    if payload.is_active is not None:
        user.is_active = payload.is_active

    session.commit()
    session.refresh(user)
    return _to_user_read(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: int,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> None:
    """Deactivate a user instead of physically deleting the audit trail owner."""

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.is_active = False
    session.commit()

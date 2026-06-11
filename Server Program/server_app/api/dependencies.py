"""FastAPI dependency functions shared by routers."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from server_app.core.config import AppConfig
from server_app.core.constants import SUPER_ADMIN_ROLE
from server_app.core.security import TokenError, decode_access_token
from server_app.db.models import User
from server_app.services.auth import user_has_role


bearer_scheme = HTTPBearer(auto_error=False)


def get_config(request: Request) -> AppConfig:
    """Return the active server configuration from FastAPI app state."""

    return request.app.state.config


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """Return the SQLAlchemy session factory stored on app state."""

    return request.app.state.session_factory


def get_db(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> Generator[Session, None, None]:
    """Open and close a database session for one API request."""

    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    config: AppConfig = Depends(get_config),
    session: Session = Depends(get_db),
) -> User:
    """Authenticate the current request using a bearer token."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    try:
        payload = decode_access_token(credentials.credentials, config.jwt_secret)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    username = payload.get("sub")
    if not isinstance(username, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is invalid.",
        )

    user = session.query(User).filter(User.username == username).one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is not active.",
        )

    return user


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """Allow only the built-in Super Admin role."""

    if not user_has_role(current_user, {SUPER_ADMIN_ROLE}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin role is required.",
        )
    return current_user

"""Authentication API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from server_app.api.dependencies import get_config, get_current_user, get_db
from server_app.core.config import AppConfig
from server_app.core.security import create_access_token
from server_app.db.models import User
from server_app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from server_app.services.auth import authenticate_user, role_name_for_user


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    config: AppConfig = Depends(get_config),
    session: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate a user and return a bearer token."""

    user = authenticate_user(session, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = create_access_token(
        subject=user.username,
        secret_key=config.jwt_secret,
        role=role_name_for_user(user),
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=CurrentUserResponse)
def read_me(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    """Return the current authenticated user."""

    return CurrentUserResponse(
        id=current_user.id,
        username=current_user.username,
        full_name=current_user.full_name,
        role=role_name_for_user(current_user),
        is_active=current_user.is_active,
    )

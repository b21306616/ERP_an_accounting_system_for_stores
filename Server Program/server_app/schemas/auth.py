"""Authentication request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from server_app.schemas.common import OrmModel


class LoginRequest(BaseModel):
    """Credentials submitted to ``POST /auth/login``."""

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """Bearer token returned after successful login."""

    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(OrmModel):
    """Current authenticated user summary."""

    id: int
    username: str
    full_name: str
    role: str
    is_active: bool

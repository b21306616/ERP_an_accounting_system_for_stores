"""User administration schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from server_app.schemas.common import OrmModel


class UserCreate(BaseModel):
    """Owner-only payload for creating a user."""

    username: str = Field(min_length=1, max_length=80)
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=6)
    role_name: str = Field(default="Cashier", max_length=50)
    is_active: bool = True


class UserUpdate(BaseModel):
    """Owner-only payload for updating a user."""

    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    password: str | None = Field(default=None, min_length=6)
    role_name: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class UserRead(OrmModel):
    """User response object used by admin endpoints."""

    id: int
    username: str
    full_name: str
    role_name: str
    is_active: bool

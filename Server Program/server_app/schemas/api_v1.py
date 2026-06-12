"""Schemas for the documented /api/v1 contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ApiEnvelope(BaseModel):
    """Standard response envelope used by API v1."""

    success: bool
    data: Any = None
    error: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class V1LoginRequest(BaseModel):
    """Credentials submitted by the endpoint client."""

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1)
    client_name: str | None = Field(default=None, max_length=120)
    client_version: str | None = Field(default=None, max_length=40)


class V1AdminPasswordRequest(BaseModel):
    """Password verification request for privileged override flows."""

    password: str = Field(min_length=1)


class V1UserCreate(BaseModel):
    """Payload for creating a user through API v1."""

    username: str = Field(min_length=1, max_length=80)
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=6)
    role_name: str = Field(default="Cashier", max_length=50)
    workplace_id: int | None = None
    is_active: bool = True


class V1UserUpdate(BaseModel):
    """Payload for updating a user through API v1."""

    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    password: str | None = Field(default=None, min_length=6)
    current_password: str | None = Field(default=None, min_length=1)
    role_name: str | None = Field(default=None, max_length=50)
    workplace_id: int | None = None
    is_active: bool | None = None


class V1WorkplaceCreate(BaseModel):
    """Payload for creating a workplace."""

    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=120)
    workplace_type: str = Field(default="office", max_length=40)
    is_active: bool = True


class V1SettingsUpdate(BaseModel):
    """Patch-style settings update."""

    values: dict[str, Any]


class V1SessionResponse(BaseModel):
    """Session data returned after login."""

    session_token: str
    expires_at: datetime
    user: dict[str, Any]

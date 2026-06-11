"""Shared Pydantic schema helpers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OrmModel(BaseModel):
    """Base schema that can read fields from SQLAlchemy ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Simple success/error message response."""

    message: str

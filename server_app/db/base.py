"""Declarative SQLAlchemy base and shared model mixins."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


# Naming conventions make Alembic-generated and hand-written constraints stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for every SQLAlchemy ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class ReprMixin:
    """Helpful ``repr`` implementation for debugging model instances."""

    id: Any

    @declared_attr.directive
    def __repr_name__(cls) -> str:
        """Return the class name used by ``__repr__``."""

        return cls.__name__

    def __repr__(self) -> str:
        """Return a concise model representation."""

        return f"<{self.__repr_name__} id={getattr(self, 'id', None)!r}>"


class TimestampMixin:
    """Add created and updated timestamps to mutable tables."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

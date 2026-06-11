"""SQLAlchemy engine and session factory helpers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from server_app.core.config import AppConfig, build_sqlalchemy_url


def create_db_engine(config: AppConfig, database_override: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured MSSQL database."""

    url = build_sqlalchemy_url(config.database, database_override=database_override)
    return create_engine(url, pool_pre_ping=True, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a configured SQLAlchemy session factory."""

    return sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Provide a transaction scope around a group of database operations."""

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

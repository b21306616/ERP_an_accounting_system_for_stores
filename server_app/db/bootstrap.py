"""Database creation, migration, and seed helpers."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from server_app.core.config import AppConfig, build_sqlalchemy_url
from server_app.core.constants import BUILTIN_ROLES, OWNER_ROLE
from server_app.core.security import hash_password
from server_app.db.models import Role, User
from server_app.db.session import create_db_engine, create_session_factory


def _quote_sql_identifier(identifier: str) -> str:
    """Quote a SQL Server identifier with square brackets."""

    return "[" + identifier.replace("]", "]]") + "]"


def validate_database_name(database_name: str) -> None:
    """Reject database names that are empty or unsafe for automatic creation."""

    if not database_name.strip():
        raise ValueError("Database name is required.")
    if any(char in database_name for char in "\r\n;"):
        raise ValueError("Database name cannot contain line breaks or semicolons.")


def escape_alembic_config_value(value: str) -> str:
    """Escape percent signs before storing a value in Alembic's config parser."""

    return value.replace("%", "%%")


def create_database_if_missing(config: AppConfig) -> None:
    """Create the configured SQL Server database when it does not exist."""

    validate_database_name(config.database.database)
    engine = create_db_engine(config, database_override="master")

    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            exists = connection.execute(
                text("SELECT 1 FROM sys.databases WHERE name = :name"),
                {"name": config.database.database},
            ).scalar_one_or_none()

            if exists is None:
                quoted_name = _quote_sql_identifier(config.database.database)
                connection.execute(text(f"CREATE DATABASE {quoted_name}"))
    finally:
        engine.dispose()


def run_migrations(config: AppConfig) -> None:
    """Run Alembic migrations against the configured database."""

    project_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    sqlalchemy_url = build_sqlalchemy_url(config.database)
    alembic_cfg.set_main_option("sqlalchemy.url", escape_alembic_config_value(sqlalchemy_url))
    command.upgrade(alembic_cfg, "head")


def seed_builtin_roles(session: Session) -> dict[str, Role]:
    """Ensure built-in roles exist and return them by name."""

    existing_roles = {
        role.name: role for role in session.query(Role).filter(Role.name.in_(BUILTIN_ROLES)).all()
    }

    for role_name in BUILTIN_ROLES:
        if role_name not in existing_roles:
            role = Role(name=role_name, description=f"Built-in {role_name} role")
            session.add(role)
            existing_roles[role_name] = role

    session.flush()
    return existing_roles


def seed_owner_user(
    session: Session,
    username: str,
    full_name: str,
    password: str,
) -> User:
    """Create or update the initial Owner user from setup."""

    roles = seed_builtin_roles(session)
    owner_role = roles[OWNER_ROLE]
    user = session.query(User).filter(User.username == username).one_or_none()

    if user is None:
        user = User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            role=owner_role,
            is_active=True,
        )
        session.add(user)
    else:
        user.full_name = full_name
        user.password_hash = hash_password(password)
        user.role = owner_role
        user.is_active = True

    session.flush()
    return user


def bootstrap_database(config: AppConfig, owner_username: str, owner_full_name: str, owner_password: str) -> None:
    """Create DB, migrate schema, and seed built-in roles plus the first Owner."""

    create_database_if_missing(config)
    run_migrations(config)

    engine = create_db_engine(config)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            seed_owner_user(session, owner_username, owner_full_name, owner_password)
            session.commit()
    finally:
        engine.dispose()


def prepare_existing_database(config: AppConfig) -> tuple[Engine, sessionmaker[Session]]:
    """Run migrations, seed roles, validate connectivity, and return runtime DB objects."""

    run_migrations(config)
    engine, session_factory = create_runtime_database(config)

    try:
        with session_factory() as session:
            seed_builtin_roles(session)
            session.execute(text("SELECT 1"))
            session.commit()
    except Exception:
        engine.dispose()
        raise

    return engine, session_factory


def create_runtime_database(config: AppConfig) -> tuple[Engine, sessionmaker[Session]]:
    """Create an engine and session factory for the running API server."""

    engine = create_db_engine(config)
    return engine, create_session_factory(engine)

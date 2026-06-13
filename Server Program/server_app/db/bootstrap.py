"""Database creation, migration, and seed helpers."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from server_app.core.config import AppConfig, build_sqlalchemy_url
from server_app.core.constants import (
    BUILTIN_ROLES,
    BUILTIN_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
    SUPER_ADMIN_FULL_NAME,
    SUPER_ADMIN_ROLE,
    SUPER_ADMIN_USERNAME,
)
from server_app.core.security import hash_password, verify_password
from server_app.db.models import Currency, Permission, Role, RolePermission, Setting, UnitOfMeasure, User
from server_app.db.session import create_db_engine, create_session_factory
from server_app.service_control import SERVICE_SQL_LOGIN_NAME


def _quote_sql_identifier(identifier: str) -> str:
    """Quote a SQL Server identifier with square brackets."""

    return "[" + identifier.replace("]", "]]") + "]"


def _quote_sql_string(value: str) -> str:
    """Quote a SQL Server unicode string literal."""

    return "N'" + value.replace("'", "''") + "'"


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


def grant_windows_service_database_access(
    config: AppConfig,
    service_account: str = SERVICE_SQL_LOGIN_NAME,
) -> None:
    """Allow the LocalSystem Windows service to use the configured database."""

    if config.database.auth_mode != "windows":
        return

    validate_database_name(config.database.database)
    quoted_account = _quote_sql_identifier(service_account)
    account_literal = _quote_sql_string(service_account)
    master_engine = create_db_engine(config, database_override="master")

    try:
        with master_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(
                text(
                    f"""
                    IF SUSER_ID({account_literal}) IS NULL
                    BEGIN
                        CREATE LOGIN {quoted_account} FROM WINDOWS
                    END
                    """
                )
            )
    finally:
        master_engine.dispose()

    database_engine = create_db_engine(config)
    try:
        with database_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(
                text(
                    f"""
                    IF DATABASE_PRINCIPAL_ID({account_literal}) IS NULL
                    BEGIN
                        CREATE USER {quoted_account} FOR LOGIN {quoted_account}
                    END

                    IF ISNULL(IS_ROLEMEMBER(N'db_owner', {account_literal}), 0) <> 1
                    BEGIN
                        ALTER ROLE [db_owner] ADD MEMBER {quoted_account}
                    END
                    """
                )
            )
    finally:
        database_engine.dispose()


def run_migrations(config: AppConfig) -> None:
    """Run Alembic migrations against the configured database."""

    project_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        escape_alembic_config_value(str(project_root / "alembic")),
    )
    alembic_cfg.set_main_option(
        "prepend_sys_path",
        escape_alembic_config_value(str(project_root)),
    )
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


def seed_builtin_permissions(session: Session) -> dict[str, Permission]:
    """Ensure built-in permissions exist and return them by code."""

    existing_permissions = {
        permission.code: permission
        for permission in session.query(Permission).filter(Permission.code.in_(BUILTIN_PERMISSIONS)).all()
    }

    for permission_code in BUILTIN_PERMISSIONS:
        if permission_code not in existing_permissions:
            module_name = permission_code.split(".", 1)[0]
            permission = Permission(
                code=permission_code,
                module=module_name,
                description=f"Built-in permission {permission_code}",
            )
            session.add(permission)
            existing_permissions[permission_code] = permission

    session.flush()
    return existing_permissions


def seed_role_permissions(
    session: Session,
    roles: dict[str, Role],
    permissions: dict[str, Permission],
) -> None:
    """Ensure each built-in role has its default permission assignments."""

    existing_pairs = {
        (role_permission.role_id, role_permission.permission_id)
        for role_permission in session.query(RolePermission).all()
    }

    for role_name, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = roles.get(role_name)
        if role is None:
            continue
        for permission_code in permission_codes:
            permission = permissions.get(permission_code)
            if permission is None:
                continue
            pair = (role.id, permission.id)
            if pair not in existing_pairs:
                session.add(RolePermission(role=role, permission=permission))
                existing_pairs.add(pair)

    session.flush()


def seed_default_settings(session: Session) -> None:
    """Ensure the first client-visible settings row exists."""

    if session.query(Setting).filter(Setting.key == "organization").one_or_none() is None:
        session.add(
            Setting(
                key="organization",
                value_json=(
                    '{"name_ru":"Новая организация","name_tk":"Täze gurama",'
                    '"base_currency":"TMT","second_currency":null}'
                ),
                description="Organization profile and default currencies.",
            )
        )
        session.flush()


def seed_catalog_defaults(session: Session) -> None:
    """Ensure basic units of measure exist for the product catalog."""

    defaults = (
        ("pcs", "Штука", "Sany"),
        ("kg", "Килограмм", "Kilogram"),
        ("l", "Литр", "Litr"),
    )
    existing = {
        row.code
        for row in session.query(UnitOfMeasure).filter(UnitOfMeasure.code.in_([item[0] for item in defaults])).all()
    }
    for code, name_ru, name_tk in defaults:
        if code not in existing:
            session.add(UnitOfMeasure(code=code, name_ru=name_ru, name_tk=name_tk, is_active=True))
    session.flush()


def seed_currency_defaults(session: Session) -> None:
    """Ensure the base TMT currency exists."""

    if session.query(Currency).filter(Currency.code == "TMT").one_or_none() is None:
        session.add(Currency(code="TMT", name="Turkmen manat", symbol="TMT", is_system=True, is_active=True))
    session.flush()


def seed_foundation_data(session: Session) -> dict[str, Role]:
    """Seed roles, permissions, and settings needed by API v1 clients."""

    roles = seed_builtin_roles(session)
    permissions = seed_builtin_permissions(session)
    seed_role_permissions(session, roles, permissions)
    seed_default_settings(session)
    seed_catalog_defaults(session)
    seed_currency_defaults(session)
    return roles


def _find_other_super_admin(session: Session) -> User | None:
    """Return any non-fixed user incorrectly assigned the Super Admin role."""

    return (
        session.query(User)
        .join(Role)
        .filter(Role.name == SUPER_ADMIN_ROLE, User.username != SUPER_ADMIN_USERNAME)
        .first()
    )


def validate_super_admin_user(session: Session) -> User:
    """Enforce the fixed Super Admin account invariant for runtime startup."""

    roles = seed_foundation_data(session)
    super_admin_role = roles[SUPER_ADMIN_ROLE]
    user_count = session.query(User).count()
    user = session.query(User).filter(User.username == SUPER_ADMIN_USERNAME).one_or_none()

    if user_count == 0:
        raise ValueError("Database does not contain the fixed super_admin user. Run first setup.")
    if user is None:
        raise ValueError("Existing database must contain the fixed super_admin user.")
    if _find_other_super_admin(session) is not None:
        raise ValueError("Super Admin role is reserved for the fixed super_admin account.")

    user.full_name = SUPER_ADMIN_FULL_NAME
    user.role = super_admin_role
    user.is_active = True
    session.flush()
    return user


def seed_super_admin_user(
    session: Session,
    current_password: str | None,
    new_password: str,
) -> User:
    """Create or securely rotate the fixed Super Admin account."""

    roles = seed_foundation_data(session)
    super_admin_role = roles[SUPER_ADMIN_ROLE]
    user_count = session.query(User).count()
    user = session.query(User).filter(User.username == SUPER_ADMIN_USERNAME).one_or_none()
    other_super_admin = _find_other_super_admin(session)

    if other_super_admin is not None:
        raise ValueError("Super Admin role is reserved for the fixed super_admin account.")

    if user_count == 0:
        user = User(
            username=SUPER_ADMIN_USERNAME,
            full_name=SUPER_ADMIN_FULL_NAME,
            password_hash=hash_password(new_password),
            role=super_admin_role,
            is_active=True,
        )
        session.add(user)
    else:
        if user is None:
            raise ValueError(
                "Existing database must contain the fixed super_admin user before setup can reset its password."
            )
        if not current_password:
            raise ValueError("Current Super Admin password is required.")
        if not verify_password(current_password, user.password_hash):
            raise ValueError("Current Super Admin password is incorrect.")

        user.full_name = SUPER_ADMIN_FULL_NAME
        user.password_hash = hash_password(new_password)
        user.role = super_admin_role
        user.is_active = True

    session.flush()
    return user


def bootstrap_database(
    config: AppConfig,
    current_super_admin_password: str | None,
    new_super_admin_password: str,
) -> None:
    """Create DB, migrate schema, and seed or rotate the fixed Super Admin."""

    create_database_if_missing(config)
    run_migrations(config)

    engine = create_db_engine(config)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            seed_super_admin_user(session, current_super_admin_password, new_super_admin_password)
            session.commit()
    finally:
        engine.dispose()


def prepare_existing_database(config: AppConfig) -> tuple[Engine, sessionmaker[Session]]:
    """Run migrations, seed roles, validate connectivity, and return runtime DB objects."""

    run_migrations(config)
    engine, session_factory = create_runtime_database(config)

    try:
        with session_factory() as session:
            seed_foundation_data(session)
            validate_super_admin_user(session)
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

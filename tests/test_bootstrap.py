"""Tests for database bootstrap helper behavior."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server_app.core.constants import (
    BUILTIN_ROLES,
    SUPER_ADMIN_FULL_NAME,
    SUPER_ADMIN_ROLE,
    SUPER_ADMIN_USERNAME,
)
from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig, build_sqlalchemy_url
from server_app.core.security import hash_password, verify_password
from server_app.db.base import Base
from server_app.db.bootstrap import (
    escape_alembic_config_value,
    grant_windows_service_database_access,
    run_migrations,
    seed_builtin_roles,
    seed_super_admin_user,
    validate_database_name,
    validate_super_admin_user,
)
from server_app.db.models import Role, User
from server_app.service_control import SERVICE_SQL_LOGIN_NAME


class _CapturedSqlConnection:
    """Tiny SQLAlchemy connection double that records executed SQL text."""

    def __init__(self, statements: list[str]) -> None:
        self.statements = statements

    def execution_options(self, **_kwargs: object) -> "_CapturedSqlConnection":
        return self

    def __enter__(self) -> "_CapturedSqlConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: object) -> None:
        self.statements.append(str(statement))


class _CapturedSqlEngine:
    """Tiny SQLAlchemy engine double that records executed SQL text."""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self.disposed = False

    def connect(self) -> _CapturedSqlConnection:
        return _CapturedSqlConnection(self.statements)

    def dispose(self) -> None:
        self.disposed = True


class BootstrapTests(unittest.TestCase):
    """Validate bootstrap helpers that do not need a live SQL Server."""

    def setUp(self) -> None:
        """Create a fresh in-memory database for bootstrap helper tests."""

        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self) -> None:
        """Dispose the in-memory database."""

        self.engine.dispose()

    def test_escape_alembic_config_value_handles_odbc_url_percent_signs(self) -> None:
        """Alembic config should accept percent-encoded ODBC URLs."""

        url = build_sqlalchemy_url(DatabaseConfig(server="localhost\\SQLEXPRESS", database="ERP"))
        config = Config()

        config.set_main_option("sqlalchemy.url", escape_alembic_config_value(url))

        self.assertEqual(config.get_main_option("sqlalchemy.url"), url)

    def test_run_migrations_uses_absolute_script_location_for_windows_service(self) -> None:
        """Service startup should not depend on the current working directory."""

        config = AppConfig(
            database=DatabaseConfig(server="localhost\\SQLEXPRESS", database="ERP"),
            api=ApiConfig(),
            jwt_secret="secret",
        )
        captured_config: Config | None = None

        def capture_upgrade(alembic_config: Config, revision: str) -> None:
            nonlocal captured_config
            captured_config = alembic_config
            self.assertEqual(revision, "head")

        with patch("server_app.db.bootstrap.command.upgrade", side_effect=capture_upgrade):
            run_migrations(config)

        self.assertIsNotNone(captured_config)
        assert captured_config is not None
        project_root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            captured_config.get_main_option("script_location"),
            str(project_root / "alembic"),
        )
        self.assertEqual(captured_config.get_main_option("prepend_sys_path"), str(project_root))

    def test_grant_windows_service_database_access_skips_sql_login_configs(self) -> None:
        """SQL Login configs do not need a LocalSystem database user."""

        config = AppConfig(
            database=DatabaseConfig(
                server="localhost\\SQLEXPRESS",
                database="ERP",
                auth_mode="sql",
                username="sa",
                password="secret",
            ),
            api=ApiConfig(),
            jwt_secret="secret",
        )

        with patch("server_app.db.bootstrap.create_db_engine") as create_engine:
            grant_windows_service_database_access(config)

        create_engine.assert_not_called()

    def test_grant_windows_service_database_access_maps_service_sid(self) -> None:
        """Windows Auth configs should grant the per-service SID DB ownership."""

        config = AppConfig(
            database=DatabaseConfig(server="localhost\\SQLEXPRESS", database="ERP"),
            api=ApiConfig(),
            jwt_secret="secret",
        )
        master_engine = _CapturedSqlEngine()
        database_engine = _CapturedSqlEngine()

        with patch(
            "server_app.db.bootstrap.create_db_engine",
            side_effect=[master_engine, database_engine],
        ) as create_engine:
            grant_windows_service_database_access(config)

        self.assertEqual(create_engine.call_args_list[0].kwargs["database_override"], "master")
        self.assertEqual(create_engine.call_args_list[1].args[0], config)
        master_sql = "\n".join(master_engine.statements)
        database_sql = "\n".join(database_engine.statements)
        quoted_service_login = f"[{SERVICE_SQL_LOGIN_NAME}]"
        self.assertIn(f"CREATE LOGIN {quoted_service_login} FROM WINDOWS", master_sql)
        self.assertIn(
            f"CREATE USER {quoted_service_login} FOR LOGIN {quoted_service_login}",
            database_sql,
        )
        self.assertIn(f"ALTER ROLE [db_owner] ADD MEMBER {quoted_service_login}", database_sql)
        self.assertTrue(master_engine.disposed)
        self.assertTrue(database_engine.disposed)

    def test_validate_database_name_rejects_semicolon(self) -> None:
        """Database name validation should reject SQL separator characters."""

        with self.assertRaises(ValueError):
            validate_database_name("ERP;DROP")

    def test_seed_super_admin_user_creates_fixed_user_for_empty_database(self) -> None:
        """First setup should create the fixed Super Admin in an empty database."""

        with self.session_factory() as session:
            user = seed_super_admin_user(session, None, "password123")
            session.commit()

            self.assertEqual(user.username, SUPER_ADMIN_USERNAME)
            self.assertEqual(user.full_name, SUPER_ADMIN_FULL_NAME)
            self.assertEqual(user.role.name, SUPER_ADMIN_ROLE)
            self.assertTrue(user.is_active)
            self.assertTrue(verify_password("password123", user.password_hash))

    def test_seed_super_admin_user_requires_current_password_for_existing_database(self) -> None:
        """Setup password rotation should require the current Super Admin password."""

        with self.session_factory() as session:
            seed_super_admin_user(session, None, "password123")
            session.commit()
            user = session.query(User).filter(User.username == SUPER_ADMIN_USERNAME).one()
            original_hash = user.password_hash

            with self.assertRaises(ValueError):
                seed_super_admin_user(session, None, "changed123")

            session.rollback()
            user = session.query(User).filter(User.username == SUPER_ADMIN_USERNAME).one()
            self.assertEqual(user.password_hash, original_hash)
            self.assertTrue(verify_password("password123", user.password_hash))

    def test_seed_super_admin_user_rejects_wrong_current_password(self) -> None:
        """Wrong current password should leave the stored hash unchanged."""

        with self.session_factory() as session:
            seed_super_admin_user(session, None, "password123")
            session.commit()
            user = session.query(User).filter(User.username == SUPER_ADMIN_USERNAME).one()
            original_hash = user.password_hash

            with self.assertRaises(ValueError):
                seed_super_admin_user(session, "wrong-password", "changed123")

            session.rollback()
            user = session.query(User).filter(User.username == SUPER_ADMIN_USERNAME).one()
            self.assertEqual(user.password_hash, original_hash)
            self.assertTrue(verify_password("password123", user.password_hash))

    def test_seed_super_admin_user_rotates_password_after_current_password_match(self) -> None:
        """Matching the current password should allow setup to set a new password."""

        with self.session_factory() as session:
            seed_super_admin_user(session, None, "password123")
            session.commit()

            user = seed_super_admin_user(session, "password123", "changed123")
            session.commit()

            self.assertEqual(user.username, SUPER_ADMIN_USERNAME)
            self.assertEqual(user.full_name, SUPER_ADMIN_FULL_NAME)
            self.assertEqual(user.role.name, SUPER_ADMIN_ROLE)
            self.assertTrue(verify_password("changed123", user.password_hash))

    def test_seed_super_admin_user_rejects_existing_database_without_super_admin(self) -> None:
        """Non-empty databases must already contain the fixed super_admin user."""

        with self.session_factory() as session:
            roles = seed_builtin_roles(session)
            session.add(
                User(
                    username="cashier",
                    full_name="Cashier",
                    password_hash=hash_password("password123"),
                    role=roles["Cashier"],
                    is_active=True,
                )
            )
            session.commit()

            with self.assertRaises(ValueError):
                seed_super_admin_user(session, None, "changed123")

    def test_validate_super_admin_user_rejects_second_super_admin(self) -> None:
        """Only the fixed super_admin user should be allowed to hold the role."""

        with self.session_factory() as session:
            roles = {name: Role(name=name) for name in BUILTIN_ROLES}
            session.add_all(roles.values())
            session.add_all(
                [
                    User(
                        username=SUPER_ADMIN_USERNAME,
                        full_name=SUPER_ADMIN_FULL_NAME,
                        password_hash=hash_password("password123"),
                        role=roles[SUPER_ADMIN_ROLE],
                        is_active=True,
                    ),
                    User(
                        username="other_admin",
                        full_name="Other Admin",
                        password_hash=hash_password("password123"),
                        role=roles[SUPER_ADMIN_ROLE],
                        is_active=True,
                    ),
                ]
            )
            session.commit()

            with self.assertRaises(ValueError):
                validate_super_admin_user(session)


if __name__ == "__main__":
    unittest.main()

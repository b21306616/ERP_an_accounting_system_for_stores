"""Tests for database bootstrap helper behavior."""

from __future__ import annotations

import unittest

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
from server_app.core.config import DatabaseConfig, build_sqlalchemy_url
from server_app.core.security import hash_password, verify_password
from server_app.db.base import Base
from server_app.db.bootstrap import (
    escape_alembic_config_value,
    seed_builtin_roles,
    seed_super_admin_user,
    validate_database_name,
    validate_super_admin_user,
)
from server_app.db.models import Role, User


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

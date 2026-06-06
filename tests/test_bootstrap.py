"""Tests for database bootstrap helper behavior."""

from __future__ import annotations

import unittest

from alembic.config import Config

from server_app.core.config import DatabaseConfig, build_sqlalchemy_url
from server_app.db.bootstrap import escape_alembic_config_value, validate_database_name


class BootstrapTests(unittest.TestCase):
    """Validate bootstrap helpers that do not need a live SQL Server."""

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


if __name__ == "__main__":
    unittest.main()

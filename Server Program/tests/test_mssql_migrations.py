"""Optional Alembic smoke test for a disposable MSSQL database."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


MSSQL_TEST_URL_ENV = "ERP_MSSQL_TEST_URL"


@unittest.skipUnless(os.getenv(MSSQL_TEST_URL_ENV), f"Set {MSSQL_TEST_URL_ENV} to a disposable MSSQL SQLAlchemy URL to run.")
class MSSQLMigrationSmokeTests(unittest.TestCase):
    """Run the full Alembic chain against an explicitly supplied MSSQL database."""

    def test_alembic_upgrade_head_on_mssql(self) -> None:
        """All migrations should apply to the configured disposable MSSQL database."""

        database_url = os.environ[MSSQL_TEST_URL_ENV]
        parsed = make_url(database_url)
        self.assertIn("mssql", parsed.drivername)

        server_program = Path(__file__).resolve().parents[1]
        config = Config(str(server_program / "alembic.ini"))
        config.set_main_option("script_location", str(server_program / "alembic"))
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

        command.upgrade(config, "head")

        engine = create_engine(database_url, future=True)
        try:
            with engine.connect() as connection:
                result = connection.execute(text("SELECT version_num FROM alembic_version"))
                self.assertEqual(result.scalar_one(), "0008_promotions_loyalty")
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()

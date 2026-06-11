"""Tests for configuration and connection-string helpers."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server_app.core.config import (
    ApiConfig,
    AppConfig,
    ConfigManager,
    DatabaseConfig,
    build_odbc_connection_string,
    build_sqlalchemy_url,
)
from server_app.core.paths import get_config_path
from server_app.core.secrets import protect_secret, unprotect_secret


class ConfigTests(unittest.TestCase):
    """Validate config helper behavior that does not require SQL Server."""

    def test_build_windows_auth_odbc_connection_string(self) -> None:
        """Windows Authentication should not include username/password fields."""

        config = DatabaseConfig(server="SERVER\\SQLEXPRESS", database="ERP")
        connection_string = build_odbc_connection_string(config)

        self.assertIn("DRIVER={ODBC Driver 18 for SQL Server}", connection_string)
        self.assertIn("SERVER=SERVER\\SQLEXPRESS", connection_string)
        self.assertIn("DATABASE=ERP", connection_string)
        self.assertIn("Trusted_Connection=yes", connection_string)
        self.assertNotIn("UID=", connection_string)
        self.assertNotIn("PWD=", connection_string)

    def test_build_sql_login_odbc_connection_string(self) -> None:
        """SQL Login should include UID and PWD fields."""

        config = DatabaseConfig(
            server="localhost",
            database="ERP",
            auth_mode="sql",
            username="sa",
            password="secret",
            trust_server_certificate=False,
        )
        connection_string = build_odbc_connection_string(config)

        self.assertIn("UID=sa", connection_string)
        self.assertIn("PWD=secret", connection_string)
        self.assertIn("TrustServerCertificate=no", connection_string)

    def test_build_sqlalchemy_url_encodes_odbc_string(self) -> None:
        """The SQLAlchemy URL should wrap the ODBC string in ``odbc_connect``."""

        config = DatabaseConfig(server="localhost", database="ERP")
        url = build_sqlalchemy_url(config)

        self.assertTrue(url.startswith("mssql+pyodbc:///?odbc_connect="))
        self.assertIn("ODBC+Driver+18+for+SQL+Server", url)

    def test_config_save_load_uses_protected_storage(self) -> None:
        """ConfigManager should roundtrip config while protecting secrets."""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "config.json")
            config = AppConfig(
                database=DatabaseConfig(
                    server="localhost",
                    database="ERP",
                    auth_mode="sql",
                    username="sa",
                    password="secret-password",
                ),
                api=ApiConfig(host="127.0.0.1", port=8123),
                jwt_secret="jwt-secret",
            )

            manager = ConfigManager(path=Path(path))
            manager.save(config)
            with open(path, "r", encoding="utf-8") as file:
                raw_text = file.read()

            self.assertNotIn("secret-password", raw_text)
            self.assertNotIn("jwt-secret", raw_text)

            loaded = manager.load()
            self.assertEqual(loaded.database.password, "secret-password")
            self.assertEqual(loaded.jwt_secret, "jwt-secret")

    def test_config_path_defaults_to_program_data(self) -> None:
        """Default config storage should be machine-wide for the Windows service."""

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"ERP_SERVER_CONFIG_DIR": "", "PROGRAMDATA": temp_dir}):
                self.assertEqual(
                    get_config_path(),
                    Path(temp_dir) / "ERPAccountingServer" / "config.json",
                )

    def test_config_path_env_override_is_preserved(self) -> None:
        """Tests and controlled deployments can still override config storage."""

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"ERP_SERVER_CONFIG_DIR": temp_dir}):
                self.assertEqual(get_config_path(), Path(temp_dir) / "config.json")

    def test_config_manager_migrates_legacy_config_once(self) -> None:
        """Old LocalAppData config should be copied to the machine-wide config path."""

        with tempfile.TemporaryDirectory() as temp_dir:
            primary = Path(temp_dir) / "program_data" / "config.json"
            legacy = Path(temp_dir) / "local_app_data" / "config.json"
            config = AppConfig(
                database=DatabaseConfig(
                    server="localhost",
                    database="ERP",
                    auth_mode="sql",
                    username="sa",
                    password="secret-password",
                ),
                api=ApiConfig(host="127.0.0.1", port=8123),
                jwt_secret="jwt-secret",
            )

            ConfigManager(path=legacy).save(config)
            manager = ConfigManager(path=primary, legacy_path=legacy)

            self.assertTrue(manager.exists())
            self.assertTrue(manager.migrate_legacy_if_needed())
            self.assertTrue(primary.exists())

            loaded = manager.load()
            self.assertEqual(loaded.database.password, "secret-password")
            self.assertEqual(loaded.jwt_secret, "jwt-secret")

    def test_dpapi_roundtrip(self) -> None:
        """DPAPI helper should return the original secret after unprotecting."""

        protected = protect_secret("local secret")
        self.assertNotEqual(protected, "local secret")
        self.assertEqual(unprotect_secret(protected), "local secret")


if __name__ == "__main__":
    unittest.main()

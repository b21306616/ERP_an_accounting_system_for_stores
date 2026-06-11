"""Tests for environment reset helper behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from server_app.core.config import AppConfig, ApiConfig, DatabaseConfig

import reset_env


class _MissingConfigManager:
    """Config manager test double with no saved config."""

    def exists(self) -> bool:
        return False


class _SavedConfigManager:
    """Config manager test double with a saved config."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def exists(self) -> bool:
        return True

    def load(self) -> AppConfig:
        return self.config


class _UnreadableConfigManager:
    """Config manager test double with an unreadable saved config."""

    def exists(self) -> bool:
        return True

    def load(self) -> AppConfig:
        raise ValueError("broken config")


class ResetEnvTests(unittest.TestCase):
    """Validate reset script choices without touching a live SQL Server."""

    def test_load_reset_config_returns_none_when_config_is_missing(self) -> None:
        """Missing config.json should not select any database to drop."""

        config = reset_env.load_reset_config(_MissingConfigManager())

        self.assertIsNone(config)

    def test_load_reset_config_returns_none_when_config_is_unreadable(self) -> None:
        """Unreadable config.json should not select any database to drop."""

        config = reset_env.load_reset_config(_UnreadableConfigManager())

        self.assertIsNone(config)

    def test_load_reset_config_uses_saved_database_when_available(self) -> None:
        """Saved config should control which database reset drops."""

        saved_config = AppConfig(
            database=DatabaseConfig(server="localhost", database="ConfiguredERP"),
            api=ApiConfig(),
            jwt_secret="secret",
        )

        config = reset_env.load_reset_config(_SavedConfigManager(saved_config))

        self.assertEqual(config.database.database, "ConfiguredERP")

    def test_db_only_skips_drop_when_config_is_missing(self) -> None:
        """`--db-only` should not drop anything when config.json is gone."""

        with (
            patch("sys.argv", ["reset_env.py", "--db-only"]),
            patch("reset_env.ConfigManager", return_value=_MissingConfigManager()),
            patch("reset_env.drop_mssql_database") as drop_database,
        ):
            reset_env.main()

        drop_database.assert_not_called()

    def test_full_reset_skips_drop_when_config_is_missing(self) -> None:
        """Full reset should not drop anything when config.json is gone."""

        with (
            patch("sys.argv", ["reset_env.py"]),
            patch("reset_env.ConfigManager", return_value=_MissingConfigManager()),
            patch("reset_env.drop_mssql_database") as drop_database,
            patch("reset_env.clear_config_settings"),
            patch("reset_env.clear_bytecode_cache"),
        ):
            reset_env.main()

        drop_database.assert_not_called()


if __name__ == "__main__":
    unittest.main()

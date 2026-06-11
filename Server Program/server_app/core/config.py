"""Typed application configuration and JSON persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus

from server_app.core.constants import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_ODBC_DRIVER,
)
from server_app.core.paths import get_config_path, get_legacy_config_path
from server_app.core.secrets import protect_secret, unprotect_secret
from server_app.core.security import generate_secret_key


AuthMode = Literal["windows", "sql"]


@dataclass(slots=True)
class DatabaseConfig:
    """Database connection settings collected from the setup GUI."""

    server: str
    database: str
    driver: str = DEFAULT_ODBC_DRIVER
    auth_mode: AuthMode = "windows"
    username: str | None = None
    password: str | None = None
    trust_server_certificate: bool = True


@dataclass(slots=True)
class ApiConfig:
    """FastAPI bind host and port values."""

    host: str = DEFAULT_API_HOST
    port: int = DEFAULT_API_PORT


@dataclass(slots=True)
class AppConfig:
    """Complete server configuration persisted after first setup."""

    database: DatabaseConfig
    api: ApiConfig
    jwt_secret: str


def create_default_config() -> AppConfig:
    """Return a default config object useful for pre-filling the setup form."""

    return AppConfig(
        database=DatabaseConfig(server="localhost", database="ERPAccounting"),
        api=ApiConfig(),
        jwt_secret=generate_secret_key(),
    )


def _clean_odbc_value(value: str) -> str:
    """Escape braces inside an ODBC value before building a connection string."""

    return value.replace("}", "}}")


def build_odbc_connection_string(
    db_config: DatabaseConfig,
    database_override: str | None = None,
    include_database: bool = True,
) -> str:
    """Build a SQL Server ODBC connection string from typed settings."""

    database_name = database_override if database_override is not None else db_config.database
    parts = [
        f"DRIVER={{{_clean_odbc_value(db_config.driver)}}}",
        f"SERVER={_clean_odbc_value(db_config.server)}",
        "Encrypt=yes",
        f"TrustServerCertificate={'yes' if db_config.trust_server_certificate else 'no'}",
    ]

    if include_database and database_name:
        parts.append(f"DATABASE={_clean_odbc_value(database_name)}")

    if db_config.auth_mode == "windows":
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={_clean_odbc_value(db_config.username or '')}")
        parts.append(f"PWD={_clean_odbc_value(db_config.password or '')}")

    return ";".join(parts) + ";"


def build_sqlalchemy_url(
    db_config: DatabaseConfig,
    database_override: str | None = None,
    include_database: bool = True,
) -> str:
    """Build the SQLAlchemy pyodbc URL for SQL Server."""

    connection_string = build_odbc_connection_string(
        db_config,
        database_override=database_override,
        include_database=include_database,
    )
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(connection_string)}"


def _config_to_storage(config: AppConfig) -> dict[str, Any]:
    """Convert config into JSON-safe storage with protected secrets."""

    data = asdict(config)
    password = data["database"].get("password")
    if password:
        data["database"]["protected_password"] = protect_secret(password)
    data["database"].pop("password", None)
    data["protected_jwt_secret"] = protect_secret(config.jwt_secret)
    data.pop("jwt_secret", None)
    return data


def _config_from_storage(data: dict[str, Any]) -> AppConfig:
    """Create typed config from JSON storage and unprotect secrets."""

    database_data = dict(data.get("database", {}))
    protected_password = database_data.pop("protected_password", None)
    if protected_password:
        database_data["password"] = unprotect_secret(protected_password)
    else:
        database_data["password"] = None

    protected_jwt_secret = data.get("protected_jwt_secret")
    if not protected_jwt_secret:
        raise ValueError("Saved configuration is missing the JWT secret.")

    return AppConfig(
        database=DatabaseConfig(**database_data),
        api=ApiConfig(**data.get("api", {})),
        jwt_secret=unprotect_secret(protected_jwt_secret),
    )


class ConfigManager:
    """Read and write the server configuration file."""

    def __init__(self, path: Path | None = None, legacy_path: Path | None = None) -> None:
        self.path = path or get_config_path()
        self.legacy_path = legacy_path if legacy_path is not None else (
            get_legacy_config_path() if path is None else None
        )

    def exists(self) -> bool:
        """Return whether the configuration file already exists."""

        return self.path.exists() or bool(self.legacy_path and self.legacy_path.exists())

    def load(self) -> AppConfig:
        """Load and decrypt configuration from JSON storage."""

        with self._read_path().open("r", encoding="utf-8") as file:
            data = json.load(file)
        return _config_from_storage(data)

    def save(self, config: AppConfig) -> None:
        """Protect secrets and save configuration to disk."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = _config_to_storage(config)
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)

    def migrate_legacy_if_needed(self) -> bool:
        """Copy old per-user config into the machine-wide config path when needed."""

        if self.path.exists() or self.legacy_path is None or not self.legacy_path.exists():
            return False

        with self.legacy_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        self.save(_config_from_storage(data))
        return True

    def _read_path(self) -> Path:
        """Return the primary config path, falling back to legacy storage."""

        if self.path.exists():
            return self.path
        if self.legacy_path is not None and self.legacy_path.exists():
            return self.legacy_path
        return self.path

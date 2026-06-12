"""Local endpoint-client configuration persisted in Windows AppData."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Literal


LanguageCode = Literal["ru", "tk"]
APP_DATA_DIR_NAME = "ERPAccountingUser"
CONFIG_FILE_NAME = "config.json"
DEFAULT_SERVER_URL = "http://127.0.0.1:8000/api/v1"


@dataclass(slots=True)
class ClientConfig:
    """Endpoint-local settings that are safe to store outside the server."""

    server_url: str = DEFAULT_SERVER_URL
    language: LanguageCode = "ru"


def get_config_dir() -> Path:
    """Return the AppData folder used by the endpoint client."""

    override = os.environ.get("ERP_USER_CONFIG_DIR")
    if override:
        return Path(override)

    app_data = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if app_data:
        return Path(app_data) / APP_DATA_DIR_NAME

    return Path.home() / f".{APP_DATA_DIR_NAME}"


def get_config_path() -> Path:
    """Return the endpoint-client config file path."""

    return get_config_dir() / CONFIG_FILE_NAME


class ClientConfigManager:
    """Load and save endpoint-client settings."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_config_path()

    def load(self) -> ClientConfig:
        """Load config, returning defaults when the file is missing or broken."""

        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return ClientConfig()

        language = data.get("language", "ru")
        if language not in {"ru", "tk"}:
            language = "ru"
        return ClientConfig(
            server_url=str(data.get("server_url") or DEFAULT_SERVER_URL),
            language=language,
        )

    def save(self, config: ClientConfig) -> None:
        """Save config to AppData."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(asdict(config), file, indent=2, sort_keys=True)


def normalize_server_url(raw_url: str) -> str:
    """Normalize a server URL so it points to the documented API v1 base."""

    url = raw_url.strip().rstrip("/")
    if not url:
        return DEFAULT_SERVER_URL
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    if not url.endswith("/api/v1"):
        url = f"{url}/api/v1"
    return url

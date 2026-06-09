"""Filesystem path helpers for app-local configuration files."""

from __future__ import annotations

import os
from pathlib import Path

from server_app.core.constants import APP_DATA_DIR_NAME, CONFIG_FILE_NAME


def get_config_dir() -> Path:
    """Return the directory where server configuration should be stored.

    ``ERP_SERVER_CONFIG_DIR`` is intentionally supported for tests and
    controlled deployments. Normal Windows service deployments use
    machine-wide ``PROGRAMDATA`` so the GUI and LocalSystem service share
    the same configuration.
    """

    override = os.environ.get("ERP_SERVER_CONFIG_DIR")
    if override:
        return Path(override)

    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        return Path(program_data) / APP_DATA_DIR_NAME

    return Path.home() / f".{APP_DATA_DIR_NAME}"


def get_legacy_config_dir() -> Path:
    """Return the previous per-user config directory used before service support."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DATA_DIR_NAME

    return Path.home() / f".{APP_DATA_DIR_NAME}"


def get_config_path() -> Path:
    """Return the full path to the JSON configuration file."""

    return get_config_dir() / CONFIG_FILE_NAME


def get_legacy_config_path() -> Path:
    """Return the old per-user config path for one-time migration."""

    return get_legacy_config_dir() / CONFIG_FILE_NAME

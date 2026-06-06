"""Qt worker threads for database startup and first-run bootstrap."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from server_app.core.config import AppConfig
from server_app.db.bootstrap import bootstrap_database, prepare_existing_database


class DatabaseStartupWorker(QThread):
    """Prepare the database in the background and return runtime DB objects."""

    succeeded = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        config: AppConfig,
        owner_username: str | None = None,
        owner_full_name: str | None = None,
        owner_password: str | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.owner_username = owner_username
        self.owner_full_name = owner_full_name
        self.owner_password = owner_password

    def run(self) -> None:
        """Create/migrate/validate the database without blocking the GUI thread."""

        try:
            if self.owner_username and self.owner_full_name and self.owner_password:
                bootstrap_database(
                    self.config,
                    self.owner_username,
                    self.owner_full_name,
                    self.owner_password,
                )

            engine, session_factory = prepare_existing_database(self.config)
            self.succeeded.emit(engine, session_factory)
        except Exception as exc:
            self.failed.emit(str(exc))

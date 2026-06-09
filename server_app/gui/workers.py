"""Qt worker threads for database startup and first-run bootstrap."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from server_app.core.config import AppConfig
from server_app.db.bootstrap import bootstrap_database


class DatabaseStartupWorker(QThread):
    """Create/migrate/seed the database in the background for first setup."""

    succeeded = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        config: AppConfig,
        current_super_admin_password: str | None = None,
        new_super_admin_password: str | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.current_super_admin_password = current_super_admin_password
        self.new_super_admin_password = new_super_admin_password

    def run(self) -> None:
        """Create/migrate/seed the database without blocking the GUI thread."""

        try:
            if self.new_super_admin_password is None:
                raise ValueError("New Super Admin password is required for first setup.")

            bootstrap_database(
                self.config,
                self.current_super_admin_password,
                self.new_super_admin_password,
            )
            self.succeeded.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class ServiceActionWorker(QThread):
    """Run a blocking Windows service action without freezing the GUI."""

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, action: Callable[[], object]) -> None:
        super().__init__()
        self.action = action

    def run(self) -> None:
        """Execute the configured service action."""

        try:
            self.succeeded.emit(self.action())
        except Exception as exc:
            self.failed.emit(str(exc))

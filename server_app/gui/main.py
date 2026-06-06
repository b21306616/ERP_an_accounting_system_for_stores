"""PyQt6 application coordinator for the server desktop app."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QMessageBox
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from server_app.core.config import AppConfig, ConfigManager
from server_app.core.constants import APP_NAME
from server_app.gui.server_thread import ApiServerThread
from server_app.gui.setup_window import SetupWindow
from server_app.gui.summary_window import SummaryWindow
from server_app.gui.workers import DatabaseStartupWorker


class ApplicationCoordinator(QObject):
    """Own the GUI windows, database workers, and API server thread."""

    def __init__(self, app: QApplication, config_manager: ConfigManager) -> None:
        super().__init__()
        self.app = app
        self.config_manager = config_manager
        self.setup_window: SetupWindow | None = None
        self.summary_window: SummaryWindow | None = None
        self.startup_worker: DatabaseStartupWorker | None = None
        self.api_thread: ApiServerThread | None = None
        self.engine: Engine | None = None
        self.quit_after_stop = False
        self.pending_config: AppConfig | None = None
        self.pending_save_config = False

        self.app.aboutToQuit.connect(self.shutdown)

    def start(self) -> None:
        """Start from saved config when available; otherwise show first setup."""

        if not self.config_manager.exists():
            self.show_setup()
            return

        try:
            config = self.config_manager.load()
        except Exception as exc:
            self.show_setup(f"Could not load saved config: {exc}")
            return

        self.summary_window = SummaryWindow(config)
        self.summary_window.stop_requested.connect(self.stop_connection)
        self.summary_window.show()
        self._start_database_worker(config, should_save_config=False)

    def show_setup(self, error_message: str | None = None) -> None:
        """Show the setup window and connect its submission signal."""

        old_summary_window = self.summary_window
        if self.summary_window is not None:
            self.summary_window = None

        self.setup_window = SetupWindow(error_message)
        self.setup_window.setup_requested.connect(self.handle_setup_requested)
        self.setup_window.show()

        if old_summary_window is not None:
            old_summary_window.close()

    def handle_setup_requested(
        self,
        config: AppConfig,
        owner_username: str,
        owner_full_name: str,
        owner_password: str,
    ) -> None:
        """Start database bootstrap after the setup form validates."""

        self._start_database_worker(
            config,
            should_save_config=True,
            owner_username=owner_username,
            owner_full_name=owner_full_name,
            owner_password=owner_password,
        )

    def _start_database_worker(
        self,
        config: AppConfig,
        should_save_config: bool,
        owner_username: str | None = None,
        owner_full_name: str | None = None,
        owner_password: str | None = None,
    ) -> None:
        """Launch the database preparation thread."""

        self.pending_config = config
        self.pending_save_config = should_save_config
        self.startup_worker = DatabaseStartupWorker(
            config,
            owner_username=owner_username,
            owner_full_name=owner_full_name,
            owner_password=owner_password,
        )
        self.startup_worker.succeeded.connect(self.handle_database_ready)
        self.startup_worker.failed.connect(self.handle_database_failed)
        self.startup_worker.start()

    def handle_database_ready(
        self,
        engine: Engine,
        session_factory: sessionmaker[Session],
    ) -> None:
        """Save config when needed, then start the API server thread."""

        config = self.pending_config
        if config is None:
            engine.dispose()
            return

        if self.pending_save_config:
            try:
                self.config_manager.save(config)
            except Exception as exc:
                engine.dispose()
                if self.setup_window is not None:
                    self.setup_window.show_error(f"Database is ready, but config could not be saved: {exc}")
                else:
                    QMessageBox.critical(None, APP_NAME, f"Config could not be saved: {exc}")
                return

        self.engine = engine
        self._start_api(config, session_factory)

    def handle_database_failed(self, message: str) -> None:
        """Show database bootstrap/startup errors to the operator."""

        if self.setup_window is not None:
            self.setup_window.show_error(message)
            return

        if self.summary_window is not None:
            self.summary_window.mark_error(message)

        QMessageBox.critical(None, APP_NAME, message)
        self.show_setup(f"Saved configuration could not start: {message}")

    def _start_api(self, config: AppConfig, session_factory: sessionmaker[Session]) -> None:
        """Create the summary window if needed and start uvicorn."""

        if self.summary_window is None:
            self.summary_window = SummaryWindow(config)
            self.summary_window.stop_requested.connect(self.stop_connection)
            self.summary_window.show()

        if self.setup_window is not None:
            self.setup_window.close()
            self.setup_window = None

        self.api_thread = ApiServerThread(config, session_factory)
        self.api_thread.started_listening.connect(self.handle_api_started)
        self.api_thread.failed.connect(self.handle_api_failed)
        self.api_thread.stopped.connect(self.handle_api_stopped)
        self.api_thread.start()

    def handle_api_started(self) -> None:
        """Mark the server as running in the summary window."""

        if self.summary_window is not None:
            self.summary_window.mark_running()

    def handle_api_failed(self, message: str) -> None:
        """Show uvicorn startup/runtime errors."""

        if self.summary_window is not None:
            self.summary_window.mark_error(message)
        QMessageBox.critical(None, APP_NAME, message)

    def stop_connection(self) -> None:
        """Stop the API after the operator clicks Stop Connection."""

        self.quit_after_stop = True
        if self.summary_window is not None:
            self.summary_window.mark_stopping()

        if self.api_thread is not None and self.api_thread.isRunning():
            self.api_thread.stop()
        else:
            self._dispose_engine()
            self.app.quit()

    def handle_api_stopped(self) -> None:
        """Dispose database resources after uvicorn exits."""

        self._dispose_engine()
        if self.quit_after_stop:
            self.app.quit()

    def _dispose_engine(self) -> None:
        """Release SQLAlchemy connection pool resources."""

        if self.engine is not None:
            self.engine.dispose()
            self.engine = None

    def shutdown(self) -> None:
        """Best-effort cleanup when the Qt application exits."""

        if self.api_thread is not None and self.api_thread.isRunning():
            self.api_thread.stop()
            self.api_thread.wait(3000)
        self._dispose_engine()


def run_desktop_app() -> None:
    """Run the PyQt6 desktop application."""

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    coordinator = ApplicationCoordinator(app, ConfigManager())
    coordinator.start()
    sys.exit(app.exec())

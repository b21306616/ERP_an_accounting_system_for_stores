"""PyQt6 application coordinator for the server desktop app."""

from __future__ import annotations

from collections.abc import Callable
import sys

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from server_app.core.config import AppConfig, ConfigManager
from server_app.core.constants import APP_NAME
from server_app.core.network import check_tcp_port, is_port_bind_error_message
from server_app.gui.i18n import format_port_check_message, tr
from server_app.gui.setup_window import SetupWindow
from server_app.gui.summary_window import SummaryWindow
from server_app.gui.workers import DatabaseStartupWorker, ServiceActionWorker
from server_app.db.bootstrap import grant_windows_service_database_access
from server_app.service_control import (
    ServiceRunState,
    ServiceStatus,
    WindowsServiceController,
)


class ApplicationCoordinator(QObject):
    """Own the GUI windows and coordinate Windows service actions."""

    SERVICE_STATUS_POLL_INTERVAL_MS = 2000

    def __init__(
        self,
        app: QApplication,
        config_manager: ConfigManager,
        service_controller: WindowsServiceController | None = None,
    ) -> None:
        super().__init__()
        self.app = app
        self.config_manager = config_manager
        self.service_controller = service_controller or WindowsServiceController()
        self.setup_window: SetupWindow | None = None
        self.summary_window: SummaryWindow | None = None
        self.startup_worker: DatabaseStartupWorker | None = None
        self.service_worker: ServiceActionWorker | None = None
        self.pending_config: AppConfig | None = None
        self.service_status_timer = QTimer(self)
        self.service_status_timer.setInterval(self.SERVICE_STATUS_POLL_INTERVAL_MS)
        self.service_status_timer.timeout.connect(self.refresh_service_status)

        self.app.aboutToQuit.connect(self.shutdown)

    def start(self) -> None:
        """Start from saved config when available; otherwise show first setup."""

        if not self.config_manager.exists():
            self.show_setup()
            return

        try:
            self.config_manager.migrate_legacy_if_needed()
            config = self.config_manager.load()
        except Exception as exc:
            self.show_setup(tr("coordinator.load_config_failed", message=exc))
            return

        self.show_summary(config)
        self.refresh_service_status()

    def show_setup(self, error_message: str | None = None) -> None:
        """Show the setup window and connect its submission signal."""

        self._stop_service_status_polling()
        old_summary_window = self.summary_window
        if self.summary_window is not None:
            self.summary_window = None

        self.setup_window = SetupWindow(error_message)
        self.setup_window.setup_requested.connect(self.handle_setup_requested)
        self.setup_window.show()

        if old_summary_window is not None:
            old_summary_window.close()

    def show_summary(self, config: AppConfig) -> None:
        """Show the running/stopped service summary window."""

        self.summary_window = SummaryWindow(config)
        self.summary_window.start_requested.connect(self.start_connection)
        self.summary_window.stop_requested.connect(self.stop_connection)
        self.summary_window.config_update_requested.connect(self.handle_summary_config_update)
        self.summary_window.super_admin_password_update_requested.connect(
            self.handle_summary_password_update_requested
        )
        self.summary_window.show()
        self._start_service_status_polling()

    def handle_setup_requested(
        self,
        config: AppConfig,
        current_super_admin_password: str | None,
        new_super_admin_password: str,
    ) -> None:
        """Start database bootstrap after the setup form validates."""

        try:
            self.service_controller.require_admin()
        except Exception as exc:
            if self.setup_window is not None:
                self.setup_window.show_error(str(exc))
            else:
                QMessageBox.critical(None, APP_NAME, str(exc))
            return

        port_result = check_tcp_port(config.api.host, config.api.port)
        if not port_result.available:
            self._show_setup_port_error(format_port_check_message(port_result, include_diagnostic=True))
            return

        self.pending_config = config
        self.startup_worker = DatabaseStartupWorker(
            config,
            current_super_admin_password=current_super_admin_password,
            new_super_admin_password=new_super_admin_password,
        )
        self.startup_worker.succeeded.connect(self.handle_database_ready)
        self.startup_worker.failed.connect(self.handle_database_failed)
        self.startup_worker.finished.connect(self._clear_startup_worker)
        self.startup_worker.start()

    def handle_database_ready(self) -> None:
        """Save config, install/repair the service, then start it."""

        config = self.pending_config
        if config is None:
            return

        port_result = check_tcp_port(config.api.host, config.api.port)
        if not port_result.available:
            self._show_setup_port_error(
                tr(
                    "coordinator.port_no_longer_available",
                    message=format_port_check_message(port_result, include_diagnostic=True),
                )
            )
            return

        try:
            self.config_manager.save(config)
        except Exception as exc:
            if self.setup_window is not None:
                self.setup_window.show_error(tr("coordinator.config_save_failed", message=exc))
            else:
                QMessageBox.critical(None, APP_NAME, tr("coordinator.config_save_failed_short", message=exc))
            return

        if self.setup_window is not None:
            self.setup_window.show_message(tr("setup.db_ready"), "info")

        self._run_service_action(
            lambda: self._start_service_for_config(config),
            success=lambda _result: self.handle_service_started_from_setup(config),
            failure=self.handle_setup_service_failed,
        )

    def handle_database_failed(self, message: str) -> None:
        """Show database bootstrap errors to the operator."""

        if self.setup_window is not None:
            self.setup_window.show_error(message)
            return

        QMessageBox.critical(None, APP_NAME, message)
        self.show_setup(tr("coordinator.saved_config_failed", message=message))

    def handle_service_started_from_setup(self, config: AppConfig) -> None:
        """Close setup and show the running service window."""

        if self.setup_window is not None:
            self.setup_window.close()
            self.setup_window = None

        self.show_summary(config)
        if self.summary_window is not None:
            self.summary_window.mark_running()

    def handle_setup_service_failed(self, message: str) -> None:
        """Show service startup failure after a successful database bootstrap."""

        self._stop_service_after_setup_failure()

        config = self.pending_config
        port_result = check_tcp_port(config.api.host, config.api.port) if config is not None else None
        is_bind_failure = port_result is not None and (
            port_result.is_bind_problem or is_port_bind_error_message(message)
        )
        if is_bind_failure and port_result is not None:
            bind_message = (
                format_port_check_message(port_result, include_diagnostic=True)
                if port_result.is_bind_problem
                else message
            )
            detail = tr("coordinator.bind_failed_after_save", message=bind_message)
        else:
            detail = tr("coordinator.api_failed_after_save", message=message)

        if self.setup_window is not None:
            if is_bind_failure:
                self.setup_window.show_port_error(detail)
            else:
                self.setup_window.show_error(detail)
            return

        QMessageBox.critical(None, APP_NAME, detail)

    def _show_setup_port_error(self, message: str) -> None:
        """Show a setup port error in both the footer and the API port row."""

        if self.setup_window is not None:
            self.setup_window.show_port_error(message)
            return

        QMessageBox.critical(None, APP_NAME, message)

    def _stop_service_after_setup_failure(self) -> None:
        """Best-effort service stop so a retry can use a different API port."""

        try:
            self.service_controller.stop_service()
        except Exception:
            pass

    def refresh_service_status(self) -> None:
        """Query Windows and update the summary window state."""

        if self.summary_window is None:
            return
        if self.service_worker is not None and self.service_worker.isRunning():
            return

        try:
            status = self.service_controller.get_status()
        except Exception as exc:
            self.summary_window.mark_error(str(exc))
            return

        self.apply_service_status(status)

    def apply_service_status(self, status: ServiceStatus) -> None:
        """Apply a queried service state to the summary window."""

        if self.summary_window is None:
            return

        if status.run_state == ServiceRunState.RUNNING:
            self.summary_window.mark_running()
        elif status.run_state == ServiceRunState.START_PENDING:
            self.summary_window.mark_starting()
        elif status.run_state == ServiceRunState.STOP_PENDING:
            self.summary_window.mark_stopping()
        elif status.run_state == ServiceRunState.STOPPED:
            self.summary_window.mark_stopped(status)
        elif status.run_state == ServiceRunState.NOT_INSTALLED:
            self.summary_window.mark_not_installed(status)
        else:
            self.summary_window.mark_error(f"Windows service state is {status.run_state.value}.")

    def start_connection(self) -> None:
        """Enable autostart, start the Windows service, and wait for API health."""

        if self.summary_window is None:
            return

        config = self.summary_window.config
        port_result = check_tcp_port(config.api.host, config.api.port)
        if not port_result.available:
            self.summary_window.show_update_error(format_port_check_message(port_result, include_diagnostic=True))
            return

        self.summary_window.mark_starting()
        self._run_service_action(
            lambda: self._start_service_for_config(config),
            success=lambda _result: self._mark_service_running(),
            failure=self._mark_service_error,
        )

    def stop_connection(self) -> None:
        """Stop and disable the Windows service after the operator clicks Stop Connection."""

        if self.summary_window is None:
            return

        self.summary_window.mark_stopping()
        self._run_service_action(
            self.service_controller.stop_and_disable,
            success=lambda _result: self._mark_service_stopped(),
            failure=self._mark_service_error,
        )

    def handle_summary_config_update(self, config: AppConfig) -> None:
        """Persist a summary-window config edit and stop the running service if needed."""

        if self.summary_window is None:
            return

        was_running = self.summary_window.is_running
        api_changed = config.api != self.summary_window.config.api
        if api_changed and not was_running:
            port_result = check_tcp_port(config.api.host, config.api.port)
            if not port_result.available:
                self.summary_window.show_update_error(
                    format_port_check_message(port_result, include_diagnostic=True)
                )
                return

        self.summary_window.set_updates_enabled(False)

        try:
            self.config_manager.save(config)
        except Exception as exc:
            self.summary_window.show_update_error(tr("coordinator.config_save_update_failed", message=exc))
            return

        self.summary_window.set_config(config)
        if was_running:
            self.summary_window.show_update_message(tr("summary.update_stopping"), "info")
            self.summary_window.mark_stopping()
            self._run_service_action(
                self.service_controller.stop_and_disable,
                success=lambda _result: self._handle_summary_update_stopped(),
                failure=self._handle_summary_update_stop_failed,
            )
            return

        self.summary_window.show_update_message(tr("summary.update_saved"), "success")
        self.summary_window.set_updates_enabled(True)

    def handle_summary_password_update_requested(self, current_password: str, new_password: str) -> None:
        """Rotate the Super Admin password from the running summary window."""

        if self.summary_window is None:
            return
        if self.startup_worker is not None and self.startup_worker.isRunning():
            self.summary_window.show_update_error(tr("coordinator.another_update_running"))
            return

        was_running = self.summary_window.is_running
        self.summary_window.set_updates_enabled(False)
        self.summary_window.show_update_message(tr("summary.password_updating"), "info")
        self.startup_worker = DatabaseStartupWorker(
            self.summary_window.config,
            current_super_admin_password=current_password,
            new_super_admin_password=new_password,
        )
        self.startup_worker.succeeded.connect(
            lambda was_running=was_running: self._handle_summary_password_updated(was_running)
        )
        self.startup_worker.failed.connect(self._handle_summary_password_update_failed)
        self.startup_worker.finished.connect(self._clear_startup_worker)
        self.startup_worker.start()

    def _handle_summary_password_updated(self, was_running: bool) -> None:
        """Handle a successful Super Admin password update."""

        if self.summary_window is None:
            return

        if was_running:
            self.summary_window.show_update_message(tr("summary.password_stopping"), "info")
            self.summary_window.mark_stopping()
            self._run_service_action(
                self.service_controller.stop_and_disable,
                success=lambda _result: self._handle_summary_update_stopped(),
                failure=self._handle_summary_update_stop_failed,
            )
            return

        self.summary_window.show_update_message(tr("summary.password_updated"), "success")
        self.summary_window.set_updates_enabled(True)

    def _handle_summary_password_update_failed(self, message: str) -> None:
        """Show a Super Admin password update failure."""

        if self.summary_window is not None:
            self.summary_window.show_update_error(tr("summary.password_failed", message=message))

    def _handle_summary_update_stopped(self) -> None:
        """Update the summary after an edit forces the service to stop."""

        if self.summary_window is not None:
            self.summary_window.mark_stopped()
            self.summary_window.show_update_message(tr("summary.update_stopped"), "success")
            self.summary_window.set_updates_enabled(True)

    def _handle_summary_update_stop_failed(self, message: str) -> None:
        """Show a failure to stop the service after a successful edit."""

        if self.summary_window is not None:
            self.summary_window.mark_error(tr("summary.service_stop_failed_status", message=message))
            self.summary_window.show_update_error(
                tr("summary.service_stop_failed", message=message)
            )

    def _mark_service_running(self) -> None:
        """Update the summary after a successful service start."""

        if self.summary_window is not None:
            self.summary_window.mark_running()

    def _start_service_for_config(self, config: AppConfig) -> None:
        """Prepare DB permissions, then start the Windows service."""

        port_result = check_tcp_port(config.api.host, config.api.port)
        if not port_result.available:
            raise RuntimeError(format_port_check_message(port_result, include_diagnostic=True))

        self.service_controller.ensure_installed()
        grant_windows_service_database_access(config)
        self.service_controller.start_and_wait_for_health(config)

    def _mark_service_stopped(self) -> None:
        """Update the summary after a successful service stop."""

        if self.summary_window is not None:
            self.summary_window.mark_stopped()

    def _mark_service_error(self, message: str) -> None:
        """Display service-control errors in the summary window."""

        if self.summary_window is not None:
            self.summary_window.mark_error(message)
        QMessageBox.critical(None, APP_NAME, message)

    def _run_service_action(
        self,
        action: Callable[[], object],
        success: Callable[[object], None],
        failure: Callable[[str], None],
    ) -> None:
        """Run one blocking service action at a time."""

        if self.service_worker is not None and self.service_worker.isRunning():
            return

        self.service_worker = ServiceActionWorker(action)
        self.service_worker.succeeded.connect(success)
        self.service_worker.failed.connect(failure)
        self.service_worker.finished.connect(self._clear_service_worker)
        self.service_worker.start()

    def _clear_startup_worker(self) -> None:
        """Release finished setup worker references."""

        self.startup_worker = None

    def _clear_service_worker(self) -> None:
        """Release finished service worker references."""

        self.service_worker = None

    def _start_service_status_polling(self) -> None:
        """Start live Windows service status refresh while summary is visible."""

        if not self.service_status_timer.isActive():
            self.service_status_timer.start()

    def _stop_service_status_polling(self) -> None:
        """Stop live Windows service status refresh."""

        if self.service_status_timer.isActive():
            self.service_status_timer.stop()

    def shutdown(self) -> None:
        """Best-effort cleanup when the Qt application exits."""

        self._stop_service_status_polling()
        for worker in (self.startup_worker, self.service_worker):
            if worker is not None and worker.isRunning():
                worker.wait(1000)


def run_desktop_app() -> None:
    """Run the PyQt6 desktop application."""

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    coordinator = ApplicationCoordinator(app, ConfigManager())
    coordinator.start()
    sys.exit(app.exec())

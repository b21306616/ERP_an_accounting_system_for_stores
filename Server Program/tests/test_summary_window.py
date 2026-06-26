"""Tests for the running summary window and update flow."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig
from server_app.core.constants import APP_NAME, DEFAULT_ODBC_DRIVER
from server_app.core.network import PortCheckResult, PortCheckStatus
from server_app.gui.i18n import format_port_check_message, set_language
from server_app.gui.main import ApplicationCoordinator
from server_app.gui.summary_window import SummaryWindow
from server_app.service_control import ServiceRunState, ServiceStartType, ServiceStatus


def make_config(auth_mode: str = "sql") -> AppConfig:
    """Return a representative saved setup config."""

    return AppConfig(
        database=DatabaseConfig(
            server="SERVER\\SQLEXPRESS",
            database="ERPAccounting",
            driver=DEFAULT_ODBC_DRIVER,
            auth_mode=auth_mode,  # type: ignore[arg-type]
            username="sa" if auth_mode == "sql" else None,
            password="secret" if auth_mode == "sql" else None,
            trust_server_certificate=False,
        ),
        api=ApiConfig(host="127.0.0.1", port=8123),
        jwt_secret="jwt-secret",
    )


def make_port_result(status: PortCheckStatus, message: str) -> PortCheckResult:
    """Return a representative port check result for coordinator tests."""

    return PortCheckResult(
        host="127.0.0.1",
        port=8123,
        bind_host="127.0.0.1",
        status=status,
        message=message,
    )


class FakeConfigManager:
    """Record config saves without touching real machine-wide config."""

    def __init__(self) -> None:
        self.saved_configs: list[AppConfig] = []

    def save(self, config: AppConfig) -> None:
        self.saved_configs.append(config)


class FakeServiceController:
    """Record service stop requests."""

    def __init__(self) -> None:
        self.stop_calls = 0
        self.admin_checks = 0

    def require_admin(self) -> None:
        self.admin_checks += 1

    def stop_and_disable(self) -> None:
        self.stop_calls += 1

    def stop_service(self) -> None:
        self.stop_calls += 1


class FakeStatusServiceController:
    """Return a scripted sequence of service statuses."""

    def __init__(self, statuses: list[ServiceStatus]) -> None:
        self.statuses = statuses
        self.calls = 0

    def get_status(self) -> ServiceStatus:
        index = min(self.calls, len(self.statuses) - 1)
        self.calls += 1
        return self.statuses[index]


class SummaryWindowTests(unittest.TestCase):
    """Validate the editable running summary UI."""

    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        set_language("en", persist=False)

    def create_window(self, config: AppConfig | None = None) -> SummaryWindow:
        window = SummaryWindow(config or make_config())
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)
        return window

    def test_displays_saved_setup_values(self) -> None:
        window = self.create_window()

        self.assertIn("http://127.0.0.1:8123", window.base_url_label.text())
        self.assertIn("http://127.0.0.1:8123/docs", window.docs_url_label.text())
        self.assertEqual(window.value_labels["database.server"].text(), "SERVER\\SQLEXPRESS")
        self.assertEqual(window.value_labels["database.database"].text(), "ERPAccounting")
        self.assertEqual(window.value_labels["database.auth_mode"].text(), "SQL Login")
        self.assertEqual(window.value_labels["database.username"].text(), "sa")
        self.assertEqual(window.value_labels["database.password"].text(), "Saved (hidden)")
        self.assertEqual(window.value_labels["database.trust_server_certificate"].text(), "No")
        self.assertEqual(window.value_labels["api.host"].text(), "127.0.0.1")
        self.assertEqual(window.value_labels["api.port"].text(), "8123")

    def test_updated_config_copies_and_validates_field_updates(self) -> None:
        window = self.create_window()

        updated = window._updated_config("api.port", 9000)

        self.assertEqual(updated.api.port, 9000)
        self.assertEqual(window.config.api.port, 8123)
        window._validate_config(updated)

        windows_auth = window._updated_config("database.auth_mode", "windows")
        self.assertEqual(windows_auth.database.auth_mode, "windows")
        self.assertIsNone(windows_auth.database.username)
        self.assertIsNone(windows_auth.database.password)
        window._validate_config(windows_auth)

    def test_validation_rejects_sql_login_without_credentials(self) -> None:
        window = self.create_window(make_config(auth_mode="windows"))

        sql_auth = window._updated_config("database.auth_mode", "sql")

        with self.assertRaisesRegex(ValueError, "SQL username is required"):
            window._validate_config(sql_auth)

    def test_responsive_layout_switches_between_wide_and_compact(self) -> None:
        window = self.create_window()

        window.show()
        window.resize(900, 700)
        self.app.processEvents()
        self.assertFalse(window._is_compact_layout)
        self.assertIs(window.sections_layout.itemAtPosition(0, 0).widget(), window.database_group)
        self.assertIs(window.sections_layout.itemAtPosition(0, 1).widget(), window.api_group)
        self.assertIs(window.sections_layout.itemAtPosition(1, 1).widget(), window.admin_group)

        window.resize(520, 560)
        self.app.processEvents()
        self.assertTrue(window._is_compact_layout)
        self.assertIs(window.sections_layout.itemAtPosition(0, 0).widget(), window.database_group)
        self.assertIs(window.sections_layout.itemAtPosition(1, 0).widget(), window.api_group)
        self.assertIs(window.sections_layout.itemAtPosition(2, 0).widget(), window.admin_group)

    def test_service_state_methods_update_title_subtitle_and_pending_buttons(self) -> None:
        window = self.create_window()

        window.mark_running()
        self.assertEqual(window.windowTitle(), f"{APP_NAME} - Running")
        self.assertEqual(window.subtitle_label.text(), "Running")
        self.assertEqual(window.action_button.text(), "Stop Connection")

        window.mark_starting()
        self.assertEqual(window.windowTitle(), f"{APP_NAME} - Starting")
        self.assertEqual(window.subtitle_label.text(), "Starting")
        self.assertEqual(window.action_button.text(), "Starting...")

        window.mark_stopping()
        self.assertEqual(window.windowTitle(), f"{APP_NAME} - Stopping")
        self.assertEqual(window.subtitle_label.text(), "Stopping")
        self.assertEqual(window.action_button.text(), "Stopping...")

        window.mark_error("Service failed")
        self.assertEqual(window.windowTitle(), f"{APP_NAME} - Error")
        self.assertEqual(window.subtitle_label.text(), "Error")

    def test_language_switch_updates_summary_text(self) -> None:
        window = self.create_window()

        window.mark_running()
        russian_index = window.language_combo.findData("ru")
        window.language_combo.setCurrentIndex(russian_index)

        self.assertEqual(window.database_group.title(), "Подключение MSSQL")
        self.assertEqual(window.status_label.text(), "Работает")
        self.assertEqual(window.action_button.text(), "Остановить подключение")
        self.assertEqual(window.value_labels["database.auth_mode"].text(), "SQL-логин")

    def test_not_installed_status_is_distinct(self) -> None:
        window = self.create_window()

        window.mark_not_installed(
            ServiceStatus(
                installed=False,
                run_state=ServiceRunState.NOT_INSTALLED,
                start_type=ServiceStartType.UNKNOWN,
            )
        )

        self.assertFalse(window.is_running)
        self.assertEqual(window.status_label.text(), "Not installed")
        self.assertEqual(window.windowTitle(), f"{APP_NAME} - Not installed")
        self.assertEqual(window.action_button.text(), "Start Connection")


class SummaryUpdateCoordinatorTests(unittest.TestCase):
    """Validate save-and-stop behavior for running-window edits."""

    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        set_language("en", persist=False)

    def create_coordinator(self) -> tuple[ApplicationCoordinator, FakeConfigManager, FakeServiceController]:
        manager = FakeConfigManager()
        controller = FakeServiceController()
        coordinator = ApplicationCoordinator(self.app, manager, controller)  # type: ignore[arg-type]
        self.addCleanup(coordinator.shutdown)
        return coordinator, manager, controller

    def run_service_actions_immediately(self, coordinator: ApplicationCoordinator) -> None:
        def immediate_run(action: object, success: object, failure: object) -> None:
            result = action()  # type: ignore[operator]
            success(result)  # type: ignore[operator]

        coordinator._run_service_action = immediate_run  # type: ignore[method-assign]

    def test_config_update_stops_running_service_after_successful_save(self) -> None:
        coordinator, manager, controller = self.create_coordinator()
        self.run_service_actions_immediately(coordinator)
        coordinator.show_summary(make_config())
        assert coordinator.summary_window is not None
        self.addCleanup(coordinator.summary_window.close)
        coordinator.summary_window.mark_running()
        updated = coordinator.summary_window._updated_config("api.port", 9001)

        coordinator.handle_summary_config_update(updated)

        self.assertEqual(manager.saved_configs, [updated])
        self.assertEqual(controller.stop_calls, 1)
        self.assertFalse(coordinator.summary_window.is_running)
        self.assertEqual(coordinator.summary_window.action_button.text(), "Start Connection")
        self.assertEqual(coordinator.summary_window.config.api.port, 9001)

    def test_config_update_does_not_stop_when_service_is_not_running(self) -> None:
        coordinator, manager, controller = self.create_coordinator()
        self.run_service_actions_immediately(coordinator)
        coordinator.show_summary(make_config())
        assert coordinator.summary_window is not None
        self.addCleanup(coordinator.summary_window.close)
        coordinator.summary_window.mark_stopped()
        updated = coordinator.summary_window._updated_config("api.host", "0.0.0.0")

        coordinator.handle_summary_config_update(updated)

        self.assertEqual(manager.saved_configs, [updated])
        self.assertEqual(controller.stop_calls, 0)
        self.assertFalse(coordinator.summary_window.is_running)
        self.assertEqual(coordinator.summary_window.config.api.host, "0.0.0.0")

    def test_setup_request_blocks_unavailable_port_before_database_bootstrap(self) -> None:
        coordinator, manager, _controller = self.create_coordinator()
        coordinator.setup_window = MagicMock()
        blocked = make_port_result(
            PortCheckStatus.IN_USE,
            "Port 8123 is already in use on 127.0.0.1.",
        )

        with patch("server_app.gui.main.check_tcp_port", return_value=blocked):
            coordinator.handle_setup_requested(make_config(), None, "secret123")

        self.assertIsNone(coordinator.startup_worker)
        self.assertEqual(manager.saved_configs, [])
        coordinator.setup_window.show_port_error.assert_called_once_with(
            format_port_check_message(blocked, include_diagnostic=True)
        )

    def test_database_ready_rechecks_port_before_saving_config(self) -> None:
        coordinator, manager, _controller = self.create_coordinator()
        coordinator.pending_config = make_config()
        coordinator.setup_window = MagicMock()
        blocked = make_port_result(
            PortCheckStatus.ACCESS_DENIED_OR_RESERVED,
            "Windows denied access to port 8123 on 127.0.0.1.",
        )

        with patch("server_app.gui.main.check_tcp_port", return_value=blocked):
            coordinator.handle_database_ready()

        self.assertEqual(manager.saved_configs, [])
        coordinator.setup_window.show_port_error.assert_called_once()
        self.assertIn("no longer available", coordinator.setup_window.show_port_error.call_args.args[0])

    def test_setup_service_failure_does_not_guess_port_conflict_on_plain_health_timeout(self) -> None:
        coordinator, _manager, _controller = self.create_coordinator()
        coordinator.pending_config = make_config()
        coordinator.setup_window = MagicMock()
        available = make_port_result(
            PortCheckStatus.AVAILABLE,
            "Port 8123 is available on 127.0.0.1.",
        )

        with patch("server_app.gui.main.check_tcp_port", return_value=available):
            coordinator.handle_setup_service_failed(
                "Windows service started, but the API did not answer http://127.0.0.1:8123/health. "
                "Last error: timed out. The port check passed, so this does not look like a port conflict."
            )

        coordinator.setup_window.show_error.assert_called_once()
        coordinator.setup_window.show_port_error.assert_not_called()
        message = coordinator.setup_window.show_error.call_args.args[0]
        self.assertNotIn("Try a different port", message)
        self.assertNotIn("Choose a different", message)

    def test_start_connection_blocks_unavailable_port(self) -> None:
        coordinator, _manager, _controller = self.create_coordinator()
        coordinator.show_summary(make_config())
        assert coordinator.summary_window is not None
        self.addCleanup(coordinator.summary_window.close)
        coordinator.summary_window.mark_stopped()
        blocked = make_port_result(
            PortCheckStatus.IN_USE,
            "Port 8123 is already in use on 127.0.0.1.",
        )

        with patch("server_app.gui.main.check_tcp_port", return_value=blocked):
            coordinator.start_connection()

        self.assertIsNone(coordinator.service_worker)
        self.assertEqual(
            coordinator.summary_window.message_label.text(),
            format_port_check_message(blocked, include_diagnostic=True),
        )
        self.assertEqual(coordinator.summary_window.action_button.text(), "Start Connection")

    def test_stopped_summary_api_update_blocks_unavailable_port(self) -> None:
        coordinator, manager, _controller = self.create_coordinator()
        coordinator.show_summary(make_config())
        assert coordinator.summary_window is not None
        self.addCleanup(coordinator.summary_window.close)
        coordinator.summary_window.mark_stopped()
        updated = coordinator.summary_window._updated_config("api.port", 9001)
        blocked = make_port_result(
            PortCheckStatus.HOST_NOT_LOCAL,
            "Windows cannot bind the API to 127.0.0.1:9001 because that address is not assigned to this PC.",
        )

        with patch("server_app.gui.main.check_tcp_port", return_value=blocked):
            coordinator.handle_summary_config_update(updated)

        self.assertEqual(manager.saved_configs, [])
        self.assertEqual(
            coordinator.summary_window.message_label.text(),
            format_port_check_message(blocked, include_diagnostic=True),
        )

    def test_password_update_success_stops_running_service(self) -> None:
        coordinator, _manager, controller = self.create_coordinator()
        self.run_service_actions_immediately(coordinator)
        coordinator.show_summary(make_config())
        assert coordinator.summary_window is not None
        self.addCleanup(coordinator.summary_window.close)
        coordinator.summary_window.mark_running()

        coordinator._handle_summary_password_updated(was_running=True)

        self.assertEqual(controller.stop_calls, 1)
        self.assertFalse(coordinator.summary_window.is_running)
        self.assertEqual(coordinator.summary_window.action_button.text(), "Start Connection")


class SummaryServicePollingCoordinatorTests(unittest.TestCase):
    """Validate live synchronization with externally changed Windows service state."""

    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        set_language("en", persist=False)

    def create_coordinator(
        self,
        statuses: list[ServiceStatus],
    ) -> tuple[ApplicationCoordinator, FakeStatusServiceController]:
        controller = FakeStatusServiceController(statuses)
        coordinator = ApplicationCoordinator(self.app, FakeConfigManager(), controller)  # type: ignore[arg-type]
        self.addCleanup(coordinator.shutdown)
        return coordinator, controller

    def test_refresh_service_status_tracks_external_start_stop(self) -> None:
        running = ServiceStatus(True, ServiceRunState.RUNNING, ServiceStartType.AUTO)
        stopped = ServiceStatus(True, ServiceRunState.STOPPED, ServiceStartType.DISABLED)
        coordinator, controller = self.create_coordinator([running, stopped])

        coordinator.show_summary(make_config())
        assert coordinator.summary_window is not None
        self.addCleanup(coordinator.summary_window.close)

        coordinator.refresh_service_status()
        self.assertTrue(coordinator.summary_window.is_running)
        self.assertEqual(coordinator.summary_window.status_label.text(), "Running")

        coordinator.refresh_service_status()
        self.assertFalse(coordinator.summary_window.is_running)
        self.assertEqual(coordinator.summary_window.status_label.text(), "Stopped (disabled)")
        self.assertEqual(coordinator.summary_window.action_button.text(), "Start Connection")
        self.assertEqual(controller.calls, 2)

    def test_status_timer_runs_only_while_summary_is_visible(self) -> None:
        coordinator, _controller = self.create_coordinator(
            [ServiceStatus(True, ServiceRunState.STOPPED, ServiceStartType.MANUAL)]
        )

        coordinator.show_summary(make_config())
        self.assertTrue(coordinator.service_status_timer.isActive())

        with patch("server_app.gui.setup_window.pyodbc.drivers", return_value=[DEFAULT_ODBC_DRIVER]):
            coordinator.show_setup()

        self.assertFalse(coordinator.service_status_timer.isActive())
        self.assertIsNotNone(coordinator.setup_window)
        assert coordinator.setup_window is not None
        self.addCleanup(coordinator.setup_window.close)


if __name__ == "__main__":
    unittest.main()

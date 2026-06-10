"""Tests for the running summary window and update flow."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig
from server_app.core.constants import DEFAULT_ODBC_DRIVER
from server_app.gui.main import ApplicationCoordinator
from server_app.gui.summary_window import SummaryWindow


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

    def stop_and_disable(self) -> None:
        self.stop_calls += 1


class SummaryWindowTests(unittest.TestCase):
    """Validate the editable running summary UI."""

    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def create_window(self, config: AppConfig | None = None) -> SummaryWindow:
        window = SummaryWindow(config or make_config())
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)
        return window

    def test_displays_saved_setup_values(self) -> None:
        window = self.create_window()

        self.assertEqual(window.base_url_label.text(), "http://127.0.0.1:8123")
        self.assertEqual(window.docs_url_label.text(), "http://127.0.0.1:8123/docs")
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
        self.assertIs(window.sections_layout.itemAtPosition(0, 0).widget(), window.service_group)
        self.assertIs(window.sections_layout.itemAtPosition(0, 1).widget(), window.api_group)
        self.assertIs(window.sections_layout.itemAtPosition(1, 0).widget(), window.database_group)

        window.resize(520, 560)
        self.app.processEvents()
        self.assertTrue(window._is_compact_layout)
        self.assertIs(window.sections_layout.itemAtPosition(0, 0).widget(), window.service_group)
        self.assertIs(window.sections_layout.itemAtPosition(1, 0).widget(), window.database_group)
        self.assertIs(window.sections_layout.itemAtPosition(2, 0).widget(), window.api_group)
        self.assertIs(window.sections_layout.itemAtPosition(3, 0).widget(), window.admin_group)


class SummaryUpdateCoordinatorTests(unittest.TestCase):
    """Validate save-and-stop behavior for running-window edits."""

    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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


if __name__ == "__main__":
    unittest.main()

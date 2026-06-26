"""Smoke tests for the first-run setup window."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox, QSizePolicy

from server_app.core.constants import DEFAULT_ODBC_DRIVER
from server_app.core.network import PortCheckResult, PortCheckStatus
from server_app.gui.i18n import format_port_check_message, set_language
from server_app.gui.setup_window import SetupWindow


def make_port_result(status: PortCheckStatus, message: str) -> PortCheckResult:
    """Return a representative port check result for UI tests."""

    return PortCheckResult(
        host="0.0.0.0",
        port=8000,
        bind_host="",
        status=status,
        message=message,
    )


class SetupWindowTests(unittest.TestCase):
    """Validate setup UI behavior that should survive visual refactors."""

    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        set_language("en", persist=False)

    def create_window(self, error_message: str | None = None) -> SetupWindow:
        with patch("server_app.gui.setup_window.pyodbc.drivers", return_value=[DEFAULT_ODBC_DRIVER]):
            window = SetupWindow(error_message)
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)
        return window

    def test_defaults_populate_from_config(self) -> None:
        window = self.create_window()

        self.assertEqual(window.server_edit.text(), window.default_config.database.server)
        self.assertEqual(window.database_edit.text(), window.default_config.database.database)
        self.assertEqual(window.host_edit.text(), window.default_config.api.host)
        self.assertEqual(window.port_spin.value(), window.default_config.api.port)
        self.assertEqual(window.driver_combo.currentText(), DEFAULT_ODBC_DRIVER)

    def test_sql_login_fields_follow_auth_mode(self) -> None:
        window = self.create_window()

        self.assertFalse(window.username_edit.isEnabled())
        self.assertFalse(window.password_edit.isEnabled())

        sql_index = window.auth_combo.findData("sql")
        window.auth_combo.setCurrentIndex(sql_index)

        self.assertTrue(window.username_edit.isEnabled())
        self.assertTrue(window.password_edit.isEnabled())

    def test_validation_still_rejects_missing_password_values(self) -> None:
        window = self.create_window()

        with self.assertRaisesRegex(ValueError, "at least 6 characters"):
            window._build_config_from_form()

        window.new_password_edit.setText("new-secret")
        window.confirm_password_edit.setText("different")

        with self.assertRaisesRegex(ValueError, "do not match"):
            window._build_config_from_form()

    def test_responsive_layout_switches_between_wide_and_compact(self) -> None:
        window = self.create_window("Initial setup error")

        window.show()
        window.resize(900, 700)
        self.app.processEvents()
        self.assertFalse(window._is_compact_layout)
        self.assertEqual(window.MAX_CONTENT_WIDTH, 1120)
        self.assertEqual(window.header_bar.width(), window.width())
        self.assertGreater(window.header_bar.width(), window.content_widget.width())
        self.assertIs(window.header_bar.parent(), window)
        self.assertIs(window.connection_card.parent(), window.header_bar)
        self.assertLessEqual(window.content_widget.width(), window.MAX_CONTENT_WIDTH)
        self.assertTrue(
            all(label.minimumHeight() == window.DESKTOP_STEP_MIN_HEIGHT for label in window.step_labels)
        )
        self.assertIs(window.wizard_stack.currentWidget(), window.database_group)

        window.resize(520, 560)
        self.app.processEvents()
        self.assertTrue(window._is_compact_layout)
        self.assertEqual(window.header_bar.width(), window.width())
        self.assertIs(window.header_layout.itemAtPosition(0, 0).widget(), window.header_title_block)
        self.assertIs(window.header_layout.itemAtPosition(1, 0).widget(), window.header_language_block)
        self.assertIs(window.connection_card.parent(), window.header_bar)
        self.assertTrue(window.connection_card.isVisible())
        self.assertLessEqual(window.content_widget.width(), window.COMPACT_CONTENT_WIDTH)
        self.assertTrue(
            all(label.minimumHeight() == window.COMPACT_STEP_MIN_HEIGHT for label in window.step_labels)
        )
        self.assertTrue(window.message_label.isVisible())

    def test_fixed_header_contains_required_controls(self) -> None:
        window = self.create_window()

        window.show()
        self.app.processEvents()

        self.assertEqual(window.title_label.text(), "ERP Accounting Server")
        self.assertEqual(window.subtitle_label.text(), "First setup")
        self.assertIs(window.language_combo.parent(), window.header_language_block)
        self.assertTrue(window.connection_card.isAncestorOf(window.setup_status_label))
        self.assertEqual(window.setup_status_label.text(), "Ready to configure")

    def test_wizard_navigation_and_live_validation(self) -> None:
        window = self.create_window()

        window.show()
        self.app.processEvents()

        self.assertEqual(window.wizard_stack.currentIndex(), 0)
        self.assertTrue(window.next_button.isEnabled())
        self.assertFalse(window.back_button.isVisible())

        window._on_next()
        self.assertEqual(window.wizard_stack.currentIndex(), 1)
        self.assertTrue(window.back_button.isVisible())

        unavailable = make_port_result(
            PortCheckStatus.IN_USE,
            "Port 8000 is already in use on 0.0.0.0.",
        )
        with patch("server_app.gui.setup_window.check_tcp_port", return_value=unavailable):
            window._on_next()
        self.assertEqual(window.wizard_stack.currentIndex(), 1)
        self.assertFalse(window.next_button.isEnabled())

        available = make_port_result(
            PortCheckStatus.AVAILABLE,
            "Port 8000 is available on 0.0.0.0.",
        )
        with patch("server_app.gui.setup_window.check_tcp_port", return_value=available):
            window._update_port_status()
            window._on_next()
        self.assertEqual(window.wizard_stack.currentIndex(), 2)
        self.assertFalse(window.submit_button.isEnabled())

        window.new_password_edit.setText("secret123")
        window.confirm_password_edit.setText("secret123")
        self.assertTrue(window.submit_button.isEnabled())

    def test_primary_button_stays_content_sized_on_wide_windows(self) -> None:
        window = self.create_window()

        window.show()
        window.resize(1200, 800)
        self.app.processEvents()

        self.assertFalse(window._is_compact_layout)
        self.assertEqual(window.content_widget.width(), window.MAX_CONTENT_WIDTH)
        self.assertEqual(window.next_button.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Fixed)

    def test_validation_rejects_invalid_database_name(self) -> None:
        window = self.create_window()

        window.server_edit.setText("localhost")
        window.database_edit.setText("ERP;DROP")
        window.host_edit.setText("127.0.0.1")
        window.new_password_edit.setText("secret123")
        window.confirm_password_edit.setText("secret123")

        with self.assertRaisesRegex(ValueError, "semicolon"):
            window._build_config_from_form()

    def test_port_status_updates_when_port_changes(self) -> None:
        window = self.create_window()
        window.show()
        self.app.processEvents()

        unavailable = make_port_result(
            PortCheckStatus.IN_USE,
            "Port 8000 is already in use on 0.0.0.0.",
        )
        with patch("server_app.gui.setup_window.check_tcp_port", return_value=unavailable):
            window._update_port_status()
            self.app.processEvents()

        self.assertEqual(window.port_status_label.text(), format_port_check_message(unavailable))
        self.assertEqual(window.port_status_label.property("messageState"), "error")

        available = make_port_result(
            PortCheckStatus.AVAILABLE,
            "Port 5000 is available on 0.0.0.0.",
        )
        with patch("server_app.gui.setup_window.check_tcp_port", return_value=available):
            window.port_spin.setValue(5000)
            window._port_check_timer.timeout.emit()
            self.app.processEvents()

        self.assertEqual(window.port_status_label.text(), format_port_check_message(available))
        self.assertEqual(window.port_status_label.property("messageState"), "success")

    def test_submit_blocks_when_port_is_unavailable(self) -> None:
        window = self.create_window()
        window.server_edit.setText("localhost")
        window.database_edit.setText("ERPAccounting")
        window.host_edit.setText("0.0.0.0")
        window.new_password_edit.setText("secret123")
        window.confirm_password_edit.setText("secret123")

        emitted = MagicMock()
        window.setup_requested.connect(emitted)

        unavailable = make_port_result(
            PortCheckStatus.ACCESS_DENIED_OR_RESERVED,
            "Windows denied access to port 8000 on 0.0.0.0.",
        )
        with patch("server_app.gui.setup_window.check_tcp_port", return_value=unavailable), patch.object(
            QMessageBox,
            "warning",
        ) as warning_dialog:
            window._on_submit()
            self.app.processEvents()

        emitted.assert_not_called()
        warning_dialog.assert_called_once()
        self.assertEqual(window.port_status_label.text(), format_port_check_message(unavailable))

    def test_language_switch_updates_wizard_text(self) -> None:
        window = self.create_window()

        russian_index = window.language_combo.findData("ru")
        window.language_combo.setCurrentIndex(russian_index)

        self.assertEqual(window.database_group.property("titleKey"), "section.mssql")
        self.assertEqual(window.title_label.text(), "ERP Accounting Server")
        self.assertEqual(window.next_button.text(), "Далее")
        self.assertEqual(window.field_labels["database.server"].text(), "Хост/экземпляр SQL Server")


if __name__ == "__main__":
    unittest.main()

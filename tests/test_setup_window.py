"""Smoke tests for the first-run setup window."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QSizePolicy

from server_app.core.constants import DEFAULT_ODBC_DRIVER
from server_app.gui.setup_window import SetupWindow


class SetupWindowTests(unittest.TestCase):
    """Validate setup UI behavior that should survive visual refactors."""

    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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
        self.assertIs(window.sections_layout.itemAtPosition(0, 0).widget(), window.database_group)
        self.assertIs(window.sections_layout.itemAtPosition(0, 1).widget(), window.api_group)
        self.assertIs(window.sections_layout.itemAtPosition(1, 1).widget(), window.super_admin_group)

        window.resize(520, 560)
        self.app.processEvents()
        self.assertTrue(window._is_compact_layout)
        self.assertIs(window.sections_layout.itemAtPosition(0, 0).widget(), window.database_group)
        self.assertIs(window.sections_layout.itemAtPosition(1, 0).widget(), window.api_group)
        self.assertIs(window.sections_layout.itemAtPosition(2, 0).widget(), window.super_admin_group)
        self.assertTrue(window.message_label.isVisible())

    def test_primary_button_stays_content_sized_on_wide_windows(self) -> None:
        window = self.create_window()

        window.show()
        window.resize(1200, 800)
        self.app.processEvents()

        self.assertFalse(window._is_compact_layout)
        self.assertEqual(
            window.submit_button.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Fixed,
        )
        self.assertLessEqual(
            window.submit_button.width(),
            window.submit_button.sizeHint().width() + 2,
        )

    def test_validation_rejects_invalid_database_name(self) -> None:
        window = self.create_window()

        window.server_edit.setText("localhost")
        window.database_edit.setText("ERP;DROP")
        window.host_edit.setText("127.0.0.1")
        window.new_password_edit.setText("secret123")
        window.confirm_password_edit.setText("secret123")

        with self.assertRaisesRegex(ValueError, "semicolon"):
            window._build_config_from_form()


if __name__ == "__main__":
    unittest.main()

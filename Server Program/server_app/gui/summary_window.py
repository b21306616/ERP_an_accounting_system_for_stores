"""Server summary and control window."""

from __future__ import annotations

from dataclasses import replace

import pyodbc
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig
from server_app.core.constants import (
    APP_NAME,
    DEFAULT_ODBC_DRIVER,
    SUPER_ADMIN_FULL_NAME,
    SUPER_ADMIN_USERNAME,
)
from server_app.db.bootstrap import validate_database_name
from server_app.service_control import ServiceStartType, ServiceStatus


class SummaryWindow(QWidget):
    """Show connection details, editable setup values, and service controls."""

    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    config_update_requested = pyqtSignal(object)
    super_admin_password_update_requested = pyqtSignal(str, str)

    COMPACT_WIDTH = 760
    MAX_CONTENT_WIDTH = 1080
    COMPACT_CONTENT_WIDTH = 620

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.setObjectName("SummaryWindow")
        self.setWindowTitle(f"{APP_NAME} - Starting")
        self.setMinimumSize(500, 520)
        self._is_compact_layout: bool | None = None
        self._updates_enabled = True
        self.is_running = False
        self.value_labels: dict[str, QLabel] = {}
        self.update_buttons: dict[str, QPushButton] = {}

        self.status_label = QLabel("Starting...")
        self.subtitle_label = QLabel("Starting")
        self.base_url_label = QLabel()
        self.docs_url_label = QLabel()
        self.database_label = QLabel()
        self.auth_label = QLabel()
        self.message_label = QLabel("")
        self.action_button = QPushButton("Stop Connection")
        self.stop_button = self.action_button

        self._build_ui()
        self._connect_signals()
        self.set_config(config)
        self.mark_starting()

    @property
    def base_url(self) -> str:
        """Return the API v1 URL clients can use to reach this server."""

        return f"{self._service_root_url()}/api/v1"

    def _service_root_url(self) -> str:
        """Return the root HTTP URL for service-local links such as Swagger."""

        host = self.config.api.host
        display_host = "localhost" if host == "0.0.0.0" else host
        return f"http://{display_host}:{self.config.api.port}"

    def _build_ui(self) -> None:
        """Build a responsive summary and control surface."""

        self._apply_stylesheet()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("SummaryScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_host = QWidget()
        scroll_host.setObjectName("SummaryScrollHost")
        scroll_area.setWidget(scroll_host)

        scroll_layout = QHBoxLayout(scroll_host)
        scroll_layout.setContentsMargins(24, 24, 24, 28)
        scroll_layout.setSpacing(0)
        scroll_layout.addStretch(1)

        self.content_widget = QWidget()
        self.content_widget.setObjectName("SummaryContent")
        self.content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        scroll_layout.addWidget(self.content_widget)
        scroll_layout.addStretch(1)

        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header = QWidget()
        header.setObjectName("SummaryHeader")
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        title_label = QLabel("ERP Accounting Server")
        title_label.setObjectName("SummaryTitle")
        self.subtitle_label.setObjectName("SummarySubtitle")
        title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.subtitle_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_layout.addWidget(title_label)
        header_layout.addWidget(self.subtitle_label)
        content_layout.addWidget(header)

        self.service_group = self._build_connection_card()
        content_layout.addWidget(self.service_group)

        self.database_group = QGroupBox("MSSQL connection")
        database_layout = QGridLayout(self.database_group)
        self._prepare_summary_layout(database_layout)
        self._add_update_row(database_layout, 0, "SQL Server host/instance", "database.server")
        self._add_update_row(database_layout, 1, "Database name", "database.database")
        self._add_update_row(database_layout, 2, "ODBC driver", "database.driver")
        self._add_update_row(database_layout, 3, "Authentication", "database.auth_mode")
        self._add_update_row(database_layout, 4, "SQL username", "database.username")
        self._add_update_row(database_layout, 5, "SQL password", "database.password")
        self._add_update_row(database_layout, 6, "Trust SQL Server certificate", "database.trust_server_certificate")
        self.database_label = self.value_labels["database.database"]
        self.auth_label = self.value_labels["database.auth_mode"]

        self.api_group = QGroupBox("API server")
        api_layout = QGridLayout(self.api_group)
        self._prepare_summary_layout(api_layout)
        self._add_update_row(api_layout, 0, "Bind host/IP", "api.host")
        self._add_update_row(api_layout, 1, "Port", "api.port")

        self.admin_group = QGroupBox("Super Admin account")
        admin_layout = QGridLayout(self.admin_group)
        self._prepare_summary_layout(admin_layout)
        self._add_static_row(admin_layout, 0, "Username", QLabel(SUPER_ADMIN_USERNAME))
        self._add_static_row(admin_layout, 1, "Full name", QLabel(SUPER_ADMIN_FULL_NAME))
        self._add_update_row(admin_layout, 2, "Password", "super_admin.password")

        self.sections_layout = QGridLayout()
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setHorizontalSpacing(18)
        self.sections_layout.setVerticalSpacing(18)
        content_layout.addLayout(self.sections_layout)
        content_layout.addStretch(1)

        footer = QWidget()
        footer.setObjectName("SummaryFooter")
        self.footer_layout = QGridLayout(footer)
        self.footer_layout.setContentsMargins(24, 14, 24, 14)
        self.footer_layout.setHorizontalSpacing(18)
        self.footer_layout.setVerticalSpacing(10)

        self.message_label.setObjectName("FooterMessage")
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(False)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.action_button.setObjectName("PrimaryButton")
        self.action_button.setMinimumHeight(42)
        self.action_button.setMinimumWidth(190)
        self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_button.setEnabled(False)

        main_layout.addWidget(scroll_area, 1)
        main_layout.addWidget(footer, 0)
        self._apply_responsive_layout()

    def _build_connection_card(self) -> QFrame:
        """Build the redesigned connection summary card."""

        card = QFrame()
        card.setObjectName("ConnectionCard")
        card.setProperty("serviceState", "neutral")
        self.connection_card = card

        outer_layout = QHBoxLayout(card)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        accent = QFrame()
        accent.setObjectName("ConnectionAccent")
        accent.setFixedWidth(4)
        self.connection_accent = accent
        outer_layout.addWidget(accent)

        content = QWidget()
        content.setObjectName("ConnectionCardContent")
        outer_layout.addWidget(content, 1)

        card_layout = QVBoxLayout(content)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        card_title = QLabel("Connection")
        card_title.setObjectName("CardTitle")

        self.status_label.setObjectName("ServiceStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header_layout.addWidget(card_title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.status_label)

        card_layout.addLayout(header_layout)

        divider = QFrame()
        divider.setObjectName("CardDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        card_layout.addWidget(divider)

        details_layout = QGridLayout()
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setHorizontalSpacing(16)
        details_layout.setVerticalSpacing(10)
        details_layout.setColumnStretch(0, 0)
        details_layout.setColumnStretch(1, 1)
        details_layout.setColumnStretch(2, 0)

        api_title = QLabel("API base URL")
        api_title.setObjectName("CardRowTitle")
        self.base_url_label.setObjectName("CardRowValue")
        self.base_url_label.setWordWrap(True)
        self.base_url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.base_url_label.setOpenExternalLinks(True)

        copy_api_btn = QPushButton("Copy")
        copy_api_btn.setObjectName("CardCopyButton")
        copy_api_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_api_btn.clicked.connect(lambda: self._copy_to_clipboard(self.base_url, copy_api_btn))

        details_layout.addWidget(api_title, 0, 0)
        details_layout.addWidget(self.base_url_label, 0, 1)
        details_layout.addWidget(copy_api_btn, 0, 2)

        docs_title = QLabel("Swagger docs")
        docs_title.setObjectName("CardRowTitle")
        self.docs_url_label.setObjectName("CardRowValue")
        self.docs_url_label.setWordWrap(True)
        self.docs_url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.docs_url_label.setOpenExternalLinks(True)

        copy_docs_btn = QPushButton("Copy")
        copy_docs_btn.setObjectName("CardCopyButton")
        copy_docs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_docs_btn.clicked.connect(lambda: self._copy_to_clipboard(f"{self._service_root_url()}/docs", copy_docs_btn))

        details_layout.addWidget(docs_title, 1, 0)
        details_layout.addWidget(self.docs_url_label, 1, 1)
        details_layout.addWidget(copy_docs_btn, 1, 2)

        card_layout.addLayout(details_layout)
        return card

    def _copy_to_clipboard(self, text: str, button: QPushButton) -> None:
        """Copy text to clipboard and show feedback."""

        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

        button.setText("Copied!")
        button.setProperty("copiedState", True)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

        QTimer.singleShot(2000, lambda: self._reset_copy_button(button))

    def _reset_copy_button(self, button: QPushButton) -> None:
        """Reset copy button text and state."""

        button.setText("Copy")
        button.setProperty("copiedState", False)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _prepare_summary_layout(self, layout: QGridLayout) -> None:
        """Apply consistent row spacing for summary sections."""

        layout.setContentsMargins(0, 8, 0, 0)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(12)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 0)

    def _add_static_row(self, layout: QGridLayout, row: int, title: str, value_label: QLabel) -> None:
        """Add a read-only row to a summary section."""

        title_label = QLabel(title)
        title_label.setObjectName("RowTitle")
        value_label.setObjectName("RowValue")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title_label, row, 0)
        layout.addWidget(value_label, row, 1, 1, 2)

    def _add_update_row(self, layout: QGridLayout, row: int, title: str, field_id: str) -> None:
        """Add a summary row with an update action."""

        title_label = QLabel(title)
        title_label.setObjectName("RowTitle")
        value_label = QLabel()
        value_label.setObjectName("RowValue")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        button = QPushButton("Update this field")
        button.setObjectName("InlineButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, name=field_id: self._on_update_field(name))
        layout.addWidget(title_label, row, 0)
        layout.addWidget(value_label, row, 1)
        layout.addWidget(button, row, 2, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.value_labels[field_id] = value_label
        self.update_buttons[field_id] = button

    def _connect_signals(self) -> None:
        """Connect user actions to summary-window signals."""

        self.action_button.clicked.connect(self._on_action_clicked)

    def _on_action_clicked(self) -> None:
        """Emit the correct action for the current service state."""

        if self.is_running:
            self.stop_requested.emit()
        else:
            self.start_requested.emit()

    def set_config(self, config: AppConfig) -> None:
        """Replace the displayed config after a successful save."""

        self.config = config
        url = self.base_url
        docs_url = f"{self._service_root_url()}/docs"
        link_style = "color: #1d4ed8; text-decoration: none; font-weight: 600;"
        self.base_url_label.setText(f'<a href="{url}" style="{link_style}">{url}</a>')
        self.docs_url_label.setText(f'<a href="{docs_url}" style="{link_style}">{docs_url}</a>')
        self.value_labels["database.server"].setText(config.database.server)
        self.value_labels["database.database"].setText(config.database.database)
        self.value_labels["database.driver"].setText(config.database.driver)
        self.value_labels["database.auth_mode"].setText(self._display_auth_mode(config.database.auth_mode))
        self.value_labels["database.username"].setText(config.database.username or "Not set")
        self.value_labels["database.password"].setText(
            "Saved (hidden)" if config.database.password else "Not set"
        )
        self.value_labels["database.trust_server_certificate"].setText(
            "Yes" if config.database.trust_server_certificate else "No"
        )
        self.value_labels["api.host"].setText(config.api.host)
        self.value_labels["api.port"].setText(str(config.api.port))
        self.value_labels["super_admin.password"].setText("Configured (hidden)")

    def _display_auth_mode(self, auth_mode: str) -> str:
        """Return the user-facing auth-mode label."""

        return "SQL Login" if auth_mode == "sql" else "Windows Authentication"

    def _on_update_field(self, field_id: str) -> None:
        """Prompt for a field update and emit the validated result."""

        if field_id == "super_admin.password":
            credentials = self._prompt_super_admin_password()
            if credentials is not None:
                current_password, new_password = credentials
                self.super_admin_password_update_requested.emit(current_password, new_password)
            return

        value = self._prompt_field_value(field_id)
        if value is None:
            return

        try:
            config = self._updated_config(field_id, value)
            self._validate_config(config)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid update", str(exc))
            return

        self.config_update_requested.emit(config)

    def _prompt_field_value(self, field_id: str) -> object | None:
        """Open the right dialog for the selected config field."""

        database = self.config.database
        api = self.config.api
        if field_id == "database.server":
            return self._prompt_text("Update SQL Server host/instance", "SQL Server host/instance", database.server)
        if field_id == "database.database":
            return self._prompt_text("Update database name", "Database name", database.database)
        if field_id == "database.driver":
            return self._prompt_choice("Update ODBC driver", "ODBC driver", self._driver_options(), database.driver)
        if field_id == "database.auth_mode":
            return self._prompt_choice(
                "Update authentication",
                "Authentication",
                [("Windows Authentication", "windows"), ("SQL Login", "sql")],
                database.auth_mode,
            )
        if field_id == "database.username":
            return self._prompt_text("Update SQL username", "SQL username", database.username or "")
        if field_id == "database.password":
            return self._prompt_text(
                "Update SQL password",
                "New SQL password",
                "",
                password=True,
                placeholder="Leave blank to clear when Windows Authentication is used",
            )
        if field_id == "database.trust_server_certificate":
            return self._prompt_checkbox(
                "Update certificate trust",
                "Trust SQL Server certificate",
                database.trust_server_certificate,
            )
        if field_id == "api.host":
            return self._prompt_text("Update API bind host/IP", "Bind host/IP", api.host)
        if field_id == "api.port":
            return self._prompt_port(api.port)
        raise ValueError(f"Unknown update field: {field_id}")

    def _updated_config(self, field_id: str, value: object) -> AppConfig:
        """Return a copied config with one updated field."""

        database = replace(self.config.database)
        api = replace(self.config.api)

        if field_id == "database.server":
            database = replace(database, server=str(value).strip())
        elif field_id == "database.database":
            database = replace(database, database=str(value).strip())
        elif field_id == "database.driver":
            database = replace(database, driver=str(value).strip())
        elif field_id == "database.auth_mode":
            auth_mode = str(value)
            if auth_mode == "windows":
                database = replace(database, auth_mode="windows", username=None, password=None)
            else:
                database = replace(database, auth_mode="sql")
        elif field_id == "database.username":
            username = str(value).strip() or None
            database = replace(database, username=username)
        elif field_id == "database.password":
            password = str(value) or None
            database = replace(database, password=password)
        elif field_id == "database.trust_server_certificate":
            database = replace(database, trust_server_certificate=bool(value))
        elif field_id == "api.host":
            api = replace(api, host=str(value).strip())
        elif field_id == "api.port":
            api = replace(api, port=int(value))
        else:
            raise ValueError(f"Unknown update field: {field_id}")

        return AppConfig(database=database, api=api, jwt_secret=self.config.jwt_secret)

    def _validate_config(self, config: AppConfig) -> None:
        """Validate updated config values before saving."""

        if not config.database.server:
            raise ValueError("SQL Server host/instance is required.")
        if not config.database.database:
            raise ValueError("Database name is required.")
        validate_database_name(config.database.database)
        if not config.database.driver:
            raise ValueError("ODBC driver is required.")
        if config.database.auth_mode == "sql" and not config.database.username:
            raise ValueError("SQL username is required for SQL Login mode.")
        if config.database.auth_mode == "sql" and not config.database.password:
            raise ValueError("SQL password is required for SQL Login mode.")
        if not config.api.host:
            raise ValueError("API bind host/IP is required.")
        if not 1 <= config.api.port <= 65535:
            raise ValueError("API port must be between 1 and 65535.")

    def _driver_options(self) -> list[tuple[str, str]]:
        """Return available ODBC drivers with the current/default values included."""

        drivers = list(pyodbc.drivers())
        for driver in (self.config.database.driver, DEFAULT_ODBC_DRIVER):
            if driver and driver not in drivers:
                drivers.insert(0, driver)
        return [(driver, driver) for driver in drivers]

    def _prompt_text(
        self,
        title: str,
        label: str,
        current: str,
        *,
        password: bool = False,
        placeholder: str = "",
    ) -> str | None:
        """Prompt for a text value."""

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        form = QFormLayout(dialog)
        edit = QLineEdit(current)
        edit.setPlaceholderText(placeholder)
        if password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(label, edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return edit.text()

    def _prompt_choice(
        self,
        title: str,
        label: str,
        options: list[tuple[str, str]],
        current: str,
    ) -> str | None:
        """Prompt for a choice value."""

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        form = QFormLayout(dialog)
        combo = QComboBox()
        for display, value in options:
            combo.addItem(display, value)
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)
        form.addRow(label, combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return str(combo.currentData())

    def _prompt_checkbox(self, title: str, label: str, current: bool) -> bool | None:
        """Prompt for a boolean value."""

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        check = QCheckBox(label)
        check.setChecked(current)
        layout.addWidget(check)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return check.isChecked()

    def _prompt_port(self, current: int) -> int | None:
        """Prompt for the API port."""

        dialog = QDialog(self)
        dialog.setWindowTitle("Update API port")
        form = QFormLayout(dialog)
        spin = QSpinBox()
        spin.setRange(1, 65535)
        spin.setValue(current)
        form.addRow("Port", spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return spin.value()

    def _prompt_super_admin_password(self) -> tuple[str, str] | None:
        """Prompt for a Super Admin password rotation."""

        while True:
            dialog = QDialog(self)
            dialog.setWindowTitle("Update Super Admin password")
            form = QFormLayout(dialog)
            current_edit = QLineEdit()
            new_edit = QLineEdit()
            confirm_edit = QLineEdit()
            for edit in (current_edit, new_edit, confirm_edit):
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow("Current password", current_edit)
            form.addRow("New password", new_edit)
            form.addRow("Confirm new password", confirm_edit)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None

            current_password = current_edit.text()
            new_password = new_edit.text()
            if not current_password:
                QMessageBox.warning(self, "Invalid password update", "Current Super Admin password is required.")
                continue
            if len(new_password) < 6:
                QMessageBox.warning(
                    self,
                    "Invalid password update",
                    "Super Admin password must contain at least 6 characters.",
                )
                continue
            if new_password != confirm_edit.text():
                QMessageBox.warning(
                    self,
                    "Invalid password update",
                    "Super Admin password and confirmation do not match.",
                )
                continue
            return current_password, new_password

    def set_updates_enabled(self, enabled: bool) -> None:
        """Enable or disable field updates during background operations."""

        self._updates_enabled = enabled
        for button in self.update_buttons.values():
            button.setEnabled(enabled)
        if not enabled:
            self.action_button.setEnabled(False)
        elif self.status_label.text() not in {"Starting...", "Stopping..."}:
            self.action_button.setEnabled(True)

    def show_update_message(self, message: str, state: str = "info") -> None:
        """Show a footer update message."""

        self.message_label.setProperty("messageState", state)
        self.message_label.setText(message)
        self.message_label.setVisible(bool(message))
        self.message_label.style().unpolish(self.message_label)
        self.message_label.style().polish(self.message_label)
        self.message_label.update()

    def show_update_error(self, message: str) -> None:
        """Show a footer update error."""

        self.show_update_message(message, "error")
        self.set_updates_enabled(True)

    def _set_window_state(self, label: str) -> None:
        """Update the summary header and OS window title."""

        self.subtitle_label.setText(label)
        self.setWindowTitle(f"{APP_NAME} - {label}")

    def _set_service_status(self, text: str, state: str, window_state: str) -> None:
        """Update the styled service status value."""

        self._set_window_state(window_state)
        self.status_label.setProperty("serviceState", state)
        self.status_label.setText(text)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.update()

        self.connection_card.setProperty("serviceState", state)
        self.connection_card.style().unpolish(self.connection_card)
        self.connection_card.style().polish(self.connection_card)
        self.connection_card.update()

    def mark_running(self) -> None:
        """Update the UI after the Windows service starts."""

        self.is_running = True
        self._set_service_status("Running", "running", "Running")
        self.action_button.setText("Stop Connection")
        self.action_button.setEnabled(self._updates_enabled)

    def mark_starting(self) -> None:
        """Update the UI while service startup is in progress."""

        self.is_running = False
        self._set_service_status("Starting...", "neutral", "Starting")
        self.action_button.setText("Starting...")
        self.action_button.setEnabled(False)

    def mark_stopping(self) -> None:
        """Update the UI while shutdown is in progress."""

        self.is_running = True
        self._set_service_status("Stopping...", "warning", "Stopping")
        self.action_button.setText("Stopping...")
        self.action_button.setEnabled(False)

    def mark_stopped(self, status: ServiceStatus | None = None) -> None:
        """Update the UI after the service is stopped or disabled."""

        self.is_running = False
        if status is not None and status.start_type == ServiceStartType.DISABLED:
            text = "Stopped (disabled)"
        elif status is not None and status.needs_repair:
            text = "Stopped (service needs repair)"
        else:
            text = "Stopped"

        self._set_service_status(text, "warning", "Stopped")
        self.action_button.setText("Start Connection")
        self.action_button.setEnabled(self._updates_enabled)

    def mark_not_installed(self, status: ServiceStatus | None = None) -> None:
        """Update the UI when the Windows service is not registered."""

        self.is_running = False
        self._set_service_status("Not installed", "warning", "Not installed")
        self.action_button.setText("Start Connection")
        self.action_button.setEnabled(self._updates_enabled)

    def mark_error(self, message: str) -> None:
        """Show a startup or runtime error."""

        self.is_running = False
        self._set_service_status(message, "error", "Error")
        self.action_button.setText("Start Connection")
        self.action_button.setEnabled(self._updates_enabled)

    def _apply_responsive_layout(self) -> None:
        """Reflow section cards and footer actions for the current width."""

        compact = self.width() < self.COMPACT_WIDTH
        self._update_content_width(compact)
        if compact == self._is_compact_layout:
            return

        self._is_compact_layout = compact
        for widget in (self.database_group, self.api_group, self.admin_group):
            self.sections_layout.removeWidget(widget)
        self.footer_layout.removeWidget(self.message_label)
        self.footer_layout.removeWidget(self.action_button)

        if compact:
            self.sections_layout.addWidget(
                self.database_group, 0, 0, alignment=Qt.AlignmentFlag.AlignTop
            )
            self.sections_layout.addWidget(
                self.api_group, 1, 0, alignment=Qt.AlignmentFlag.AlignTop
            )
            self.sections_layout.addWidget(
                self.admin_group, 2, 0, alignment=Qt.AlignmentFlag.AlignTop
            )
            self.sections_layout.setColumnStretch(0, 1)
            self.sections_layout.setColumnStretch(1, 0)

            self.footer_layout.addWidget(self.message_label, 0, 0)
            self.footer_layout.addWidget(self.action_button, 1, 0)
            self.footer_layout.setColumnStretch(0, 1)
            self.footer_layout.setColumnStretch(1, 0)
            self.action_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.sections_layout.addWidget(
                self.database_group, 0, 0, 2, 1, alignment=Qt.AlignmentFlag.AlignTop
            )
            self.sections_layout.addWidget(
                self.api_group, 0, 1, alignment=Qt.AlignmentFlag.AlignTop
            )
            self.sections_layout.addWidget(
                self.admin_group, 1, 1, alignment=Qt.AlignmentFlag.AlignTop
            )
            self.sections_layout.setColumnStretch(0, 1)
            self.sections_layout.setColumnStretch(1, 1)

            self.footer_layout.addWidget(self.message_label, 0, 0)
            self.footer_layout.addWidget(
                self.action_button,
                0,
                1,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
            self.footer_layout.setColumnStretch(0, 1)
            self.footer_layout.setColumnStretch(1, 0)
            self.action_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _update_content_width(self, compact: bool) -> None:
        """Keep summary content centered without stretching forever."""

        max_width = self.COMPACT_CONTENT_WIDTH if compact else self.MAX_CONTENT_WIDTH
        available_width = max(320, self.width() - 48)
        self.content_widget.setFixedWidth(min(max_width, available_width))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override name
        """Keep the running summary aligned as the window resizes."""

        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_stylesheet(self) -> None:
        """Apply scoped styling for the running summary window."""

        self.setStyleSheet(
            """
            QWidget#SummaryWindow {
                background: #f3f6fb;
                color: #182033;
                font-size: 10pt;
            }
            QScrollArea#SummaryScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#SummaryScrollHost {
                background: #f3f6fb;
            }
            QLabel#SummaryTitle {
                color: #111827;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#SummarySubtitle {
                color: #64748b;
                font-size: 12px;
                font-weight: 600;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #dce4ef;
                border-radius: 8px;
                color: #172033;
                font-size: 11px;
                font-weight: 700;
                margin-top: 18px;
                padding: 18px 18px 16px 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 7px;
                color: #334155;
            }
            QLabel#RowTitle {
                color: #64748b;
                font-weight: 600;
                min-width: 138px;
            }
            QLabel#RowValue {
                color: #111827;
                font-weight: 600;
            }
            QLabel#ServiceStatus {
                border-radius: 14px;
                font-weight: 700;
                font-size: 15px;
                padding: 6px 16px;
                border: 1px solid transparent;
            }
            QLabel#ServiceStatus[serviceState="neutral"] {
                background: #f1f5f9;
                color: #475569;
                border-color: #cbd5e1;
            }
            QLabel#ServiceStatus[serviceState="running"] {
                background: #ecfdf3;
                color: #167a3b;
                border-color: #d1fae5;
            }
            QLabel#ServiceStatus[serviceState="warning"] {
                background: #fffbeb;
                color: #9a6a00;
                border-color: #fef3c7;
            }
            QLabel#ServiceStatus[serviceState="error"] {
                background: #fef2f2;
                color: #b42318;
                border-color: #fee2e2;
            }
            QFrame#ConnectionCard {
                background: #ffffff;
                border: 1px solid #dce4ef;
                border-radius: 10px;
                margin-top: 12px;
                margin-bottom: 0;
            }
            QFrame#ConnectionCard[serviceState="neutral"] {
                background: #f1f5f9;
                border-color: #cbd5e1;
            }
            QFrame#ConnectionCard[serviceState="running"] {
                background: #ecfdf3;
                border-color: #d1fae5;
            }
            QFrame#ConnectionCard[serviceState="warning"] {
                background: #fffbeb;
                border-color: #fef3c7;
            }
            QFrame#ConnectionCard[serviceState="error"] {
                background: #fef2f2;
                border-color: #fee2e2;
            }
            QWidget#ConnectionCardContent {
                background: transparent;
            }
            QFrame#ConnectionAccent {
                background-color: #2563eb;
                border: none;
                border-top-left-radius: 10px;
                border-bottom-left-radius: 10px;
            }
            QFrame#ConnectionCard[serviceState="running"] QFrame#ConnectionAccent {
                background-color: #16a34a;
            }
            QFrame#ConnectionCard[serviceState="warning"] QFrame#ConnectionAccent {
                background-color: #d97706;
            }
            QFrame#ConnectionCard[serviceState="error"] QFrame#ConnectionAccent {
                background-color: #dc2626;
            }
            QFrame#ConnectionCard[serviceState="running"] QFrame#CardDivider {
                background-color: #d1fae5;
            }
            QFrame#ConnectionCard[serviceState="warning"] QFrame#CardDivider {
                background-color: #fef3c7;
            }
            QFrame#ConnectionCard[serviceState="error"] QFrame#CardDivider {
                background-color: #fee2e2;
            }
            QFrame#ConnectionCard[serviceState="neutral"] QFrame#CardDivider {
                background-color: #cbd5e1;
            }
            QFrame#ConnectionCard[serviceState="running"] QLabel#ServiceStatus,
            QFrame#ConnectionCard[serviceState="warning"] QLabel#ServiceStatus,
            QFrame#ConnectionCard[serviceState="error"] QLabel#ServiceStatus,
            QFrame#ConnectionCard[serviceState="neutral"] QLabel#ServiceStatus {
                background: transparent;
            }
            QLabel#CardTitle {
                color: #334155;
                font-size: 16px;
                font-weight: 700;
            }
            QFrame#CardDivider {
                background-color: #e8edf5;
                max-height: 1px;
                border: none;
            }
            QLabel#CardRowTitle {
                color: #64748b;
                font-weight: 600;
                font-size: 12px;
                min-width: 120px;
            }
            QLabel#CardRowValue {
                color: #111827;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton#CardCopyButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #1d4ed8;
                font-weight: 700;
                font-size: 11px;
                padding: 4px 10px;
                min-width: 60px;
            }
            QPushButton#CardCopyButton:hover {
                background: #eff6ff;
                border-color: #93c5fd;
            }
            QPushButton#CardCopyButton:pressed {
                background: #dbeafe;
            }
            QPushButton#CardCopyButton[copiedState="true"] {
                background: #10b981;
                border-color: #34d399;
                color: #ffffff;
            }
            QLineEdit,
            QComboBox,
            QSpinBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #111827;
                min-height: 34px;
                padding: 5px 9px;
                selection-background-color: #2563eb;
            }
            QLineEdit:focus,
            QComboBox:focus,
            QSpinBox:focus {
                border: 1px solid #2563eb;
                background: #fbfdff;
            }
            QComboBox::drop-down {
                border: none;
                width: 28px;
            }
            QSpinBox::up-button,
            QSpinBox::down-button {
                border: none;
                width: 18px;
            }
            QCheckBox {
                color: #475569;
                spacing: 8px;
            }
            QPushButton#InlineButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #1d4ed8;
                font-weight: 700;
                padding: 6px 10px;
            }
            QPushButton#InlineButton:hover {
                background: #eff6ff;
                border-color: #93c5fd;
            }
            QPushButton#InlineButton:disabled {
                background: #f1f5f9;
                color: #94a3b8;
            }
            QWidget#SummaryFooter {
                background: #ffffff;
                border-top: 1px solid #dce4ef;
            }
            QLabel#FooterMessage {
                border-radius: 6px;
                font-weight: 600;
                padding: 9px 11px;
            }
            QLabel#FooterMessage[messageState="info"] {
                background: #eff6ff;
                border: 1px solid #bfdbfe;
                color: #1d4ed8;
            }
            QLabel#FooterMessage[messageState="success"] {
                background: #ecfdf3;
                border: 1px solid #bbf7d0;
                color: #167a3b;
            }
            QLabel#FooterMessage[messageState="error"] {
                background: #fef2f2;
                border: 1px solid #fecaca;
                color: #b42318;
            }
            QPushButton#PrimaryButton {
                background: #2563eb;
                border: 1px solid #1d4ed8;
                border-radius: 7px;
                color: #ffffff;
                font-weight: 700;
                padding: 8px 18px;
            }
            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }
            QPushButton#PrimaryButton:pressed {
                background: #1e40af;
            }
            QPushButton#PrimaryButton:disabled {
                background: #94a3b8;
                border-color: #94a3b8;
                color: #f8fafc;
            }
            """
        )

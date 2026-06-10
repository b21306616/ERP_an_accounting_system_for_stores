"""First-run setup window for database and API configuration."""

from __future__ import annotations

import pyodbc
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig, create_default_config
from server_app.core.constants import DEFAULT_ODBC_DRIVER, SUPER_ADMIN_FULL_NAME, SUPER_ADMIN_USERNAME
from server_app.db.bootstrap import validate_database_name


class SetupWindow(QWidget):
    """Collect all first-run settings needed to start the server."""

    setup_requested = pyqtSignal(object, object, str)
    COMPACT_WIDTH = 760
    MAX_CONTENT_WIDTH = 1080
    COMPACT_CONTENT_WIDTH = 620

    def __init__(self, error_message: str | None = None) -> None:
        super().__init__()
        self.setObjectName("SetupWindow")
        self.setWindowTitle("ERP Accounting Server - First Setup")
        self.setMinimumSize(500, 520)
        self.default_config = create_default_config()
        self._initial_error_message = error_message
        self._is_compact_layout: bool | None = None
        self._is_busy = False
        self._setup_status_before_busy = ("Ready to configure", "neutral")

        self.server_edit = QLineEdit(self.default_config.database.server)
        self.database_edit = QLineEdit(self.default_config.database.database)
        self.driver_combo = QComboBox()
        self.auth_combo = QComboBox()
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.trust_cert_check = QCheckBox("Trust SQL Server certificate")

        self.host_edit = QLineEdit(self.default_config.api.host)
        self.port_spin = QSpinBox()

        self.super_admin_username_edit = QLineEdit(SUPER_ADMIN_USERNAME)
        self.super_admin_full_name_edit = QLineEdit(SUPER_ADMIN_FULL_NAME)
        self.current_password_edit = QLineEdit()
        self.new_password_edit = QLineEdit()
        self.confirm_password_edit = QLineEdit()

        self.setup_status_label = QLabel("Ready to configure")
        self.message_label = QLabel(error_message or "")
        self.submit_button = QPushButton("Create database and start Windows service")

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        """Create form controls and lay them out in logical groups."""

        self._apply_stylesheet()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("SetupScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_host = QWidget()
        scroll_host.setObjectName("SetupScrollHost")
        scroll_area.setWidget(scroll_host)

        scroll_layout = QHBoxLayout(scroll_host)
        scroll_layout.setContentsMargins(24, 24, 24, 28)
        scroll_layout.setSpacing(0)
        scroll_layout.addStretch(1)

        self.content_widget = QWidget()
        self.content_widget.setObjectName("SetupContent")
        self.content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        scroll_layout.addWidget(self.content_widget)
        scroll_layout.addStretch(1)

        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header = QWidget()
        header.setObjectName("SetupHeader")
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        title_label = QLabel("ERP Accounting Server")
        title_label.setObjectName("SetupTitle")
        title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        subtitle_label = QLabel("First setup")
        subtitle_label.setObjectName("SetupSubtitle")
        subtitle_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        content_layout.addWidget(header)

        self.setup_group = self._build_setup_card()
        content_layout.addWidget(self.setup_group)

        self.database_group = QGroupBox("MSSQL connection")
        self.database_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        database_layout = QGridLayout(self.database_group)
        self._prepare_form_layout(database_layout)
        self._fill_driver_combo()
        self.auth_combo.addItem("Windows Authentication", "windows")
        self.auth_combo.addItem("SQL Login", "sql")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.trust_cert_check.setChecked(True)
        self.server_edit.setPlaceholderText("localhost\\SQLEXPRESS")
        self.database_edit.setPlaceholderText("ERPAccounting")
        self.username_edit.setPlaceholderText("SQL login user")

        self._add_form_row(database_layout, 0, "SQL Server host/instance", self.server_edit)
        self._add_form_row(database_layout, 1, "Database name", self.database_edit)
        self._add_form_row(database_layout, 2, "ODBC driver", self.driver_combo)
        self._add_form_row(database_layout, 3, "Authentication", self.auth_combo)
        self._add_form_row(database_layout, 4, "SQL username", self.username_edit)
        self._add_form_row(database_layout, 5, "SQL password", self.password_edit)
        self._add_form_row(database_layout, 6, "", self.trust_cert_check)

        self.api_group = QGroupBox("API server")
        api_layout = QGridLayout(self.api_group)
        self._prepare_form_layout(api_layout)
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.default_config.api.port)
        self.host_edit.setPlaceholderText("0.0.0.0")
        self._add_form_row(api_layout, 0, "Bind host/IP", self.host_edit)
        self._add_form_row(api_layout, 1, "Port", self.port_spin)

        self.super_admin_group = QGroupBox("Super Admin account")
        super_admin_layout = QGridLayout(self.super_admin_group)
        self._prepare_form_layout(super_admin_layout)
        self.super_admin_username_edit.setReadOnly(True)
        self.super_admin_full_name_edit.setReadOnly(True)
        self.current_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._add_form_row(super_admin_layout, 0, "Username", self.super_admin_username_edit)
        self._add_form_row(super_admin_layout, 1, "Full name", self.super_admin_full_name_edit)
        self._add_form_row(super_admin_layout, 2, "Current password", self.current_password_edit)
        self._add_form_row(super_admin_layout, 3, "New password", self.new_password_edit)
        self._add_form_row(super_admin_layout, 4, "Confirm new password", self.confirm_password_edit)

        self.sections_layout = QGridLayout()
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setHorizontalSpacing(18)
        self.sections_layout.setVerticalSpacing(18)
        content_layout.addLayout(self.sections_layout)
        content_layout.addStretch(1)

        footer = QWidget()
        footer.setObjectName("SetupFooter")
        self.footer_layout = QGridLayout(footer)
        self.footer_layout.setContentsMargins(24, 14, 24, 14)
        self.footer_layout.setHorizontalSpacing(18)
        self.footer_layout.setVerticalSpacing(10)

        self.message_label.setObjectName("FooterMessage")
        self.message_label.setWordWrap(True)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.setMinimumHeight(42)
        self.submit_button.setCursor(Qt.CursorShape.PointingHandCursor)

        main_layout.addWidget(scroll_area, 1)
        main_layout.addWidget(footer, 0)

        self._sync_auth_fields()
        if self._initial_error_message:
            self.show_message(self._initial_error_message, "error")
            self._set_setup_status("Setup failed", "error")
        else:
            self._set_setup_status("Ready to configure", "neutral")
        self._apply_responsive_layout()

    def _build_setup_card(self) -> QFrame:
        """Build the setup summary card matching the running window connection card."""

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

        card_layout = QHBoxLayout(content)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(0)

        card_title = QLabel("Setup")
        card_title.setObjectName("CardTitle")

        self.setup_status_label.setObjectName("ServiceStatus")
        self.setup_status_label.setWordWrap(True)
        self.setup_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card_layout.addWidget(card_title)
        card_layout.addStretch(1)
        card_layout.addWidget(self.setup_status_label)
        return card

    def _prepare_form_layout(self, layout: QGridLayout) -> None:
        """Apply consistent row spacing for setup form sections."""

        layout.setContentsMargins(0, 8, 0, 0)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(12)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 0)

    def _add_form_row(self, layout: QGridLayout, row: int, title: str, widget: QWidget) -> None:
        """Add a labeled form row matching the running summary section style."""

        if title:
            title_label = QLabel(title)
            title_label.setObjectName("RowTitle")
            layout.addWidget(title_label, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(widget, row, 1, 1, 2)

    def _apply_responsive_layout(self) -> None:
        """Reflow sections and footer controls for compact or wide windows."""

        compact = self.width() < self.COMPACT_WIDTH
        self._update_content_width(compact)
        self._apply_footer_button_sizing(compact)
        if compact == self._is_compact_layout:
            return

        self._is_compact_layout = compact
        for widget in (self.database_group, self.api_group, self.super_admin_group):
            self.sections_layout.removeWidget(widget)
        self.footer_layout.removeWidget(self.message_label)
        self.footer_layout.removeWidget(self.submit_button)

        if compact:
            self.sections_layout.addWidget(self.database_group, 0, 0)
            self.sections_layout.addWidget(self.api_group, 1, 0)
            self.sections_layout.addWidget(self.super_admin_group, 2, 0)
            self.sections_layout.setColumnStretch(0, 1)
            self.sections_layout.setColumnStretch(1, 0)

            self.footer_layout.addWidget(self.message_label, 0, 0)
            self.footer_layout.addWidget(self.submit_button, 1, 0)
            self.footer_layout.setColumnStretch(0, 1)
            self.footer_layout.setColumnStretch(1, 0)
        else:
            self.sections_layout.addWidget(
                self.database_group, 0, 0, 2, 1, alignment=Qt.AlignmentFlag.AlignTop
            )
            self.sections_layout.addWidget(
                self.api_group, 0, 1, alignment=Qt.AlignmentFlag.AlignTop
            )
            self.sections_layout.addWidget(
                self.super_admin_group, 1, 1, alignment=Qt.AlignmentFlag.AlignTop
            )
            self.sections_layout.setColumnStretch(0, 1)
            self.sections_layout.setColumnStretch(1, 1)
            self.sections_layout.setRowStretch(0, 0)
            self.sections_layout.setRowStretch(1, 0)

            self.footer_layout.addWidget(self.message_label, 0, 0)
            self.footer_layout.addWidget(
                self.submit_button,
                0,
                1,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
            self.footer_layout.setColumnStretch(0, 1)
            self.footer_layout.setColumnStretch(1, 0)

    def _apply_footer_button_sizing(self, compact: bool) -> None:
        """Keep the primary action button full-width only on compact windows."""

        if compact:
            self.submit_button.setMinimumWidth(0)
            self.submit_button.setMaximumWidth(16777215)
            self.submit_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return

        self.submit_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.submit_button.setMinimumWidth(0)
        self.submit_button.setMaximumWidth(16777215)
        self.submit_button.adjustSize()
        content_width = self.submit_button.sizeHint().width()
        self.submit_button.setMinimumWidth(content_width)
        self.submit_button.setMaximumWidth(content_width)

    def _update_content_width(self, compact: bool) -> None:
        """Keep the form centered without letting it stretch too wide."""

        max_width = self.COMPACT_CONTENT_WIDTH if compact else self.MAX_CONTENT_WIDTH
        available_width = max(320, self.width() - 48)
        self.content_widget.setFixedWidth(min(max_width, available_width))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override name
        """Keep the setup form aligned as the desktop window resizes."""

        super().resizeEvent(event)
        self._apply_responsive_layout()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt override name
        """Re-apply layout once the window has its final size."""

        super().showEvent(event)
        self._apply_responsive_layout()

    def _set_setup_status(self, text: str, state: str) -> None:
        """Update the styled setup status badge and card state."""

        self.setup_status_label.setProperty("serviceState", state)
        self.setup_status_label.setText(text)
        self.setup_status_label.style().unpolish(self.setup_status_label)
        self.setup_status_label.style().polish(self.setup_status_label)
        self.setup_status_label.update()

        self.connection_card.setProperty("serviceState", state)
        self.connection_card.style().unpolish(self.connection_card)
        self.connection_card.style().polish(self.connection_card)
        self.connection_card.update()

    def show_message(self, message: str, state: str = "info") -> None:
        """Show a styled footer message."""

        self.message_label.setProperty("messageState", state)
        self.message_label.setText(message)
        self.message_label.setVisible(bool(message))
        self.message_label.style().unpolish(self.message_label)
        self.message_label.style().polish(self.message_label)
        self.message_label.update()

    def _apply_stylesheet(self) -> None:
        """Apply scoped styling for the first-run setup window."""

        self.setStyleSheet(
            """
            QWidget#SetupWindow {
                background: #f3f6fb;
                color: #182033;
                font-size: 10pt;
            }
            QScrollArea#SetupScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#SetupScrollHost {
                background: #f3f6fb;
            }
            QLabel#SetupTitle {
                color: #111827;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#SetupSubtitle {
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
            QLabel {
                color: #475569;
                font-weight: 500;
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
            QLineEdit:read-only {
                background: #f8fafc;
                color: #64748b;
            }
            QLineEdit:disabled,
            QComboBox:disabled,
            QSpinBox:disabled {
                background: #eef2f7;
                border-color: #d7dee8;
                color: #94a3b8;
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
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background: #ffffff;
            }
            QCheckBox::indicator:checked {
                background: #2563eb;
                border-color: #2563eb;
            }
            QCheckBox:disabled {
                color: #94a3b8;
            }
            QWidget#SetupFooter {
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

    def _fill_driver_combo(self) -> None:
        """Populate ODBC drivers, preferring Driver 18 when available."""

        drivers = list(pyodbc.drivers())
        if DEFAULT_ODBC_DRIVER not in drivers:
            drivers.insert(0, DEFAULT_ODBC_DRIVER)

        self.driver_combo.addItems(drivers)
        index = self.driver_combo.findText(DEFAULT_ODBC_DRIVER)
        if index >= 0:
            self.driver_combo.setCurrentIndex(index)

    def _input_widgets(self) -> list[QWidget]:
        """Return all editable setup form controls."""

        return [
            self.server_edit,
            self.database_edit,
            self.driver_combo,
            self.auth_combo,
            self.username_edit,
            self.password_edit,
            self.trust_cert_check,
            self.host_edit,
            self.port_spin,
            self.current_password_edit,
            self.new_password_edit,
            self.confirm_password_edit,
        ]

    def _connect_signals(self) -> None:
        """Connect user actions to validation and setup logic."""

        self.auth_combo.currentIndexChanged.connect(self._sync_auth_fields)
        self.submit_button.clicked.connect(self._on_submit)

    def _sync_auth_fields(self) -> None:
        """Enable SQL username/password only for SQL Login mode."""

        is_sql_login = self.auth_combo.currentData() == "sql"
        self.username_edit.setEnabled(is_sql_login and not self._is_busy)
        self.password_edit.setEnabled(is_sql_login and not self._is_busy)

    def set_busy(self, is_busy: bool, *, restore_status: bool = True) -> None:
        """Disable inputs while setup is running."""

        if is_busy and not self._is_busy:
            self._setup_status_before_busy = (
                self.setup_status_label.text(),
                str(self.connection_card.property("serviceState") or "neutral"),
            )
            self._set_setup_status("Working...", "neutral")
        elif not is_busy and self._is_busy and restore_status:
            previous_text, previous_state = self._setup_status_before_busy
            self._set_setup_status(previous_text, previous_state)

        self._is_busy = is_busy
        self.submit_button.setDisabled(is_busy)
        self.submit_button.setText(
            "Working..." if is_busy else "Create database and start Windows service"
        )
        self._apply_footer_button_sizing(self.width() < self.COMPACT_WIDTH)

        for widget in self._input_widgets():
            widget.setDisabled(is_busy)
        self._sync_auth_fields()

    def show_error(self, message: str) -> None:
        """Show a recoverable setup error."""

        self.show_message(message, "error")
        self.set_busy(False, restore_status=False)
        self._set_setup_status("Setup failed", "error")

    def _on_submit(self) -> None:
        """Validate form values and emit a setup request."""

        try:
            config, current_password, new_password = self._build_config_from_form()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid setup values", str(exc))
            return

        self.show_message(
            "Creating database, running migrations, and preparing Windows service...",
            "info",
        )
        self.set_busy(True)
        self.setup_requested.emit(config, current_password, new_password)

    def _build_config_from_form(self) -> tuple[AppConfig, str | None, str]:
        """Create typed config and Super Admin password values from validated form fields."""

        server = self.server_edit.text().strip()
        database = self.database_edit.text().strip()
        host = self.host_edit.text().strip()
        current_password = self.current_password_edit.text()
        new_password = self.new_password_edit.text()
        password_confirm = self.confirm_password_edit.text()
        auth_mode = self.auth_combo.currentData()

        if not server:
            raise ValueError("SQL Server host/instance is required.")
        if not database:
            raise ValueError("Database name is required.")
        validate_database_name(database)
        if not host:
            raise ValueError("API bind host/IP is required.")
        if auth_mode == "sql" and not self.username_edit.text().strip():
            raise ValueError("SQL username is required for SQL Login mode.")
        if auth_mode == "sql" and not self.password_edit.text():
            raise ValueError("SQL password is required for SQL Login mode.")
        if len(new_password) < 6:
            raise ValueError("Super Admin password must contain at least 6 characters.")
        if new_password != password_confirm:
            raise ValueError("Super Admin password and confirmation do not match.")

        database_config = DatabaseConfig(
            server=server,
            database=database,
            driver=self.driver_combo.currentText(),
            auth_mode=auth_mode,
            username=self.username_edit.text().strip() or None,
            password=self.password_edit.text() or None,
            trust_server_certificate=self.trust_cert_check.isChecked(),
        )
        api_config = ApiConfig(host=host, port=self.port_spin.value())
        config = AppConfig(
            database=database_config,
            api=api_config,
            jwt_secret=self.default_config.jwt_secret,
        )
        return config, current_password or None, new_password

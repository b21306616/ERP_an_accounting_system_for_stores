"""First-run setup window for database and API configuration."""

from __future__ import annotations

import pyodbc
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
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
        self.setMinimumSize(480, 520)
        self.default_config = create_default_config()
        self._initial_error_message = error_message
        self._is_compact_layout: bool | None = None

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

        self.status_label = QLabel(error_message or "")
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

        header = QWidget()
        header.setObjectName("SetupHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(4)

        title_label = QLabel("ERP Accounting Server")
        title_label.setObjectName("SetupTitle")
        subtitle_label = QLabel("First setup")
        subtitle_label.setObjectName("SetupSubtitle")
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        content_layout.addWidget(header)

        self.database_group = QGroupBox("MSSQL connection")
        database_form = QFormLayout(self.database_group)
        self._prepare_form(database_form)
        self._fill_driver_combo()
        self.auth_combo.addItem("Windows Authentication", "windows")
        self.auth_combo.addItem("SQL Login", "sql")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.trust_cert_check.setChecked(True)
        self.server_edit.setPlaceholderText("localhost\\SQLEXPRESS")
        self.database_edit.setPlaceholderText("ERPAccounting")
        self.username_edit.setPlaceholderText("SQL login user")

        database_form.addRow("SQL Server host/instance", self.server_edit)
        database_form.addRow("Database name", self.database_edit)
        database_form.addRow("ODBC driver", self.driver_combo)
        database_form.addRow("Authentication", self.auth_combo)
        database_form.addRow("SQL username", self.username_edit)
        database_form.addRow("SQL password", self.password_edit)
        database_form.addRow("", self.trust_cert_check)

        self.api_group = QGroupBox("API server")
        api_form = QFormLayout(self.api_group)
        self._prepare_form(api_form)
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.default_config.api.port)
        self.host_edit.setPlaceholderText("0.0.0.0")
        api_form.addRow("Bind host/IP", self.host_edit)
        api_form.addRow("Port", self.port_spin)

        self.super_admin_group = QGroupBox("Super Admin account")
        super_admin_form = QFormLayout(self.super_admin_group)
        self._prepare_form(super_admin_form)
        self.super_admin_username_edit.setReadOnly(True)
        self.super_admin_full_name_edit.setReadOnly(True)
        self.current_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        super_admin_form.addRow("Username", self.super_admin_username_edit)
        super_admin_form.addRow("Full name", self.super_admin_full_name_edit)
        super_admin_form.addRow("Current password", self.current_password_edit)
        super_admin_form.addRow("New password", self.new_password_edit)
        super_admin_form.addRow("Confirm new password", self.confirm_password_edit)

        self.sections_layout = QGridLayout()
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setHorizontalSpacing(18)
        self.sections_layout.setVerticalSpacing(18)
        content_layout.addLayout(self.sections_layout)

        footer = QWidget()
        footer.setObjectName("SetupFooter")
        self.footer_layout = QGridLayout(footer)
        self.footer_layout.setContentsMargins(24, 14, 24, 14)
        self.footer_layout.setHorizontalSpacing(18)
        self.footer_layout.setVerticalSpacing(10)

        self.status_label.setObjectName("StatusBanner")
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.setMinimumHeight(42)
        self.submit_button.setMinimumWidth(330)
        self.submit_button.setCursor(Qt.CursorShape.PointingHandCursor)

        main_layout.addWidget(scroll_area, 1)
        main_layout.addWidget(footer, 0)

        self._sync_auth_fields()
        self._set_status_message(self._initial_error_message or "", "error")
        self._apply_responsive_layout()

    def _prepare_form(self, form: QFormLayout) -> None:
        """Apply consistent spacing and growth behavior to section forms."""

        form.setContentsMargins(0, 8, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

    def _apply_responsive_layout(self) -> None:
        """Reflow sections and footer controls for compact or wide windows."""

        compact = self.width() < self.COMPACT_WIDTH
        self._update_content_width(compact)
        if compact == self._is_compact_layout:
            return

        self._is_compact_layout = compact
        for widget in (self.database_group, self.api_group, self.super_admin_group):
            self.sections_layout.removeWidget(widget)
        self.footer_layout.removeWidget(self.status_label)
        self.footer_layout.removeWidget(self.submit_button)

        if compact:
            self.sections_layout.addWidget(self.database_group, 0, 0)
            self.sections_layout.addWidget(self.api_group, 1, 0)
            self.sections_layout.addWidget(self.super_admin_group, 2, 0)
            self.sections_layout.setColumnStretch(0, 1)
            self.sections_layout.setColumnStretch(1, 0)

            self.footer_layout.addWidget(self.status_label, 0, 0)
            self.footer_layout.addWidget(self.submit_button, 1, 0)
            self.footer_layout.setColumnStretch(0, 1)
            self.footer_layout.setColumnStretch(1, 0)
            self.submit_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.sections_layout.addWidget(self.database_group, 0, 0, 2, 1)
            self.sections_layout.addWidget(self.api_group, 0, 1)
            self.sections_layout.addWidget(self.super_admin_group, 1, 1)
            self.sections_layout.setColumnStretch(0, 1)
            self.sections_layout.setColumnStretch(1, 1)

            self.footer_layout.addWidget(self.status_label, 0, 0)
            self.footer_layout.addWidget(
                self.submit_button,
                0,
                1,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
            self.footer_layout.setColumnStretch(0, 1)
            self.footer_layout.setColumnStretch(1, 0)
            self.submit_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _update_content_width(self, compact: bool) -> None:
        """Keep the form centered without letting it stretch too wide."""

        max_width = self.COMPACT_CONTENT_WIDTH if compact else self.MAX_CONTENT_WIDTH
        available_width = max(320, self.width() - 48)
        self.content_widget.setFixedWidth(min(max_width, available_width))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override name
        """Keep the setup form aligned as the desktop window resizes."""

        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _set_status_message(self, message: str, state: str) -> None:
        """Show a styled footer status message."""

        self.status_label.setProperty("statusState", state)
        self.status_label.setText(message)
        self.status_label.setVisible(bool(message))
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.update()

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
                text-transform: uppercase;
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
            QWidget#SetupFooter {
                background: #ffffff;
                border-top: 1px solid #dce4ef;
            }
            QLabel#StatusBanner {
                border-radius: 6px;
                padding: 9px 11px;
                font-weight: 600;
            }
            QLabel#StatusBanner[statusState="info"] {
                background: #eff6ff;
                border: 1px solid #bfdbfe;
                color: #1d4ed8;
            }
            QLabel#StatusBanner[statusState="error"] {
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

    def _connect_signals(self) -> None:
        """Connect user actions to validation and setup logic."""

        self.auth_combo.currentIndexChanged.connect(self._sync_auth_fields)
        self.submit_button.clicked.connect(self._on_submit)

    def _sync_auth_fields(self) -> None:
        """Enable SQL username/password only for SQL Login mode."""

        is_sql_login = self.auth_combo.currentData() == "sql"
        self.username_edit.setEnabled(is_sql_login)
        self.password_edit.setEnabled(is_sql_login)

    def set_busy(self, is_busy: bool) -> None:
        """Disable inputs while setup is running."""

        self.submit_button.setDisabled(is_busy)
        self.submit_button.setText("Working..." if is_busy else "Create database and start Windows service")

    def show_error(self, message: str) -> None:
        """Show a recoverable setup error."""

        self._set_status_message(message, "error")
        self.set_busy(False)

    def _on_submit(self) -> None:
        """Validate form values and emit a setup request."""

        try:
            config, current_password, new_password = self._build_config_from_form()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid setup values", str(exc))
            return

        self._set_status_message(
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

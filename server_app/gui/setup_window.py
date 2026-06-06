"""First-run setup window for database and API configuration."""

from __future__ import annotations

import pyodbc
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig, create_default_config
from server_app.core.constants import DEFAULT_ODBC_DRIVER


class SetupWindow(QWidget):
    """Collect all first-run settings needed to start the server."""

    setup_requested = pyqtSignal(object, str, str, str)

    def __init__(self, error_message: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("ERP Accounting Server - First Setup")
        self.setMinimumWidth(560)
        self.default_config = create_default_config()

        self.server_edit = QLineEdit(self.default_config.database.server)
        self.database_edit = QLineEdit(self.default_config.database.database)
        self.driver_combo = QComboBox()
        self.auth_combo = QComboBox()
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.trust_cert_check = QCheckBox("Trust SQL Server certificate")

        self.host_edit = QLineEdit(self.default_config.api.host)
        self.port_spin = QSpinBox()

        self.owner_username_edit = QLineEdit("owner")
        self.owner_full_name_edit = QLineEdit("System Owner")
        self.owner_password_edit = QLineEdit()
        self.owner_confirm_edit = QLineEdit()

        self.status_label = QLabel(error_message or "")
        self.submit_button = QPushButton("Create database and start server")

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        """Create form controls and lay them out in logical groups."""

        main_layout = QVBoxLayout(self)

        database_group = QGroupBox("MSSQL connection")
        database_form = QFormLayout(database_group)
        self._fill_driver_combo()
        self.auth_combo.addItem("Windows Authentication", "windows")
        self.auth_combo.addItem("SQL Login", "sql")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.trust_cert_check.setChecked(True)

        database_form.addRow("SQL Server host/instance", self.server_edit)
        database_form.addRow("Database name", self.database_edit)
        database_form.addRow("ODBC driver", self.driver_combo)
        database_form.addRow("Authentication", self.auth_combo)
        database_form.addRow("SQL username", self.username_edit)
        database_form.addRow("SQL password", self.password_edit)
        database_form.addRow("", self.trust_cert_check)

        api_group = QGroupBox("API server")
        api_form = QFormLayout(api_group)
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.default_config.api.port)
        api_form.addRow("Bind host/IP", self.host_edit)
        api_form.addRow("Port", self.port_spin)

        owner_group = QGroupBox("Initial Owner user")
        owner_form = QFormLayout(owner_group)
        self.owner_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.owner_confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        owner_form.addRow("Username", self.owner_username_edit)
        owner_form.addRow("Full name", self.owner_full_name_edit)
        owner_form.addRow("Password", self.owner_password_edit)
        owner_form.addRow("Confirm password", self.owner_confirm_edit)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.submit_button)

        self.status_label.setWordWrap(True)
        if self.status_label.text():
            self.status_label.setStyleSheet("color: #a33;")

        main_layout.addWidget(database_group)
        main_layout.addWidget(api_group)
        main_layout.addWidget(owner_group)
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(button_row)

        self._sync_auth_fields()

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
        self.submit_button.setText("Working..." if is_busy else "Create database and start server")

    def show_error(self, message: str) -> None:
        """Show a recoverable setup error."""

        self.status_label.setStyleSheet("color: #a33;")
        self.status_label.setText(message)
        self.set_busy(False)

    def _on_submit(self) -> None:
        """Validate form values and emit a setup request."""

        try:
            config, owner_username, owner_full_name, owner_password = self._build_config_from_form()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid setup values", str(exc))
            return

        self.status_label.setStyleSheet("color: #555;")
        self.status_label.setText("Creating database, running migrations, and starting API...")
        self.set_busy(True)
        self.setup_requested.emit(config, owner_username, owner_full_name, owner_password)

    def _build_config_from_form(self) -> tuple[AppConfig, str, str, str]:
        """Create typed config and Owner credentials from validated form fields."""

        server = self.server_edit.text().strip()
        database = self.database_edit.text().strip()
        host = self.host_edit.text().strip()
        owner_username = self.owner_username_edit.text().strip()
        owner_full_name = self.owner_full_name_edit.text().strip()
        owner_password = self.owner_password_edit.text()
        owner_confirm = self.owner_confirm_edit.text()
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
        if not owner_username:
            raise ValueError("Owner username is required.")
        if not owner_full_name:
            raise ValueError("Owner full name is required.")
        if len(owner_password) < 6:
            raise ValueError("Owner password must contain at least 6 characters.")
        if owner_password != owner_confirm:
            raise ValueError("Owner password and confirmation do not match.")

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
        return config, owner_username, owner_full_name, owner_password

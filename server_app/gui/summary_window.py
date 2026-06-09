"""Server summary and stop-control window."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from server_app.core.config import AppConfig
from server_app.core.constants import APP_NAME
from server_app.service_control import ServiceStartType, ServiceStatus


class SummaryWindow(QWidget):
    """Show active connection details and expose the Stop Connection action."""

    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.setWindowTitle(f"{APP_NAME} - Running")
        self.setMinimumWidth(520)

        self.status_label = QLabel("Starting...")
        self.base_url_label = QLabel(self.base_url)
        self.docs_url_label = QLabel(f"{self.base_url}/docs")
        self.database_label = QLabel(f"{config.database.server} / {config.database.database}")
        self.auth_label = QLabel(config.database.auth_mode)
        self.action_button = QPushButton("Stop Connection")
        self.stop_button = self.action_button
        self.is_running = False

        self._build_ui()
        self.action_button.clicked.connect(self._on_action_clicked)

    @property
    def base_url(self) -> str:
        """Return the HTTP URL clients can use to reach this server."""

        host = self.config.api.host
        display_host = "localhost" if host == "0.0.0.0" else host
        return f"http://{display_host}:{self.config.api.port}"

    def _build_ui(self) -> None:
        """Build the compact summary UI."""

        main_layout = QVBoxLayout(self)
        group = QGroupBox("Connection summary")
        form = QFormLayout(group)

        self.status_label.setStyleSheet("font-weight: 600; color: #555;")
        self.base_url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.docs_url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form.addRow("Status", self.status_label)
        form.addRow("API base URL", self.base_url_label)
        form.addRow("Swagger docs", self.docs_url_label)
        form.addRow("Database", self.database_label)
        form.addRow("DB auth mode", self.auth_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.action_button.setEnabled(False)
        button_row.addWidget(self.action_button)

        main_layout.addWidget(group)
        main_layout.addLayout(button_row)

    def _on_action_clicked(self) -> None:
        """Emit the correct action for the current service state."""

        if self.is_running:
            self.stop_requested.emit()
        else:
            self.start_requested.emit()

    def mark_running(self) -> None:
        """Update the UI after the Windows service starts."""

        self.is_running = True
        self.status_label.setText("Running")
        self.status_label.setStyleSheet("font-weight: 600; color: #167a3b;")
        self.action_button.setText("Stop Connection")
        self.action_button.setEnabled(True)

    def mark_starting(self) -> None:
        """Update the UI while service startup is in progress."""

        self.is_running = False
        self.status_label.setText("Starting...")
        self.status_label.setStyleSheet("font-weight: 600; color: #555;")
        self.action_button.setText("Start Connection")
        self.action_button.setEnabled(False)

    def mark_stopping(self) -> None:
        """Update the UI while shutdown is in progress."""

        self.is_running = True
        self.status_label.setText("Stopping...")
        self.status_label.setStyleSheet("font-weight: 600; color: #9a6a00;")
        self.action_button.setText("Stop Connection")
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

        self.status_label.setText(text)
        self.status_label.setStyleSheet("font-weight: 600; color: #9a6a00;")
        self.action_button.setText("Start Connection")
        self.action_button.setEnabled(True)

    def mark_error(self, message: str) -> None:
        """Show a startup or runtime error."""

        self.is_running = False
        self.status_label.setText(message)
        self.status_label.setStyleSheet("font-weight: 600; color: #a33;")
        self.action_button.setText("Start Connection")
        self.action_button.setEnabled(True)

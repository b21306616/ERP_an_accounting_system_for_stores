"""Server summary and stop-control window."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from server_app.core.config import AppConfig
from server_app.core.constants import APP_NAME


class SummaryWindow(QWidget):
    """Show active connection details and expose the Stop Connection action."""

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
        self.stop_button = QPushButton("Stop Connection")

        self._build_ui()
        self.stop_button.clicked.connect(self.stop_requested.emit)

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
        button_row.addWidget(self.stop_button)

        main_layout.addWidget(group)
        main_layout.addLayout(button_row)

    def mark_running(self) -> None:
        """Update the UI after uvicorn starts."""

        self.status_label.setText("Running")
        self.status_label.setStyleSheet("font-weight: 600; color: #167a3b;")
        self.stop_button.setEnabled(True)

    def mark_stopping(self) -> None:
        """Update the UI while shutdown is in progress."""

        self.status_label.setText("Stopping...")
        self.status_label.setStyleSheet("font-weight: 600; color: #9a6a00;")
        self.stop_button.setEnabled(False)

    def mark_error(self, message: str) -> None:
        """Show a startup or runtime error."""

        self.status_label.setText(message)
        self.status_label.setStyleSheet("font-weight: 600; color: #a33;")
        self.stop_button.setEnabled(False)

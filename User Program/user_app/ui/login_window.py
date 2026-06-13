"""Login window for the endpoint client."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from user_app.core.config import ClientConfig, LanguageCode
from user_app.core.i18n import Translator


class LoginWindow(QWidget):
    """Collect server URL and user credentials."""

    login_requested = pyqtSignal(str, str, str)
    language_changed = pyqtSignal(str)

    def __init__(self, config: ClientConfig, translator: Translator) -> None:
        super().__init__()
        self.config = config
        self.translator = translator
        self.setObjectName("LoginWindow")
        self.setMinimumSize(460, 360)

        self.title_label = QLabel()
        self.status_label = QLabel()
        self.server_edit = QLineEdit(config.server_url)
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.language_combo = QComboBox()
        self.submit_button = QPushButton()

        self._build_ui()
        self._connect_signals()
        self.retranslate()

    def _build_ui(self) -> None:
        """Build the login form."""

        self.setStyleSheet(
            """
            QWidget#LoginWindow {
                background: #f3f6fb;
                color: #182033;
                font-size: 10pt;
            }
            QLabel#Title {
                color: #111827;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#Status {
                background: #eff6ff;
                border: 1px solid #bfdbfe;
                border-radius: 6px;
                color: #1d4ed8;
                font-weight: 600;
                padding: 9px 11px;
            }
            QLineEdit,
            QComboBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                min-height: 34px;
                padding: 5px 9px;
            }
            QPushButton#PrimaryButton {
                background: #2563eb;
                border: 1px solid #1d4ed8;
                border-radius: 7px;
                color: #ffffff;
                font-weight: 700;
                min-height: 38px;
                padding: 8px 18px;
            }
            QPushButton#PrimaryButton:disabled {
                background: #94a3b8;
                border-color: #94a3b8;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(18)

        self.title_label.setObjectName("Title")
        layout.addWidget(self.title_label)

        form = QFormLayout()
        form.setSpacing(12)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.language_combo.addItem("Русский", "ru")
        self.language_combo.addItem("Türkmençe", "tk")
        self.language_combo.addItem("English", "en")
        index = self.language_combo.findData(self.config.language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        form.addRow("", self.server_edit)
        form.addRow("", self.username_edit)
        form.addRow("", self.password_edit)
        form.addRow("", self.language_combo)
        layout.addLayout(form)

        self.status_label.setObjectName("Status")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button_row.addWidget(self.submit_button)
        layout.addLayout(button_row)
        layout.addStretch(1)

    def _connect_signals(self) -> None:
        """Connect actions."""

        self.submit_button.clicked.connect(self._on_submit)
        self.password_edit.returnPressed.connect(self._on_submit)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

    def _on_language_changed(self) -> None:
        """Emit language changes."""

        language = str(self.language_combo.currentData())
        self.language_changed.emit(language)

    def _on_submit(self) -> None:
        """Emit validated login values."""

        self.login_requested.emit(
            self.server_edit.text().strip(),
            self.username_edit.text().strip(),
            self.password_edit.text(),
        )

    def set_busy(self, busy: bool) -> None:
        """Enable or disable form controls while logging in."""

        for widget in (self.server_edit, self.username_edit, self.password_edit, self.language_combo):
            widget.setEnabled(not busy)
        self.submit_button.setEnabled(not busy)
        if busy:
            self.status_label.setText(self.translator.text("login.status.connecting"))

    def show_error(self, message: str) -> None:
        """Show a login error."""

        self.status_label.setText(f"{self.translator.text('login.status.failed')}: {message}")
        self.set_busy(False)

    def retranslate(self) -> None:
        """Apply active translations."""

        self.setWindowTitle(self.translator.text("app.title"))
        self.title_label.setText(self.translator.text("login.title"))
        self.server_edit.setPlaceholderText(self.translator.text("login.server"))
        self.username_edit.setPlaceholderText(self.translator.text("login.username"))
        self.password_edit.setPlaceholderText(self.translator.text("login.password"))
        self.submit_button.setText(self.translator.text("login.submit"))
        self.status_label.setText(self.translator.text("login.status.ready"))

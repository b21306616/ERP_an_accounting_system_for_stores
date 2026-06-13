"""PyQt6 application coordinator for the endpoint client."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from user_app.api.client import ApiClient, ApiClientError
from user_app.core.config import ClientConfig, ClientConfigManager, SUPPORTED_LANGUAGES, normalize_server_url
from user_app.core.i18n import Translator
from user_app.ui.login_window import LoginWindow
from user_app.ui.main_window import MainWindow


class ClientApplicationCoordinator:
    """Own login and main windows for the endpoint app."""

    def __init__(self, app: QApplication, config_manager: ClientConfigManager) -> None:
        self.app = app
        self.config_manager = config_manager
        self.config = config_manager.load()
        self.translator = Translator(self.config.language)
        self.api_client = ApiClient(self.config.server_url)
        self.login_window: LoginWindow | None = None
        self.main_window: MainWindow | None = None

    def start(self) -> None:
        """Show login window."""

        self.show_login()

    def show_login(self) -> None:
        """Show login window."""

        if self.main_window is not None:
            self.main_window.close()
            self.main_window = None
        self.login_window = LoginWindow(self.config, self.translator)
        self.login_window.login_requested.connect(self.handle_login)
        self.login_window.language_changed.connect(self.handle_language_changed)
        self.login_window.show()

    def handle_login(self, server_url: str, username: str, password: str) -> None:
        """Log in and open the main shell."""

        if self.login_window is None:
            return
        self.login_window.set_busy(True)
        normalized_url = normalize_server_url(server_url)
        self.api_client.set_base_url(normalized_url)
        try:
            self.api_client.login(username, password)
        except ApiClientError as exc:
            self.login_window.show_error(str(exc))
            return

        self.config = ClientConfig(server_url=normalized_url, language=self.translator.language)
        self.config_manager.save(self.config)
        self.login_window.close()
        self.login_window = None
        self.main_window = MainWindow(self.api_client, self.translator)
        self.main_window.logout_requested.connect(self.handle_logout)
        self.main_window.language_changed.connect(self.handle_language_changed)
        self.main_window.show()

    def handle_logout(self) -> None:
        """Log out and return to login."""

        try:
            self.api_client.logout()
        except ApiClientError as exc:
            QMessageBox.warning(None, self.translator.text("common.error"), str(exc))
        self.show_login()

    def handle_language_changed(self, language: str) -> None:
        """Switch UI language and save local preference."""

        if language not in SUPPORTED_LANGUAGES:
            return
        self.translator.set_language(language)  # type: ignore[arg-type]
        self.config.language = self.translator.language
        self.config_manager.save(self.config)
        if self.login_window is not None:
            self.login_window.retranslate()
        if self.main_window is not None:
            self.main_window.retranslate()


def run_desktop_app() -> None:
    """Run the PyQt6 endpoint client."""

    app = QApplication(sys.argv)
    app.setApplicationName("ERP Accounting User")
    coordinator = ClientApplicationCoordinator(app, ClientConfigManager())
    coordinator.start()
    sys.exit(app.exec())

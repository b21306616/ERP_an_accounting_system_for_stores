"""Main endpoint-client shell."""

from __future__ import annotations

from decimal import Decimal
import json
from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from user_app.api.client import ApiClient, ApiClientError
from user_app.core.i18n import Translator
from user_app.hardware.simulator import HardwareSimulator


class MainWindow(QWidget):
    """Role-aware main shell for the endpoint client."""

    logout_requested = pyqtSignal()
    language_changed = pyqtSignal(str)

    def __init__(self, api_client: ApiClient, translator: Translator) -> None:
        super().__init__()
        self.api_client = api_client
        self.translator = translator
        self.hardware = HardwareSimulator()
        self.setObjectName("MainWindow")
        self.setMinimumSize(980, 620)
        self.nav = QListWidget()
        self.stack = QStackedWidget()
        self.language_combo = QComboBox()
        self.logout_button = QPushButton()
        self.status_label = QLabel()
        self.pages: dict[str, QWidget] = {}
        self.nav_items: dict[str, QListWidgetItem] = {}

        self._build_ui()
        self._connect_signals()
        self.retranslate()
        self._apply_permissions()
        self.refresh_dashboard()

    def _build_ui(self) -> None:
        """Build shell layout."""

        self.setStyleSheet(
            """
            QWidget#MainWindow {
                background: #f3f6fb;
                color: #182033;
                font-size: 10pt;
            }
            QListWidget {
                background: #ffffff;
                border: 1px solid #dce4ef;
                border-radius: 8px;
                padding: 6px;
            }
            QListWidget::item {
                border-radius: 6px;
                padding: 9px;
            }
            QListWidget::item:selected {
                background: #dbeafe;
                color: #1d4ed8;
            }
            QLabel#PageTitle {
                color: #111827;
                font-size: 20px;
                font-weight: 700;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #1d4ed8;
                font-weight: 700;
                padding: 7px 11px;
            }
            QPushButton#PrimaryButton {
                background: #2563eb;
                border-color: #1d4ed8;
                color: #ffffff;
            }
            QTableWidget,
            QPlainTextEdit,
            QLineEdit,
            QComboBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        top = QHBoxLayout()
        self.status_label.setObjectName("PageTitle")
        top.addWidget(self.status_label)
        top.addStretch(1)
        self.language_combo.addItem("Русский", "ru")
        self.language_combo.addItem("Türkmençe", "tk")
        index = self.language_combo.findData(self.translator.language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        top.addWidget(self.language_combo)
        self.logout_button.setObjectName("PrimaryButton")
        top.addWidget(self.logout_button)
        root.addLayout(top)

        body = QHBoxLayout()
        self.nav.setFixedWidth(220)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self._add_page("dashboard", self._build_dashboard_page())
        self._add_page("users", self._build_users_page())
        self._add_page("roles", self._build_roles_page())
        self._add_page("settings", self._build_settings_page())
        self._add_page("hardware", self._build_hardware_page())
        for page_id in ("catalog", "warehouse", "purchase", "pricing", "sales", "cashier", "reports"):
            self._add_page(page_id, self._build_placeholder_page(page_id))

        self.nav.setCurrentRow(0)

    def _connect_signals(self) -> None:
        """Connect shell actions."""

        self.logout_button.clicked.connect(self.logout_requested.emit)
        self.language_combo.currentIndexChanged.connect(lambda: self.language_changed.emit(str(self.language_combo.currentData())))
        self.nav.currentRowChanged.connect(self._on_page_changed)

    def _add_page(self, page_id: str, page: QWidget) -> None:
        """Register one page and matching nav item."""

        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, page_id)
        self.nav.addItem(item)
        self.stack.addWidget(page)
        self.pages[page_id] = page
        self.nav_items[page_id] = item

    def _page(self, title_key: str) -> tuple[QWidget, QVBoxLayout, QLabel]:
        """Create a page with a title label."""

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(12)
        title = QLabel(self.translator.text(title_key))
        title.setObjectName("PageTitle")
        title.setProperty("titleKey", title_key)
        layout.addWidget(title)
        return page, layout, title

    def _build_dashboard_page(self) -> QWidget:
        """Build dashboard page."""

        page, layout, _title = self._page("dashboard.title")
        self.dashboard_text = QPlainTextEdit()
        self.dashboard_text.setReadOnly(True)
        refresh = QPushButton()
        refresh.setProperty("textKey", "dashboard.refresh")
        refresh.clicked.connect(self.refresh_dashboard)
        layout.addWidget(refresh)
        layout.addWidget(self.dashboard_text, 1)
        return page

    def _build_users_page(self) -> QWidget:
        """Build users page."""

        page, layout, _title = self._page("users.title")
        row = QHBoxLayout()
        refresh = QPushButton()
        refresh.setProperty("textKey", "users.refresh")
        refresh.clicked.connect(self.refresh_users)
        create = QPushButton()
        create.setProperty("textKey", "users.create")
        create.clicked.connect(self.create_user_dialog)
        row.addWidget(refresh)
        row.addWidget(create)
        row.addStretch(1)
        self.users_table = QTableWidget(0, 5)
        self.users_table.setHorizontalHeaderLabels(["ID", "Username", "Full name", "Role", "Active"])
        layout.addLayout(row)
        layout.addWidget(self.users_table, 1)
        return page

    def _build_roles_page(self) -> QWidget:
        """Build roles page."""

        page, layout, _title = self._page("roles.title")
        self.roles_text = QPlainTextEdit()
        self.roles_text.setReadOnly(True)
        refresh = QPushButton()
        refresh.setProperty("textKey", "dashboard.refresh")
        refresh.clicked.connect(self.refresh_roles)
        layout.addWidget(refresh)
        layout.addWidget(self.roles_text, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        """Build settings page."""

        page, layout, _title = self._page("settings.title")
        self.settings_text = QPlainTextEdit()
        save = QPushButton()
        save.setProperty("textKey", "settings.save")
        save.clicked.connect(self.save_settings)
        layout.addWidget(self.settings_text, 1)
        layout.addWidget(save)
        return page

    def _build_hardware_page(self) -> QWidget:
        """Build hardware simulator page."""

        page, layout, _title = self._page("hardware.title")
        self.hardware_text = QPlainTextEdit()
        self.hardware_text.setReadOnly(True)
        actions: list[tuple[str, Callable[[], None]]] = [
            ("hardware.scan", self.simulate_scan),
            ("hardware.print", self.simulate_print),
            ("hardware.drawer", self.simulate_drawer),
            ("hardware.scale", self.simulate_scale),
            ("hardware.fiscal", self.simulate_fiscal),
        ]
        row = QHBoxLayout()
        for key, callback in actions:
            button = QPushButton()
            button.setProperty("textKey", key)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.hardware_text, 1)
        return page

    def _build_placeholder_page(self, page_id: str) -> QWidget:
        """Build a disabled future-module page."""

        page, layout, _title = self._page("placeholder.title")
        body = QLabel(self.translator.text("placeholder.body"))
        body.setWordWrap(True)
        body.setProperty("bodyKey", "placeholder.body")
        layout.addWidget(body)
        layout.addStretch(1)
        page.setProperty("moduleId", page_id)
        return page

    def refresh_dashboard(self) -> None:
        """Refresh server status."""

        self._run_api(lambda: self.dashboard_text.setPlainText(json.dumps(self.api_client.get_status(), indent=2, ensure_ascii=False)))

    def _on_page_changed(self, row: int) -> None:
        """Switch pages and refresh data for the selected foundation view."""

        self.stack.setCurrentIndex(row)
        item = self.nav.item(row)
        if item is None:
            return
        page_id = str(item.data(Qt.ItemDataRole.UserRole))
        if page_id == "users":
            self.refresh_users()
        elif page_id == "roles":
            self.refresh_roles()
        elif page_id == "settings":
            self.refresh_settings()

    def refresh_users(self) -> None:
        """Refresh users table."""

        def action() -> None:
            users = self.api_client.get_users()
            self.users_table.setRowCount(len(users))
            for row, user in enumerate(users):
                values = [user.get("id"), user.get("username"), user.get("full_name"), user.get("role_name"), user.get("is_active")]
                for col, value in enumerate(values):
                    self.users_table.setItem(row, col, QTableWidgetItem(str(value)))

        self._run_api(action)

    def refresh_roles(self) -> None:
        """Refresh roles."""

        self._run_api(lambda: self.roles_text.setPlainText(json.dumps(self.api_client.get_roles(), indent=2, ensure_ascii=False)))

    def refresh_settings(self) -> None:
        """Refresh settings editor."""

        self._run_api(lambda: self.settings_text.setPlainText(json.dumps(self.api_client.get_settings(), indent=2, ensure_ascii=False)))

    def save_settings(self) -> None:
        """Save JSON settings."""

        def action() -> None:
            values = json.loads(self.settings_text.toPlainText() or "{}")
            updated = self.api_client.update_settings(values)
            self.settings_text.setPlainText(json.dumps(updated, indent=2, ensure_ascii=False))
            QMessageBox.information(self, self.translator.text("common.success"), self.translator.text("common.success"))

        self._run_api(action)

    def create_user_dialog(self) -> None:
        """Open a minimal create-user dialog."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("users.create"))
        form = QFormLayout(dialog)
        username = QLineEdit()
        full_name = QLineEdit()
        password = QLineEdit()
        password.setEchoMode(QLineEdit.EchoMode.Password)
        role = QLineEdit("Cashier")
        form.addRow("Username", username)
        form.addRow("Full name", full_name)
        form.addRow("Password", password)
        form.addRow("Role", role)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            self.api_client.create_user(
                {
                    "username": username.text().strip(),
                    "full_name": full_name.text().strip(),
                    "password": password.text(),
                    "role_name": role.text().strip() or "Cashier",
                }
            )
            self.refresh_users()

        self._run_api(action)

    def simulate_scan(self) -> None:
        """Run scanner simulator."""

        self.hardware_text.appendPlainText(f"Scanner: {self.hardware.scan()}")

    def simulate_print(self) -> None:
        """Run printer simulator."""

        self.hardware_text.appendPlainText(f"Printer: {self.hardware.print_receipt()}")

    def simulate_drawer(self) -> None:
        """Run cash drawer simulator."""

        self.hardware_text.appendPlainText(f"Drawer: {self.hardware.open_drawer()}")

    def simulate_scale(self) -> None:
        """Run scale simulator."""

        self.hardware_text.appendPlainText(f"Scale: {self.hardware.read_weight()} kg")

    def simulate_fiscal(self) -> None:
        """Run fiscal-device simulator."""

        self.hardware_text.appendPlainText(f"Fiscal: {self.hardware.register_operation(Decimal('0.00'))}")

    def _run_api(self, action: Callable[[], None]) -> None:
        """Run an API action and show a simple error dialog."""

        try:
            action()
        except (ApiClientError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, self.translator.text("common.error"), str(exc))

    def retranslate(self) -> None:
        """Apply active translations to visible labels."""

        self.setWindowTitle(self.translator.text("app.title"))
        user = self.api_client.current_user
        user_text = f"{user.full_name} ({user.role_name})" if user else ""
        self.status_label.setText(f"{self.translator.text('main.connected')}: {user_text}")
        self.logout_button.setText(self.translator.text("main.logout"))
        for page_id, item in self.nav_items.items():
            key = f"nav.{page_id}"
            item.setText(self.translator.text(key))
        for label in self.findChildren(QLabel):
            title_key = label.property("titleKey")
            body_key = label.property("bodyKey")
            if title_key:
                label.setText(self.translator.text(str(title_key)))
            if body_key:
                label.setText(self.translator.text(str(body_key)))
        for button in self.findChildren(QPushButton):
            text_key = button.property("textKey")
            if text_key:
                button.setText(self.translator.text(str(text_key)))

    def _apply_permissions(self) -> None:
        """Hide navigation pages that the current user cannot reasonably use yet."""

        user = self.api_client.current_user
        permissions = set(user.permissions if user else [])
        page_permissions = {
            "dashboard": None,
            "users": "admin.manage_users",
            "roles": "admin.manage_roles",
            "settings": "settings.view",
            "hardware": None,
            "catalog": "goods.view",
            "warehouse": "warehouse.view",
            "purchase": "purchase.view",
            "pricing": "pricing.view",
            "sales": "sale.view",
            "cashier": "cashier.view",
            "reports": "reports.view",
        }
        for page_id, required in page_permissions.items():
            item = self.nav_items.get(page_id)
            if item is not None:
                item.setHidden(required is not None and required not in permissions)

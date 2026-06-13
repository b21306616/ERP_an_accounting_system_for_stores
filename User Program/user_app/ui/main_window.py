"""Main endpoint-client shell."""

from __future__ import annotations

from datetime import date
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
from user_app.core.i18n import (
    CATALOG_TABLE_HEADER_KEYS,
    COUNTERPARTY_TABLE_HEADER_KEYS,
    PRICING_TABLE_HEADER_KEYS,
    PURCHASE_TABLE_HEADER_KEYS,
    USER_TABLE_HEADER_KEYS,
    WAREHOUSE_TABLE_HEADER_KEYS,
    Translator,
)
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
        self.language_combo.addItem("English", "en")
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
        self._add_page("catalog", self._build_catalog_page())
        self._add_page("warehouse", self._build_warehouse_page())
        self._add_page("counterparties", self._build_counterparties_page())
        self._add_page("pricing", self._build_pricing_page())
        self._add_page("purchase", self._build_purchase_page())
        for page_id in ("sales", "cashier", "reports"):
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
        self.users_table = QTableWidget(0, len(USER_TABLE_HEADER_KEYS))
        self._set_users_table_headers()
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

    def _build_catalog_page(self) -> QWidget:
        """Build product catalog page."""

        page, layout, _title = self._page("catalog.title")
        action_row = QHBoxLayout()
        self.catalog_search = QLineEdit()
        self.catalog_search.setPlaceholderText(self.translator.text("catalog.search"))
        refresh = QPushButton()
        refresh.setProperty("textKey", "catalog.refresh")
        refresh.clicked.connect(self.refresh_catalog)
        create_group = QPushButton()
        create_group.setProperty("textKey", "catalog.create_group")
        create_group.clicked.connect(self.create_product_group_dialog)
        create_product = QPushButton()
        create_product.setProperty("textKey", "catalog.create_product")
        create_product.clicked.connect(self.create_product_dialog)
        create_service = QPushButton()
        create_service.setProperty("textKey", "catalog.create_service")
        create_service.clicked.connect(self.create_service_dialog)
        find_barcode = QPushButton()
        find_barcode.setProperty("textKey", "catalog.find_barcode")
        find_barcode.clicked.connect(self.find_barcode_dialog)
        for widget in (self.catalog_search, refresh, create_group, create_product, create_service, find_barcode):
            action_row.addWidget(widget)
        action_row.addStretch(1)

        self.catalog_table = QTableWidget(0, len(CATALOG_TABLE_HEADER_KEYS))
        self._set_catalog_table_headers()
        layout.addLayout(action_row)
        layout.addWidget(self.catalog_table, 1)
        return page

    def _build_warehouse_page(self) -> QWidget:
        """Build warehouse balances and document actions page."""

        page, layout, _title = self._page("warehouse.title")
        action_row = QHBoxLayout()
        refresh = QPushButton()
        refresh.setProperty("textKey", "warehouse.refresh")
        refresh.clicked.connect(self.refresh_warehouse)
        create_warehouse = QPushButton()
        create_warehouse.setProperty("textKey", "warehouse.create_warehouse")
        create_warehouse.clicked.connect(self.create_warehouse_dialog)
        opening_inventory = QPushButton()
        opening_inventory.setProperty("textKey", "warehouse.opening_inventory")
        opening_inventory.clicked.connect(self.opening_inventory_dialog)
        transfer = QPushButton()
        transfer.setProperty("textKey", "warehouse.transfer")
        transfer.clicked.connect(self.transfer_dialog)
        writeoff = QPushButton()
        writeoff.setProperty("textKey", "warehouse.writeoff")
        writeoff.clicked.connect(self.writeoff_dialog)
        for widget in (refresh, create_warehouse, opening_inventory, transfer, writeoff):
            action_row.addWidget(widget)
        action_row.addStretch(1)

        self.warehouse_table = QTableWidget(0, len(WAREHOUSE_TABLE_HEADER_KEYS))
        self._set_warehouse_table_headers()
        self.warehouse_movements_text = QPlainTextEdit()
        self.warehouse_movements_text.setReadOnly(True)
        self.warehouse_movements_text.setMinimumHeight(150)
        layout.addLayout(action_row)
        layout.addWidget(self.warehouse_table, 1)
        movements_label = QLabel(self.translator.text("warehouse.movements"))
        movements_label.setProperty("bodyKey", "warehouse.movements")
        layout.addWidget(movements_label)
        layout.addWidget(self.warehouse_movements_text)
        return page

    def _build_counterparties_page(self) -> QWidget:
        """Build counterparties page."""

        page, layout, _title = self._page("counterparties.title")
        action_row = QHBoxLayout()
        self.counterparty_search = QLineEdit()
        self.counterparty_search.setPlaceholderText(self.translator.text("counterparties.search"))
        refresh = QPushButton()
        refresh.setProperty("textKey", "counterparties.refresh")
        refresh.clicked.connect(self.refresh_counterparties)
        create = QPushButton()
        create.setProperty("textKey", "counterparties.create")
        create.clicked.connect(self.create_counterparty_dialog)
        for widget in (self.counterparty_search, refresh, create):
            action_row.addWidget(widget)
        action_row.addStretch(1)
        self.counterparties_table = QTableWidget(0, len(COUNTERPARTY_TABLE_HEADER_KEYS))
        self._set_counterparties_table_headers()
        layout.addLayout(action_row)
        layout.addWidget(self.counterparties_table, 1)
        return page

    def _build_pricing_page(self) -> QWidget:
        """Build pricing page."""

        page, layout, _title = self._page("pricing.title")
        action_row = QHBoxLayout()
        refresh = QPushButton()
        refresh.setProperty("textKey", "pricing.refresh")
        refresh.clicked.connect(self.refresh_pricing)
        create = QPushButton()
        create.setProperty("textKey", "pricing.create_price_list")
        create.clicked.connect(self.create_price_list_dialog)
        add_price = QPushButton()
        add_price.setProperty("textKey", "pricing.add_price")
        add_price.clicked.connect(self.add_price_dialog)
        for widget in (refresh, create, add_price):
            action_row.addWidget(widget)
        action_row.addStretch(1)
        self.pricing_table = QTableWidget(0, len(PRICING_TABLE_HEADER_KEYS))
        self._set_pricing_table_headers()
        layout.addLayout(action_row)
        layout.addWidget(self.pricing_table, 1)
        return page

    def _build_purchase_page(self) -> QWidget:
        """Build purchase invoices and supplier payment page."""

        page, layout, _title = self._page("purchase.title")
        action_row = QHBoxLayout()
        refresh = QPushButton()
        refresh.setProperty("textKey", "purchase.refresh")
        refresh.clicked.connect(self.refresh_purchase)
        create_invoice = QPushButton()
        create_invoice.setProperty("textKey", "purchase.create_invoice")
        create_invoice.clicked.connect(self.create_purchase_invoice_dialog)
        create_payment = QPushButton()
        create_payment.setProperty("textKey", "purchase.create_payment")
        create_payment.clicked.connect(self.create_supplier_payment_dialog)
        for widget in (refresh, create_invoice, create_payment):
            action_row.addWidget(widget)
        action_row.addStretch(1)
        self.purchase_table = QTableWidget(0, len(PURCHASE_TABLE_HEADER_KEYS))
        self._set_purchase_table_headers()
        self.purchase_debt_text = QPlainTextEdit()
        self.purchase_debt_text.setReadOnly(True)
        self.purchase_debt_text.setMinimumHeight(130)
        layout.addLayout(action_row)
        layout.addWidget(self.purchase_table, 1)
        layout.addWidget(self.purchase_debt_text)
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
        elif page_id == "catalog":
            self.refresh_catalog()
        elif page_id == "warehouse":
            self.refresh_warehouse()
        elif page_id == "counterparties":
            self.refresh_counterparties()
        elif page_id == "pricing":
            self.refresh_pricing()
        elif page_id == "purchase":
            self.refresh_purchase()

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

    def refresh_catalog(self) -> None:
        """Refresh product catalog table."""

        def action() -> None:
            products = self.api_client.get_products(self.catalog_search.text().strip() or None)
            self.catalog_table.setRowCount(len(products))
            for row, product in enumerate(products):
                values = [
                    product.get("id"),
                    product.get("sku") or product.get("code"),
                    product.get("name") or product.get("name_ru"),
                    product.get("retail_price"),
                    product.get("is_active"),
                ]
                for col, value in enumerate(values):
                    self.catalog_table.setItem(row, col, QTableWidgetItem(str(value)))

        self._run_api(action)

    def refresh_warehouse(self) -> None:
        """Refresh warehouse balances and movement log."""

        def action() -> None:
            balances = self.api_client.get_stock_balances()
            self.warehouse_table.setRowCount(len(balances))
            for row, balance in enumerate(balances):
                values = [
                    balance.get("id"),
                    balance.get("warehouse_name") or balance.get("warehouse_code"),
                    balance.get("product_name") or balance.get("product_sku"),
                    balance.get("quantity"),
                    balance.get("avg_cost_tmt"),
                ]
                for col, value in enumerate(values):
                    self.warehouse_table.setItem(row, col, QTableWidgetItem(str(value)))
            movements = self.api_client.get_stock_movements()
            self.warehouse_movements_text.setPlainText(json.dumps(movements, indent=2, ensure_ascii=False))

        self._run_api(action)

    def refresh_counterparties(self) -> None:
        """Refresh counterparties table with debt balances."""

        def action() -> None:
            rows = self.api_client.get_counterparties(self.counterparty_search.text().strip() or None, include_debt=True)
            self.counterparties_table.setRowCount(len(rows))
            for row, counterparty in enumerate(rows):
                debt = counterparty.get("debt") or {}
                debt_text = f"R {debt.get('receivable', '0.00')} / P {debt.get('payable', '0.00')}"
                values = [
                    counterparty.get("id"),
                    counterparty.get("code"),
                    counterparty.get("name"),
                    counterparty.get("role_flags"),
                    debt_text,
                ]
                for col, value in enumerate(values):
                    self.counterparties_table.setItem(row, col, QTableWidgetItem(str(value)))

        self._run_api(action)

    def refresh_pricing(self) -> None:
        """Refresh price-list table."""

        def action() -> None:
            rows = self.api_client.get_price_lists()
            self.pricing_table.setRowCount(len(rows))
            for row, price_list in enumerate(rows):
                values = [
                    price_list.get("id"),
                    price_list.get("name_ru"),
                    price_list.get("currency_code") or price_list.get("currency_id"),
                    price_list.get("is_default"),
                ]
                for col, value in enumerate(values):
                    self.pricing_table.setItem(row, col, QTableWidgetItem(str(value)))

        self._run_api(action)

    def refresh_purchase(self) -> None:
        """Refresh purchase invoices and payable ledger."""

        def action() -> None:
            invoices = self.api_client.get_purchase_invoices()
            self.purchase_table.setRowCount(len(invoices))
            for row, invoice in enumerate(invoices):
                values = [
                    invoice.get("id"),
                    invoice.get("doc_number"),
                    invoice.get("counterparty_name"),
                    invoice.get("total_amount_tmt"),
                    invoice.get("status"),
                    invoice.get("payment_status"),
                ]
                for col, value in enumerate(values):
                    self.purchase_table.setItem(row, col, QTableWidgetItem(str(value)))
            ledger = self.api_client.get_debt_ledger(debt_type="payable")
            self.purchase_debt_text.setPlainText(json.dumps(ledger, indent=2, ensure_ascii=False))

        self._run_api(action)

    def _default_currency_id(self) -> int:
        """Return the seeded TMT currency id, or the first available currency id."""

        currencies = self.api_client.get_currencies()
        for currency in currencies:
            if currency.get("code") == "TMT":
                return int(currency["id"])
        if not currencies:
            raise ValueError("No currencies are configured.")
        return int(currencies[0]["id"])

    def create_product_group_dialog(self) -> None:
        """Create a product group."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("catalog.create_group"))
        form = QFormLayout(dialog)
        code = QLineEdit()
        name_ru = QLineEdit()
        name_tk = QLineEdit()
        form.addRow(self.translator.text("catalog.form.code"), code)
        form.addRow(self.translator.text("catalog.form.name_ru"), name_ru)
        form.addRow(self.translator.text("catalog.form.name_tk"), name_tk)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._run_api(
            lambda: self.api_client.create_product_group(
                {
                    "code": code.text().strip(),
                    "name_ru": name_ru.text().strip(),
                    "name_tk": name_tk.text().strip() or None,
                }
            )
        )

    def create_product_dialog(self) -> None:
        """Create a product and optional barcode."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("catalog.create_product"))
        form = QFormLayout(dialog)
        code = QLineEdit()
        name_ru = QLineEdit()
        name_tk = QLineEdit()
        price = QLineEdit("0")
        barcode = QLineEdit()
        for key, widget in (
            ("catalog.form.code", code),
            ("catalog.form.name_ru", name_ru),
            ("catalog.form.name_tk", name_tk),
            ("catalog.form.price", price),
            ("catalog.form.barcode", barcode),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            product = self.api_client.create_product(
                {
                    "sku": code.text().strip(),
                    "name": name_ru.text().strip(),
                    "name_tk": name_tk.text().strip() or None,
                    "retail_price": price.text().strip() or "0",
                }
            )
            barcode_value = barcode.text().strip()
            if barcode_value:
                self.api_client.add_product_barcode(int(product["id"]), barcode_value)
            self.refresh_catalog()

        self._run_api(action)

    def create_service_dialog(self) -> None:
        """Create a service."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("catalog.create_service"))
        form = QFormLayout(dialog)
        code = QLineEdit()
        name_ru = QLineEdit()
        name_tk = QLineEdit()
        price = QLineEdit("0")
        for key, widget in (
            ("catalog.form.code", code),
            ("catalog.form.name_ru", name_ru),
            ("catalog.form.name_tk", name_tk),
            ("catalog.form.price", price),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._run_api(
            lambda: self.api_client.create_service(
                {
                    "code": code.text().strip(),
                    "name_ru": name_ru.text().strip(),
                    "name_tk": name_tk.text().strip() or None,
                    "default_price": price.text().strip() or "0",
                }
            )
        )

    def find_barcode_dialog(self) -> None:
        """Find a product by barcode."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("catalog.find_barcode"))
        form = QFormLayout(dialog)
        barcode = QLineEdit()
        form.addRow(self.translator.text("catalog.form.barcode"), barcode)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            product = self.api_client.find_product_by_barcode(barcode.text().strip())
            QMessageBox.information(
                self,
                self.translator.text("catalog.find_barcode"),
                json.dumps(product, indent=2, ensure_ascii=False),
            )

        self._run_api(action)

    def create_counterparty_dialog(self) -> None:
        """Create a supplier/customer counterparty."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("counterparties.create"))
        form = QFormLayout(dialog)
        code = QLineEdit()
        name = QLineEdit()
        role = QLineEdit("1")
        phone = QLineEdit()
        address = QLineEdit()
        for key, widget in (
            ("counterparties.form.code", code),
            ("counterparties.form.name", name),
            ("counterparties.form.role", role),
            ("counterparties.form.phone", phone),
            ("counterparties.form.address", address),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            role_flags = int(role.text().strip() or "1")
            self.api_client.create_counterparty(
                {
                    "code": code.text().strip(),
                    "name": name.text().strip(),
                    "role_flags": role_flags,
                    "counterparty_type": "supplier" if role_flags == 1 else "both" if role_flags == 3 else "customer",
                    "phone": phone.text().strip() or None,
                    "address": address.text().strip() or None,
                }
            )
            self.refresh_counterparties()

        self._run_api(action)

    def create_price_list_dialog(self) -> None:
        """Create a price list."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("pricing.create_price_list"))
        form = QFormLayout(dialog)
        name = QLineEdit()
        currency_id = QLineEdit()
        is_default = QLineEdit("true")
        form.addRow(self.translator.text("pricing.form.name"), name)
        form.addRow(self.translator.text("pricing.form.currency_id"), currency_id)
        form.addRow(self.translator.text("pricing.table.default"), is_default)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            selected_currency_id = int(currency_id.text().strip() or self._default_currency_id())
            self.api_client.create_price_list(
                {
                    "name_ru": name.text().strip(),
                    "currency_id": selected_currency_id,
                    "is_default": is_default.text().strip().lower() in {"1", "true", "yes", "да"},
                }
            )
            self.refresh_pricing()

        self._run_api(action)

    def add_price_dialog(self) -> None:
        """Add a product price to a price list."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("pricing.add_price"))
        form = QFormLayout(dialog)
        price_list_id = QLineEdit()
        product_id = QLineEdit()
        product_price = QLineEdit("0")
        valid_from = QLineEdit(date.today().isoformat())
        for key, widget in (
            ("pricing.form.price_list_id", price_list_id),
            ("pricing.form.product_id", product_id),
            ("pricing.form.price", product_price),
            ("pricing.form.valid_from", valid_from),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            self.api_client.add_price_list_item(
                int(price_list_id.text().strip()),
                {
                    "product_id": int(product_id.text().strip()),
                    "price_tmt": product_price.text().strip() or "0",
                    "valid_from": valid_from.text().strip() or date.today().isoformat(),
                },
            )
            self.refresh_pricing()

        self._run_api(action)

    def create_purchase_invoice_dialog(self) -> None:
        """Create and post a one-line purchase invoice."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("purchase.create_invoice"))
        form = QFormLayout(dialog)
        supplier_id = QLineEdit()
        warehouse_id = QLineEdit()
        currency_id = QLineEdit()
        product_id = QLineEdit()
        quantity = QLineEdit("1")
        purchase_price = QLineEdit("0")
        for key, widget in (
            ("purchase.form.supplier_id", supplier_id),
            ("purchase.form.warehouse_id", warehouse_id),
            ("purchase.form.currency_id", currency_id),
            ("purchase.form.product_id", product_id),
            ("purchase.form.quantity", quantity),
            ("purchase.form.price", purchase_price),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            invoice = self.api_client.create_purchase_invoice(
                {
                    "counterparty_id": int(supplier_id.text().strip()),
                    "warehouse_id": int(warehouse_id.text().strip()),
                    "currency_id": int(currency_id.text().strip() or self._default_currency_id()),
                    "currency_rate": "1",
                    "lines": [
                        {
                            "product_id": int(product_id.text().strip()),
                            "quantity": quantity.text().strip() or "1",
                            "price_cur": purchase_price.text().strip() or "0",
                        }
                    ],
                }
            )
            self.api_client.post_purchase_invoice(int(invoice["id"]))
            self.refresh_purchase()
            self.refresh_warehouse()

        self._run_api(action)

    def create_supplier_payment_dialog(self) -> None:
        """Create an outgoing supplier payment."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("purchase.create_payment"))
        form = QFormLayout(dialog)
        supplier_id = QLineEdit()
        invoice_id = QLineEdit()
        amount = QLineEdit("0")
        for key, widget in (
            ("purchase.form.supplier_id", supplier_id),
            ("purchase.form.invoice_id", invoice_id),
            ("purchase.form.payment_amount", amount),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            self.api_client.create_payment(
                {
                    "counterparty_id": int(supplier_id.text().strip()),
                    "direction": "outgoing",
                    "payment_method": "cash",
                    "amount_tmt": amount.text().strip() or "0",
                    "allocations": [
                        {
                            "doc_type": "purchase_invoice",
                            "doc_id": int(invoice_id.text().strip()),
                            "allocated_amount": amount.text().strip() or "0",
                        }
                    ],
                }
            )
            self.refresh_purchase()
            self.refresh_counterparties()

        self._run_api(action)

    def create_warehouse_dialog(self) -> None:
        """Create a warehouse."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("warehouse.create_warehouse"))
        form = QFormLayout(dialog)
        code = QLineEdit()
        name = QLineEdit()
        location = QLineEdit()
        form.addRow(self.translator.text("warehouse.form.code"), code)
        form.addRow(self.translator.text("warehouse.form.name"), name)
        form.addRow(self.translator.text("warehouse.form.location"), location)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            self.api_client.create_warehouse(
                {
                    "code": code.text().strip(),
                    "name": name.text().strip(),
                    "location": location.text().strip() or None,
                }
            )
            self.refresh_warehouse()

        self._run_api(action)

    def opening_inventory_dialog(self) -> None:
        """Create and post an opening inventory line."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("warehouse.opening_inventory"))
        form = QFormLayout(dialog)
        warehouse_id = QLineEdit()
        product_id = QLineEdit()
        qty_actual = QLineEdit("0")
        unit_cost = QLineEdit("0")
        for key, widget in (
            ("warehouse.form.warehouse_id", warehouse_id),
            ("warehouse.form.product_id", product_id),
            ("warehouse.form.quantity", qty_actual),
            ("warehouse.form.unit_cost", unit_cost),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            inventory = self.api_client.create_inventory(
                {
                    "warehouse_id": int(warehouse_id.text().strip()),
                    "lines": [
                        {
                            "product_id": int(product_id.text().strip()),
                            "qty_actual": qty_actual.text().strip() or "0",
                            "unit_cost_tmt": unit_cost.text().strip() or "0",
                        }
                    ],
                }
            )
            self.api_client.post_inventory(int(inventory["id"]))
            self.refresh_warehouse()

        self._run_api(action)

    def transfer_dialog(self) -> None:
        """Create, send, and receive a one-line stock transfer."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("warehouse.transfer"))
        form = QFormLayout(dialog)
        source_warehouse_id = QLineEdit()
        target_warehouse_id = QLineEdit()
        product_id = QLineEdit()
        quantity = QLineEdit("0")
        for key, widget in (
            ("warehouse.form.source_warehouse_id", source_warehouse_id),
            ("warehouse.form.target_warehouse_id", target_warehouse_id),
            ("warehouse.form.product_id", product_id),
            ("warehouse.form.quantity", quantity),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            transfer = self.api_client.create_stock_transfer(
                {
                    "source_warehouse_id": int(source_warehouse_id.text().strip()),
                    "target_warehouse_id": int(target_warehouse_id.text().strip()),
                    "lines": [
                        {
                            "product_id": int(product_id.text().strip()),
                            "quantity": quantity.text().strip() or "0",
                        }
                    ],
                }
            )
            transfer_id = int(transfer["id"])
            self.api_client.send_stock_transfer(transfer_id)
            self.api_client.receive_stock_transfer(transfer_id)
            self.refresh_warehouse()

        self._run_api(action)

    def writeoff_dialog(self) -> None:
        """Create and post a one-line write-off."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("warehouse.writeoff"))
        form = QFormLayout(dialog)
        warehouse_id = QLineEdit()
        product_id = QLineEdit()
        quantity = QLineEdit("0")
        reason = QLineEdit("other")
        for key, widget in (
            ("warehouse.form.warehouse_id", warehouse_id),
            ("warehouse.form.product_id", product_id),
            ("warehouse.form.quantity", quantity),
            ("warehouse.form.reason", reason),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            writeoff = self.api_client.create_stock_writeoff(
                {
                    "warehouse_id": int(warehouse_id.text().strip()),
                    "reason_code": reason.text().strip() or "other",
                    "lines": [
                        {
                            "product_id": int(product_id.text().strip()),
                            "quantity": quantity.text().strip() or "0",
                        }
                    ],
                }
            )
            self.api_client.post_stock_writeoff(int(writeoff["id"]))
            self.refresh_warehouse()

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
        form.addRow(self.translator.text("users.form.username"), username)
        form.addRow(self.translator.text("users.form.full_name"), full_name)
        form.addRow(self.translator.text("users.form.password"), password)
        form.addRow(self.translator.text("users.form.role"), role)
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

        self.hardware_text.appendPlainText(f"{self.translator.text('hardware.log.scanner')}: {self.hardware.scan()}")

    def simulate_print(self) -> None:
        """Run printer simulator."""

        self.hardware_text.appendPlainText(f"{self.translator.text('hardware.log.printer')}: {self.hardware.print_receipt()}")

    def simulate_drawer(self) -> None:
        """Run cash drawer simulator."""

        self.hardware_text.appendPlainText(f"{self.translator.text('hardware.log.drawer')}: {self.hardware.open_drawer()}")

    def simulate_scale(self) -> None:
        """Run scale simulator."""

        self.hardware_text.appendPlainText(f"{self.translator.text('hardware.log.scale')}: {self.hardware.read_weight()} kg")

    def simulate_fiscal(self) -> None:
        """Run fiscal-device simulator."""

        self.hardware_text.appendPlainText(f"{self.translator.text('hardware.log.fiscal')}: {self.hardware.register_operation(Decimal('0.00'))}")

    def _run_api(self, action: Callable[[], None]) -> None:
        """Run an API action and show a simple error dialog."""

        try:
            action()
        except (ApiClientError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, self.translator.text("common.error"), str(exc))

    def _set_users_table_headers(self) -> None:
        """Apply translated column headers to the users table."""

        self.users_table.setHorizontalHeaderLabels([self.translator.text(key) for key in USER_TABLE_HEADER_KEYS])

    def _set_catalog_table_headers(self) -> None:
        """Apply translated column headers to the catalog table."""

        self.catalog_table.setHorizontalHeaderLabels([self.translator.text(key) for key in CATALOG_TABLE_HEADER_KEYS])

    def _set_warehouse_table_headers(self) -> None:
        """Apply translated column headers to the warehouse table."""

        self.warehouse_table.setHorizontalHeaderLabels([self.translator.text(key) for key in WAREHOUSE_TABLE_HEADER_KEYS])

    def _set_counterparties_table_headers(self) -> None:
        """Apply translated column headers to the counterparties table."""

        self.counterparties_table.setHorizontalHeaderLabels(
            [self.translator.text(key) for key in COUNTERPARTY_TABLE_HEADER_KEYS]
        )

    def _set_pricing_table_headers(self) -> None:
        """Apply translated column headers to the pricing table."""

        self.pricing_table.setHorizontalHeaderLabels([self.translator.text(key) for key in PRICING_TABLE_HEADER_KEYS])

    def _set_purchase_table_headers(self) -> None:
        """Apply translated column headers to the purchase table."""

        self.purchase_table.setHorizontalHeaderLabels([self.translator.text(key) for key in PURCHASE_TABLE_HEADER_KEYS])

    def retranslate(self) -> None:
        """Apply active translations to visible labels."""

        self.setWindowTitle(self.translator.text("app.title"))
        self._set_users_table_headers()
        self._set_catalog_table_headers()
        self._set_warehouse_table_headers()
        self._set_counterparties_table_headers()
        self._set_pricing_table_headers()
        self._set_purchase_table_headers()
        if hasattr(self, "catalog_search"):
            self.catalog_search.setPlaceholderText(self.translator.text("catalog.search"))
        if hasattr(self, "counterparty_search"):
            self.counterparty_search.setPlaceholderText(self.translator.text("counterparties.search"))
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
            "counterparties": "counterparty.view",
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

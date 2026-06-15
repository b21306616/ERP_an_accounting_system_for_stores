"""Main endpoint-client shell."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from user_app.api.client import ApiClient, ApiClientError
from user_app.core.i18n import (
    CATALOG_TABLE_HEADER_KEYS,
    CASHIER_CART_HEADER_KEYS,
    CASHIER_TABLE_HEADER_KEYS,
    COUNTERPARTY_TABLE_HEADER_KEYS,
    PRICING_TABLE_HEADER_KEYS,
    PURCHASE_TABLE_HEADER_KEYS,
    SALES_TABLE_HEADER_KEYS,
    USER_TABLE_HEADER_KEYS,
    WAREHOUSE_TABLE_HEADER_KEYS,
    Translator,
)
from user_app.hardware.simulator import HardwareSimulator
from user_app.ui.selectors import ReferenceSelectorDialog


class MainWindow(QWidget):
    """Role-aware main shell for the endpoint client."""

    logout_requested = pyqtSignal()
    language_changed = pyqtSignal(str)

    def __init__(self, api_client: ApiClient, translator: Translator) -> None:
        super().__init__()
        self.api_client = api_client
        self.translator = translator
        self.hardware = HardwareSimulator()
        self.cashier_cart: list[dict[str, object]] = []
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
        self._add_page("sales", self._build_sales_page())
        self._add_page("cashier", self._build_cashier_page())
        self._add_page("reports", self._build_reports_page())

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

    def _add_selector_row(
        self,
        form: QFormLayout,
        label_key: str,
        field: QLineEdit,
        selector: Callable[[QLineEdit], None],
    ) -> None:
        """Add a form row with an ID field and a searchable selector button."""

        row = QHBoxLayout()
        row.addWidget(field, 1)
        button = QPushButton("...")
        button.setFixedWidth(34)
        button.clicked.connect(lambda _checked=False: selector(field))
        row.addWidget(button)
        form.addRow(self.translator.text(label_key), row)

    def _select_reference(
        self,
        title: str,
        rows_provider: Callable[[], list[dict[str, object]]],
        target: QLineEdit,
        columns: list[tuple[str, str]],
        *,
        display_target: QLineEdit | None = None,
        display_fields: tuple[str, ...] = (),
        price_target: QLineEdit | None = None,
        price_field: str | None = None,
        id_field: str = "id",
    ) -> None:
        """Open a selector dialog and copy the selected row into target fields."""

        try:
            rows = rows_provider()
        except ApiClientError as exc:
            QMessageBox.critical(self, self.translator.text("common.error"), str(exc))
            return
        dialog = ReferenceSelectorDialog(title, rows, columns, search_placeholder=self.translator.text("common.search"), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_row()
        if not selected:
            return
        target.setText(str(selected.get(id_field, "") or ""))
        if display_target is not None and display_fields:
            values = [str(selected.get(field, "") or "") for field in display_fields if selected.get(field) not in (None, "")]
            display_target.setText(" - ".join(values))
        if price_target is not None and price_field is not None and selected.get(price_field) is not None:
            price_target.setText(str(selected.get(price_field)))

    def _select_product_id(self, target: QLineEdit, name_target: QLineEdit | None = None, price_target: QLineEdit | None = None) -> None:
        """Select a product and copy its id to a line edit."""

        self._select_reference(
            self.translator.text("catalog.title"),
            lambda: self.api_client.get_products(),
            target,
            [("id", "ID"), ("sku", "SKU"), ("name", "Name"), ("retail_price", "Price")],
            display_target=name_target,
            display_fields=("sku", "name"),
            price_target=price_target,
            price_field="retail_price",
        )

    def _select_warehouse_id(self, target: QLineEdit) -> None:
        self._select_reference(self.translator.text("warehouse.title"), lambda: self.api_client.get_warehouses(), target, [("id", "ID"), ("code", "Code"), ("name", "Name")])

    def _select_counterparty_id(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("counterparties.title"),
            lambda: self.api_client.get_counterparties(include_debt=True),
            target,
            [("id", "ID"), ("code", "Code"), ("name", "Name"), ("counterparty_type", "Type"), ("debt_balance_tmt", "Debt")],
        )

    def _select_currency_id(self, target: QLineEdit) -> None:
        self._select_reference(self.translator.text("pricing.form.currency_id"), lambda: self.api_client.get_currencies(), target, [("id", "ID"), ("code", "Code"), ("name", "Name")])

    def _select_price_list_id(self, target: QLineEdit) -> None:
        self._select_reference(self.translator.text("pricing.create_price_list"), lambda: self.api_client.get_price_lists(), target, [("id", "ID"), ("name_ru", "Name"), ("currency_code", "Currency"), ("is_default", "Default")])

    def _select_cash_register_id(self, target: QLineEdit) -> None:
        self._select_reference(self.translator.text("cashier.create_register"), lambda: self.api_client.get_cash_registers(), target, [("id", "ID"), ("name", "Name"), ("warehouse_id", "Warehouse"), ("is_active", "Active")])

    def _select_cash_shift_id(self, target: QLineEdit) -> None:
        self._select_reference(self.translator.text("cashier.form.shift_id"), lambda: self.api_client.get_cash_shifts(), target, [("id", "ID"), ("cash_register_name", "Register"), ("opened_at", "Opened"), ("status", "Status")])

    def _select_purchase_invoice_id(self, target: QLineEdit) -> None:
        self._select_reference(self.translator.text("purchase.create_invoice"), lambda: self.api_client.get_purchase_invoices(), target, [("id", "ID"), ("doc_number", "Number"), ("counterparty_name", "Supplier"), ("total_amount_tmt", "Total"), ("status", "Status")])

    def _select_purchase_order_id(self, target: QLineEdit) -> None:
        self._select_reference(self.translator.text("purchase.create_order"), lambda: self.api_client.get_purchase_orders(), target, [("id", "ID"), ("doc_number", "Number"), ("counterparty_name", "Supplier"), ("total_amount_tmt", "Total"), ("status", "Status")])

    def _select_purchase_order_line_id(self, target: QLineEdit, order_id: QLineEdit) -> None:
        """Select a line from the selected purchase order."""

        order_text = order_id.text().strip()
        if not order_text:
            QMessageBox.warning(self, self.translator.text("common.error"), self.translator.text("purchase.form.order_id"))
            return
        try:
            order = next((row for row in self.api_client.get_purchase_orders() if int(row.get("id", 0)) == int(order_text)), None)
        except (ApiClientError, ValueError) as exc:
            QMessageBox.critical(self, self.translator.text("common.error"), str(exc))
            return
        if not order:
            QMessageBox.warning(self, self.translator.text("common.error"), self.translator.text("purchase.form.order_id"))
            return
        lines = list(order.get("lines", []))
        self._select_reference(
            self.translator.text("purchase.form.order_line_id"),
            lambda: lines,
            target,
            [("id", "ID"), ("product_name", "Product"), ("quantity_ordered", "Qty"), ("amount_tmt", "Amount")],
        )

    def _select_sale_id(self, target: QLineEdit) -> None:
        self._select_reference(self.translator.text("sales.create_sale"), lambda: self.api_client.get_sales(), target, [("id", "ID"), ("doc_number", "Number"), ("counterparty_name", "Customer"), ("total_amount_tmt", "Total"), ("status", "Status")])

    def _select_sale_line_id(self, target: QLineEdit, sale_id: QLineEdit) -> None:
        """Select a line from the selected sale document."""

        sale_text = sale_id.text().strip()
        if not sale_text:
            QMessageBox.warning(self, self.translator.text("common.error"), self.translator.text("sales.form.sale_id"))
            return
        try:
            sale = next((row for row in self.api_client.get_sales() if int(row.get("id", 0)) == int(sale_text)), None)
        except (ApiClientError, ValueError) as exc:
            QMessageBox.critical(self, self.translator.text("common.error"), str(exc))
            return
        if not sale:
            QMessageBox.warning(self, self.translator.text("common.error"), self.translator.text("sales.form.sale_id"))
            return
        lines = list(sale.get("lines", []))
        self._select_reference(
            self.translator.text("sales.form.sale_line_id"),
            lambda: lines,
            target,
            [("id", "ID"), ("product_name", "Product"), ("quantity", "Qty"), ("amount_tmt", "Amount")],
        )

    def _select_role_name(self, target: QLineEdit) -> None:
        self._select_reference(self.translator.text("roles.title"), lambda: self.api_client.get_roles(), target, [("name", "Role"), ("description", "Description")], id_field="name")

    def _build_dashboard_page(self) -> QWidget:
        """Build dashboard page."""

        page, layout, _title = self._page("dashboard.title")
        
        # Define self.dashboard_text as a hidden/dummy variable to prevent any attribute error
        self.dashboard_text = QPlainTextEdit()
        self.dashboard_text.setReadOnly(True)
        self.dashboard_text.hide()
        
        # Responsive Scroll Area container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 16, 0)
        container_layout.setSpacing(16)
        
        # Header Status Banner
        self.status_banner = QFrame()
        self.status_banner.setObjectName("DashboardStatusBanner")
        self.status_banner.setStyleSheet("""
            QFrame#DashboardStatusBanner {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 16px;
            }
        """)
        banner_shadow = QGraphicsDropShadowEffect(self.status_banner)
        banner_shadow.setBlurRadius(15)
        banner_shadow.setColor(QColor(0, 0, 0, 15))
        banner_shadow.setOffset(0, 4)
        self.status_banner.setGraphicsEffect(banner_shadow)
        
        banner_layout = QHBoxLayout(self.status_banner)
        banner_layout.setContentsMargins(16, 16, 16, 16)
        
        banner_text_layout = QVBoxLayout()
        self.banner_app_name = QLabel("ERP Accounting Server")
        self.banner_app_name.setStyleSheet("font-size: 20px; font-weight: bold; color: #0f172a;")
        
        status_sub_layout = QHBoxLayout()
        status_sub_layout.setSpacing(8)
        self.banner_status_label = QLabel()
        self.banner_status_label.setProperty("titleKey", "sales.table.status")
        self.banner_status_label.setStyleSheet("font-size: 13px; color: #64748b;")
        
        self.banner_status_badge = QLabel("RUNNING")
        self.banner_status_badge.setObjectName("StatusBadge")
        self.banner_status_badge.setStyleSheet("""
            QLabel#StatusBadge {
                background-color: #dcfce7;
                color: #15803d;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 6px;
            }
        """)
        status_sub_layout.addWidget(self.banner_status_label)
        status_sub_layout.addWidget(self.banner_status_badge)
        status_sub_layout.addStretch(1)
        
        banner_text_layout.addWidget(self.banner_app_name)
        banner_text_layout.addLayout(status_sub_layout)
        
        self.dashboard_refresh_btn = QPushButton()
        self.dashboard_refresh_btn.setObjectName("DashboardRefreshBtn")
        self.dashboard_refresh_btn.setProperty("textKey", "dashboard.refresh")
        self.dashboard_refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dashboard_refresh_btn.clicked.connect(self.refresh_dashboard)
        self.dashboard_refresh_btn.setStyleSheet("""
            QPushButton#DashboardRefreshBtn {
                background-color: #2563eb;
                border: none;
                border-radius: 8px;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton#DashboardRefreshBtn:hover {
                background-color: #1d4ed8;
            }
            QPushButton#DashboardRefreshBtn:pressed {
                background-color: #1e3a8a;
            }
        """)
        
        banner_layout.addLayout(banner_text_layout, 1)
        banner_layout.addWidget(self.dashboard_refresh_btn)
        
        container_layout.addWidget(self.status_banner)
        
        # Grid of cards
        grid_layout = QGridLayout()
        grid_layout.setSpacing(16)
        
        def create_card(title_prop_key: str) -> tuple[QFrame, QLabel, QVBoxLayout]:
            card = QFrame()
            card.setObjectName("DashboardCard")
            card.setStyleSheet("""
                QFrame#DashboardCard {
                    background-color: #ffffff;
                    border: 1px solid #e2e8f0;
                    border-radius: 12px;
                    padding: 16px;
                }
            """)
            card_shadow = QGraphicsDropShadowEffect(card)
            card_shadow.setBlurRadius(12)
            card_shadow.setColor(QColor(0, 0, 0, 10))
            card_shadow.setOffset(0, 4)
            card.setGraphicsEffect(card_shadow)
            
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 16, 16, 16)
            card_layout.setSpacing(8)
            
            card_title = QLabel()
            card_title.setProperty("titleKey", title_prop_key)
            card_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #64748b; text-transform: uppercase;")
            card_layout.addWidget(card_title)
            
            return card, card_title, card_layout
            
        # Card 1: User Card
        self.user_card, self.user_card_title, user_layout = create_card("dashboard.current_user")
        user_info_layout = QHBoxLayout()
        user_info_layout.setSpacing(12)
        
        self.user_avatar = QLabel("U")
        self.user_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.user_avatar.setStyleSheet("""
            background-color: #3b82f6;
            color: #ffffff;
            font-size: 20px;
            font-weight: bold;
            border-radius: 20px;
            min-width: 40px;
            max-width: 40px;
            min-height: 40px;
            max-height: 40px;
        """)
        
        user_text_layout = QVBoxLayout()
        self.user_name_val = QLabel("Unknown User")
        self.user_name_val.setStyleSheet("font-size: 16px; font-weight: bold; color: #0f172a;")
        self.user_id_val = QLabel("ID: -")
        self.user_id_val.setStyleSheet("font-size: 12px; color: #64748b;")
        
        user_text_layout.addWidget(self.user_name_val)
        user_text_layout.addWidget(self.user_id_val)
        
        user_info_layout.addWidget(self.user_avatar)
        user_info_layout.addLayout(user_text_layout, 1)
        user_layout.addLayout(user_info_layout)
        user_layout.addStretch(1)
        
        # Card 2: Server Time Card
        self.time_card, self.time_card_title, time_layout = create_card("dashboard.server_time")
        time_info_layout = QHBoxLayout()
        time_info_layout.setSpacing(12)
        
        self.time_icon = QLabel("🕒")
        self.time_icon.setStyleSheet("font-size: 24px;")
        
        time_text_layout = QVBoxLayout()
        self.time_val = QLabel("--:--:--")
        self.time_val.setStyleSheet("font-size: 18px; font-weight: bold; color: #0f172a;")
        self.date_val = QLabel("----- -- --")
        self.date_val.setStyleSheet("font-size: 12px; color: #64748b;")
        
        time_text_layout.addWidget(self.time_val)
        time_text_layout.addWidget(self.date_val)
        
        time_info_layout.addWidget(self.time_icon)
        time_info_layout.addLayout(time_text_layout, 1)
        time_layout.addLayout(time_info_layout)
        time_layout.addStretch(1)
        
        # Card 3: Permissions Card
        self.perm_card, self.perm_card_title, perm_layout = create_card("dashboard.permissions")
        perm_info_layout = QHBoxLayout()
        perm_info_layout.setSpacing(12)
        
        self.perm_icon = QLabel("🔑")
        self.perm_icon.setStyleSheet("font-size: 24px;")
        
        perm_text_layout = QVBoxLayout()
        self.perm_val = QLabel("Authorized")
        self.perm_val.setStyleSheet("font-size: 16px; font-weight: bold; color: #0f172a;")
        self.perm_desc = QLabel("Verified Session")
        self.perm_desc.setStyleSheet("font-size: 12px; color: #64748b;")
        
        perm_text_layout.addWidget(self.perm_val)
        perm_text_layout.addWidget(self.perm_desc)
        
        perm_info_layout.addWidget(self.perm_icon)
        perm_info_layout.addLayout(perm_text_layout, 1)
        perm_layout.addLayout(perm_info_layout)
        perm_layout.addStretch(1)
        
        grid_layout.addWidget(self.user_card, 0, 0)
        grid_layout.addWidget(self.time_card, 0, 1)
        grid_layout.addWidget(self.perm_card, 0, 2)
        
        container_layout.addLayout(grid_layout)
        
        # Dynamic responsive layout adjustments for grid spacing on resizing
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)
        grid_layout.setColumnStretch(2, 1)
        
        # Informational Banner
        self.tip_frame = QFrame()
        self.tip_frame.setObjectName("TipFrame")
        self.tip_frame.setStyleSheet("""
            QFrame#TipFrame {
                background-color: #eff6ff;
                border: 1px solid #bfdbfe;
                border-radius: 12px;
                padding: 16px;
            }
        """)
        tip_layout = QVBoxLayout(self.tip_frame)
        self.tip_title = QLabel()
        self.tip_title.setProperty("titleKey", "dashboard.tip_title")
        self.tip_title.setStyleSheet("font-weight: bold; color: #1e40af; font-size: 13px;")
        self.tip_desc = QLabel()
        self.tip_desc.setProperty("titleKey", "dashboard.tip_desc")
        self.tip_desc.setWordWrap(True)
        self.tip_desc.setStyleSheet("color: #1e3a8a; font-size: 12px;")
        tip_layout.addWidget(self.tip_title)
        tip_layout.addWidget(self.tip_desc)
        
        container_layout.addWidget(self.tip_frame)
        container_layout.addStretch(1)
        
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
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
        create_order = QPushButton()
        create_order.setProperty("textKey", "purchase.create_order")
        create_order.clicked.connect(self.create_purchase_order_dialog)
        create_invoice = QPushButton()
        create_invoice.setProperty("textKey", "purchase.create_invoice")
        create_invoice.clicked.connect(self.create_purchase_invoice_dialog)
        create_return = QPushButton()
        create_return.setProperty("textKey", "purchase.create_return")
        create_return.clicked.connect(self.create_supplier_return_dialog)
        create_payment = QPushButton()
        create_payment.setProperty("textKey", "purchase.create_payment")
        create_payment.clicked.connect(self.create_supplier_payment_dialog)
        for widget in (refresh, create_order, create_invoice, create_return, create_payment):
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

    def _build_sales_page(self) -> QWidget:
        """Build sales and customer payment page."""

        page, layout, _title = self._page("sales.title")
        action_row = QHBoxLayout()
        refresh = QPushButton()
        refresh.setProperty("textKey", "sales.refresh")
        refresh.clicked.connect(self.refresh_sales)
        create_sale = QPushButton()
        create_sale.setProperty("textKey", "sales.create_sale")
        create_sale.clicked.connect(self.create_sale_dialog)
        create_payment = QPushButton()
        create_payment.setProperty("textKey", "sales.create_payment")
        create_payment.clicked.connect(self.create_customer_payment_dialog)
        create_return = QPushButton()
        create_return.setProperty("textKey", "sales.create_return")
        create_return.clicked.connect(self.create_sale_return_dialog)
        cancel_sale = QPushButton()
        cancel_sale.setProperty("textKey", "sales.cancel")
        cancel_sale.clicked.connect(self.cancel_sale_dialog)
        for widget in (refresh, create_sale, create_return, create_payment, cancel_sale):
            action_row.addWidget(widget)
        action_row.addStretch(1)
        self.sales_table = QTableWidget(0, len(SALES_TABLE_HEADER_KEYS))
        self._set_sales_table_headers()
        self.sales_debt_text = QPlainTextEdit()
        self.sales_debt_text.setReadOnly(True)
        self.sales_debt_text.setMinimumHeight(130)
        layout.addLayout(action_row)
        layout.addWidget(self.sales_table, 1)
        layout.addWidget(self.sales_debt_text)
        return page

    def _build_cashier_page(self) -> QWidget:
        """Build cashier shift controls and cart workflow page."""

        page, layout, _title = self._page("cashier.title")
        action_row = QHBoxLayout()
        refresh = QPushButton()
        refresh.setProperty("textKey", "cashier.refresh")
        refresh.clicked.connect(self.refresh_cashier)
        create_register = QPushButton()
        create_register.setProperty("textKey", "cashier.create_register")
        create_register.clicked.connect(self.create_cash_register_dialog)
        open_shift = QPushButton()
        open_shift.setProperty("textKey", "cashier.open_shift")
        open_shift.clicked.connect(self.open_cash_shift_dialog)
        close_shift = QPushButton()
        close_shift.setProperty("textKey", "cashier.close_shift")
        close_shift.clicked.connect(self.close_cash_shift_dialog)
        cash_operation = QPushButton()
        cash_operation.setProperty("textKey", "cashier.cash_operation")
        cash_operation.clicked.connect(self.cash_operation_dialog)
        for widget in (refresh, create_register, open_shift, close_shift, cash_operation):
            action_row.addWidget(widget)
        action_row.addStretch(1)

        self.cashier_table = QTableWidget(0, len(CASHIER_TABLE_HEADER_KEYS))
        self._set_cashier_table_headers()
        self.cashier_text = QPlainTextEdit()
        self.cashier_text.setReadOnly(True)
        self.cashier_text.setMinimumHeight(110)

        cart_title = QLabel(self.translator.text("cashier.cart.title"))
        cart_title.setProperty("bodyKey", "cashier.cart.title")

        entry_row = QHBoxLayout()
        self.cashier_barcode_input = QLineEdit()
        self.cashier_product_id_input = QLineEdit()
        self.cashier_product_name_input = QLineEdit()
        self.cashier_quantity_input = QLineEdit("1")
        self.cashier_price_input = QLineEdit("0")
        self.cashier_discount_input = QLineEdit("0")
        for widget, key in (
            (self.cashier_barcode_input, "cashier.form.barcode"),
            (self.cashier_product_id_input, "cashier.form.product_id"),
            (self.cashier_product_name_input, "cashier.form.product_name"),
            (self.cashier_quantity_input, "cashier.form.quantity"),
            (self.cashier_price_input, "cashier.form.price"),
            (self.cashier_discount_input, "cashier.form.discount_percent"),
        ):
            widget.setProperty("placeholderKey", key)
            widget.setPlaceholderText(self.translator.text(key))
            entry_row.addWidget(widget)
        pick_product = QPushButton("...")
        pick_product.setFixedWidth(34)
        pick_product.clicked.connect(
            lambda _checked=False: self._select_product_id(
                self.cashier_product_id_input,
                self.cashier_product_name_input,
                self.cashier_price_input,
            )
        )
        entry_row.addWidget(pick_product)
        scan = QPushButton()
        scan.setProperty("textKey", "cashier.cart.scan")
        scan.clicked.connect(self.cashier_scan_barcode)
        add = QPushButton()
        add.setProperty("textKey", "cashier.cart.add")
        add.clicked.connect(self.cashier_add_item_from_inputs)
        update = QPushButton()
        update.setProperty("textKey", "cashier.cart.update")
        update.clicked.connect(self.cashier_update_selected_item)
        remove = QPushButton()
        remove.setProperty("textKey", "cashier.cart.remove")
        remove.clicked.connect(self.cashier_remove_selected_item)
        clear = QPushButton()
        clear.setProperty("textKey", "cashier.cart.clear")
        clear.clicked.connect(self.cashier_clear_cart)
        for button in (scan, add, update, remove, clear):
            entry_row.addWidget(button)

        self.cashier_cart_table = QTableWidget(0, len(CASHIER_CART_HEADER_KEYS))
        self.cashier_cart_table.setMinimumHeight(170)
        self.cashier_cart_table.itemSelectionChanged.connect(self.cashier_load_selected_cart_item)
        self._set_cashier_cart_table_headers()

        payment_row = QHBoxLayout()
        self.cashier_register_id_input = QLineEdit()
        self.cashier_shift_id_input = QLineEdit()
        self.cashier_warehouse_id_input = QLineEdit()
        self.cashier_currency_id_input = QLineEdit()
        self.cashier_customer_id_input = QLineEdit()
        self.cashier_payment_type_combo = QComboBox()
        self.cashier_payment_type_combo.addItems(["cash", "transfer", "mixed", "debt"])
        self.cashier_paid_cash_input = QLineEdit("0")
        self.cashier_paid_transfer_input = QLineEdit("0")
        self.cashier_debt_amount_input = QLineEdit("0")
        self.cashier_closing_amount_input = QLineEdit()
        for widget, key in (
            (self.cashier_register_id_input, "cashier.form.register_id"),
            (self.cashier_shift_id_input, "cashier.form.shift_id"),
            (self.cashier_warehouse_id_input, "cashier.form.warehouse_id"),
            (self.cashier_currency_id_input, "cashier.form.currency_id"),
            (self.cashier_customer_id_input, "cashier.form.customer_id"),
            (self.cashier_paid_cash_input, "cashier.form.paid_cash"),
            (self.cashier_paid_transfer_input, "cashier.form.paid_transfer"),
            (self.cashier_debt_amount_input, "cashier.form.debt_amount"),
            (self.cashier_closing_amount_input, "cashier.form.closing_amount"),
        ):
            widget.setProperty("placeholderKey", key)
            widget.setPlaceholderText(self.translator.text(key))
            payment_row.addWidget(widget)
        payment_row.addWidget(self.cashier_payment_type_combo)
        for target, selector in (
            (self.cashier_register_id_input, self._select_cash_register_id),
            (self.cashier_shift_id_input, self._select_cash_shift_id),
            (self.cashier_warehouse_id_input, self._select_warehouse_id),
            (self.cashier_currency_id_input, self._select_currency_id),
            (self.cashier_customer_id_input, self._select_counterparty_id),
        ):
            picker = QPushButton("...")
            picker.setFixedWidth(34)
            picker.clicked.connect(lambda _checked=False, field=target, pick=selector: pick(field))
            payment_row.addWidget(picker)
        checkout = QPushButton()
        checkout.setObjectName("PrimaryButton")
        checkout.setProperty("textKey", "cashier.cart.checkout")
        checkout.clicked.connect(self.cashier_checkout)
        print_receipt = QPushButton()
        print_receipt.setProperty("textKey", "cashier.cart.print")
        print_receipt.clicked.connect(self.cashier_print_receipt)
        x_report = QPushButton()
        x_report.setProperty("textKey", "cashier.cart.x_report")
        x_report.clicked.connect(self.cashier_x_report)
        z_report = QPushButton()
        z_report.setProperty("textKey", "cashier.cart.z_report")
        z_report.clicked.connect(self.cashier_z_report)
        for button in (checkout, print_receipt, x_report, z_report):
            payment_row.addWidget(button)

        self.cashier_total_label = QLabel()
        receipt_label = QLabel(self.translator.text("cashier.cart.receipt"))
        receipt_label.setProperty("bodyKey", "cashier.cart.receipt")
        self.cashier_receipt_preview = QPlainTextEdit()
        self.cashier_receipt_preview.setReadOnly(True)
        self.cashier_receipt_preview.setMinimumHeight(130)

        layout.addLayout(action_row)
        layout.addWidget(self.cashier_table, 1)
        layout.addWidget(self.cashier_text)
        layout.addWidget(cart_title)
        layout.addLayout(entry_row)
        layout.addWidget(self.cashier_cart_table)
        layout.addWidget(self.cashier_total_label)
        layout.addLayout(payment_row)
        layout.addWidget(receipt_label)
        layout.addWidget(self.cashier_receipt_preview)
        self._refresh_cashier_cart_table()
        return page

    def _build_reports_page(self) -> QWidget:
        """Build reports summary page."""

        page, layout, _title = self._page("reports.title")
        self.report_code = QComboBox()
        for code in ("dashboard", "stock", "sales", "purchases", "debts", "cash-flow", "profit-loss"):
            self.report_code.addItem(code, code)
        self.report_date_from = QLineEdit()
        self.report_date_to = QLineEdit()
        self.report_warehouse_id = QLineEdit()
        self.report_counterparty_id = QLineEdit()
        self.report_product_id = QLineEdit()
        self.report_cash_register_id = QLineEdit()
        self.report_cash_shift_id = QLineEdit()
        self.report_filter_name = QLineEdit()
        for key, widget in (
            ("reports.date_from", self.report_date_from),
            ("reports.date_to", self.report_date_to),
            ("reports.warehouse_id", self.report_warehouse_id),
            ("reports.counterparty_id", self.report_counterparty_id),
            ("reports.product_id", self.report_product_id),
            ("reports.cash_register_id", self.report_cash_register_id),
            ("reports.cash_shift_id", self.report_cash_shift_id),
            ("reports.filter_name", self.report_filter_name),
        ):
            widget.setProperty("placeholderKey", key)
        self.report_debt_type = QComboBox()
        self.report_debt_type.addItem("", None)
        self.report_debt_type.addItem("receivable", "receivable")
        self.report_debt_type.addItem("payable", "payable")

        filters = QFormLayout()
        filters.addRow(self.translator.text("reports.report_code"), self.report_code)
        filters.addRow(self.translator.text("reports.date_from"), self.report_date_from)
        filters.addRow(self.translator.text("reports.date_to"), self.report_date_to)
        self._add_selector_row(filters, "reports.warehouse_id", self.report_warehouse_id, self._select_warehouse_id)
        self._add_selector_row(filters, "reports.counterparty_id", self.report_counterparty_id, self._select_counterparty_id)
        self._add_selector_row(filters, "reports.product_id", self.report_product_id, self._select_product_id)
        self._add_selector_row(filters, "reports.cash_register_id", self.report_cash_register_id, self._select_cash_register_id)
        self._add_selector_row(filters, "reports.cash_shift_id", self.report_cash_shift_id, self._select_cash_shift_id)
        filters.addRow(self.translator.text("reports.debt_type"), self.report_debt_type)
        filters.addRow(self.translator.text("reports.filter_name"), self.report_filter_name)

        actions = QHBoxLayout()
        refresh = QPushButton()
        refresh.setProperty("textKey", "reports.refresh")
        refresh.clicked.connect(self.refresh_reports)
        export = QPushButton()
        export.setProperty("textKey", "reports.export")
        export.clicked.connect(self.export_current_report)
        save_filter = QPushButton()
        save_filter.setProperty("textKey", "reports.save_filter")
        save_filter.clicked.connect(self.save_current_report_filter)
        for button in (refresh, export, save_filter):
            actions.addWidget(button)
        actions.addStretch(1)

        self.reports_text = QPlainTextEdit()
        self.reports_text.setReadOnly(True)
        layout.addLayout(filters)
        layout.addLayout(actions)
        layout.addWidget(self.reports_text, 1)
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

        def action() -> None:
            try:
                data = self.api_client.get_status()
                self._update_dashboard_ui(data)
            except (ApiClientError, ValueError, json.JSONDecodeError) as exc:
                self._set_dashboard_offline(str(exc))
                raise exc

        self._run_api(action)

    def _update_dashboard_ui(self, data: dict[str, Any]) -> None:
        """Populate modern UI cards with active server data."""

        app_name = data.get("application") or "ERP Accounting Server"
        status = data.get("status") or "running"
        server_time_raw = data.get("server_time") or ""
        current_user_id = data.get("current_user_id") or ""
        current_username = data.get("current_username") or ""

        # Update application banner status
        self.banner_app_name.setText(app_name)
        
        lang = self.translator.language
        if status.lower() == "running":
            status_text = "РАБОТАЕТ" if lang == "ru" else "DEŇIZ" if lang == "tk" else "RUNNING"
            self.banner_status_badge.setText(status_text)
            self.banner_status_badge.setStyleSheet("""
                background-color: #dcfce7;
                color: #15803d;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 6px;
            """)
        else:
            status_text = str(status).upper()
            self.banner_status_badge.setText(status_text)
            self.banner_status_badge.setStyleSheet("""
                background-color: #fef3c7;
                color: #d97706;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 6px;
            """)

        # User details card
        user_name_text = str(current_username) if current_username else "Unknown User"
        self.user_name_val.setText(user_name_text)
        self.user_id_val.setText(f"ID: {current_user_id}" if current_user_id != "" else "ID: -")
        
        avatar_letter = user_name_text[0].upper() if user_name_text else "U"
        self.user_avatar.setText(avatar_letter)
        colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"]
        color_index = sum(ord(c) for c in user_name_text) % len(colors)
        self.user_avatar.setStyleSheet(f"""
            background-color: {colors[color_index]};
            color: #ffffff;
            font-size: 20px;
            font-weight: bold;
            border-radius: 20px;
            min-width: 40px;
            max-width: 40px;
            min-height: 40px;
            max-height: 40px;
            text-align: center;
        """)

        # Server time parsing and formatting
        formatted_time = "--:--:--"
        formatted_date = "----- -- --"
        if server_time_raw:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(server_time_raw)
                formatted_time = dt.strftime("%H:%M:%S")
                formatted_date = dt.strftime("%Y-%m-%d")
                tz_offset = dt.strftime("UTC%z")
                if len(tz_offset) == 8:
                    formatted_date += f" ({tz_offset[0:6]}:{tz_offset[6:8]})"
            except Exception:
                try:
                    parts = server_time_raw.split("T")
                    if len(parts) == 2:
                        formatted_date = parts[0]
                        formatted_time = parts[1].split(".")[0]
                except Exception:
                    formatted_time = str(server_time_raw)

        self.time_val.setText(formatted_time)
        self.date_val.setText(formatted_date)

        # Authorization card
        self.perm_val.setText("AUTHORIZED" if lang == "en" else "АВТОРИЗОВАН" if lang == "ru" else "YGTYYARLY")
        self.perm_desc.setText("Session Token Valid" if lang == "en" else "Токен сессии действителен" if lang == "ru" else "Sessiýa tokeni dogry")

    def _set_dashboard_offline(self, error_msg: str) -> None:
        """Adjust dashboard to represent offline/error state."""

        lang = self.translator.language
        offline_text = "ОФФЛАЙН" if lang == "ru" else "OFLAYN" if lang == "tk" else "OFFLINE"
        self.banner_status_badge.setText(offline_text)
        self.banner_status_badge.setStyleSheet("""
            background-color: #fee2e2;
            color: #dc2626;
            font-size: 11px;
            font-weight: bold;
            padding: 4px 8px;
            border-radius: 6px;
        """)
        self.time_val.setText("--:--:--")
        self.date_val.setText("----- -- --")
        self.user_name_val.setText("-")
        self.user_id_val.setText("ID: -")
        
        self.user_avatar.setText("?")
        self.user_avatar.setStyleSheet("""
            background-color: #94a3b8;
            color: #ffffff;
            font-size: 20px;
            font-weight: bold;
            border-radius: 20px;
            min-width: 40px;
            max-width: 40px;
            min-height: 40px;
            max-height: 40px;
        """)
        
        self.perm_val.setText("OFFLINE" if lang == "en" else "ОФФЛАЙН" if lang == "ru" else "OFLAYN")
        self.perm_desc.setText(error_msg)

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
        elif page_id == "sales":
            self.refresh_sales()
        elif page_id == "cashier":
            self.refresh_cashier()
        elif page_id == "reports":
            self.refresh_reports()

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

    def refresh_sales(self) -> None:
        """Refresh sales and receivable ledger."""

        def action() -> None:
            rows = self.api_client.get_sales()
            self.sales_table.setRowCount(len(rows))
            for row, sale in enumerate(rows):
                values = [
                    sale.get("id"),
                    sale.get("doc_number"),
                    sale.get("sale_type"),
                    sale.get("counterparty_name"),
                    sale.get("total_amount_tmt"),
                    sale.get("status"),
                    sale.get("payment_type"),
                ]
                for col, value in enumerate(values):
                    self.sales_table.setItem(row, col, QTableWidgetItem(str(value)))
            ledger = self.api_client.get_debt_ledger(debt_type="receivable")
            self.sales_debt_text.setPlainText(json.dumps(ledger, indent=2, ensure_ascii=False))

        self._run_api(action)

    def refresh_cashier(self) -> None:
        """Refresh cashier shifts and cash-flow snapshot."""

        def action() -> None:
            rows = self.api_client.get_cash_shifts()
            self.cashier_table.setRowCount(len(rows))
            for row, shift in enumerate(rows):
                values = [
                    shift.get("id"),
                    shift.get("cash_register_name") or shift.get("cash_register_id"),
                    shift.get("opened_at"),
                    shift.get("opening_amount"),
                    shift.get("closing_amount"),
                    shift.get("status"),
                ]
                for col, value in enumerate(values):
                    self.cashier_table.setItem(row, col, QTableWidgetItem(str(value)))
            self.cashier_text.setPlainText(json.dumps(self.api_client.get_cash_flow_report(), indent=2, ensure_ascii=False))

        self._run_api(action)

    def _current_report_filters(self) -> dict[str, str]:
        """Return active report filters from the compact report toolbar."""

        pairs = {
            "date_from": self.report_date_from.text().strip(),
            "date_to": self.report_date_to.text().strip(),
            "warehouse_id": self.report_warehouse_id.text().strip(),
            "counterparty_id": self.report_counterparty_id.text().strip(),
            "product_id": self.report_product_id.text().strip(),
            "cash_register_id": self.report_cash_register_id.text().strip(),
            "cash_shift_id": self.report_cash_shift_id.text().strip(),
        }
        debt_type = self.report_debt_type.currentData()
        if debt_type:
            pairs["debt_type"] = str(debt_type)
        return {key: value for key, value in pairs.items() if value}

    def _selected_report_code(self) -> str:
        """Return selected report code."""

        return str(self.report_code.currentData() or "dashboard")

    def _fetch_selected_report(self, code: str, filters: dict[str, str]) -> object:
        """Fetch one report through the matching API helper."""

        if code == "dashboard":
            return self.api_client.get_dashboard_report(filters)
        if code == "stock":
            return self.api_client.get_stock_report(filters)
        if code == "sales":
            return self.api_client.get_sales_report(filters)
        if code == "purchases":
            return self.api_client.get_purchases_report(filters)
        if code == "debts":
            return self.api_client.get_debts_report(filters)
        if code == "cash-flow":
            return self.api_client.get_cash_flow_report(filters)
        return self.api_client.get_profit_loss_report(filters)

    def refresh_reports(self) -> None:
        """Refresh the selected filtered report."""

        def action() -> None:
            code = self._selected_report_code()
            filters = self._current_report_filters()
            report = self._fetch_selected_report(code, filters)
            saved_filters = self.api_client.get_report_filters(code)
            self.reports_text.setPlainText(
                json.dumps(
                    {"report_code": code, "filters": filters, "saved_filters": saved_filters, "report": report},
                    indent=2,
                    ensure_ascii=False,
                )
            )

        self._run_api(action)

    def export_current_report(self) -> None:
        """Export the selected report and show the export payload metadata."""

        def action() -> None:
            code = self._selected_report_code()
            payload = self.api_client.export_report(code, self._current_report_filters())
            self.reports_text.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))

        self._run_api(action)

    def save_current_report_filter(self) -> None:
        """Save the current report filters as a server-side preset."""

        name = self.report_filter_name.text().strip()
        if not name:
            QMessageBox.warning(self, self.translator.text("common.error"), self.translator.text("reports.filter_name"))
            return

        def action() -> None:
            payload = self.api_client.create_report_filter(
                {
                    "report_code": self._selected_report_code(),
                    "name": name,
                    "filters": self._current_report_filters(),
                    "is_shared": False,
                }
            )
            self.reports_text.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))

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
        self._add_selector_row(form, "pricing.form.currency_id", currency_id, self._select_currency_id)
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
        self._add_selector_row(form, "pricing.form.price_list_id", price_list_id, self._select_price_list_id)
        self._add_selector_row(form, "pricing.form.product_id", product_id, lambda field: self._select_product_id(field, price_target=product_price))
        for key, widget in (
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

    def create_purchase_order_dialog(self) -> None:
        """Create a one-line purchase order."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("purchase.create_order"))
        form = QFormLayout(dialog)
        supplier_id = QLineEdit()
        warehouse_id = QLineEdit()
        currency_id = QLineEdit()
        product_id = QLineEdit()
        quantity = QLineEdit("1")
        purchase_price = QLineEdit("0")
        self._add_selector_row(form, "purchase.form.supplier_id", supplier_id, self._select_counterparty_id)
        self._add_selector_row(form, "purchase.form.warehouse_id", warehouse_id, self._select_warehouse_id)
        self._add_selector_row(form, "purchase.form.currency_id", currency_id, self._select_currency_id)
        self._add_selector_row(form, "purchase.form.product_id", product_id, lambda field: self._select_product_id(field, price_target=purchase_price))
        for key, widget in (
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
            self.api_client.create_purchase_order(
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
            self.refresh_purchase()

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
        self._add_selector_row(form, "purchase.form.supplier_id", supplier_id, self._select_counterparty_id)
        self._add_selector_row(form, "purchase.form.warehouse_id", warehouse_id, self._select_warehouse_id)
        self._add_selector_row(form, "purchase.form.currency_id", currency_id, self._select_currency_id)
        self._add_selector_row(form, "purchase.form.product_id", product_id, lambda field: self._select_product_id(field, price_target=purchase_price))
        for key, widget in (
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

    def create_supplier_return_dialog(self) -> None:
        """Create and post a one-line supplier return invoice."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("purchase.create_return"))
        form = QFormLayout(dialog)
        supplier_id = QLineEdit()
        warehouse_id = QLineEdit()
        currency_id = QLineEdit()
        source_invoice_id = QLineEdit()
        order_id = QLineEdit()
        order_line_id = QLineEdit()
        product_id = QLineEdit()
        quantity = QLineEdit("1")
        purchase_price = QLineEdit("0")
        self._add_selector_row(form, "purchase.form.supplier_id", supplier_id, self._select_counterparty_id)
        self._add_selector_row(form, "purchase.form.warehouse_id", warehouse_id, self._select_warehouse_id)
        self._add_selector_row(form, "purchase.form.currency_id", currency_id, self._select_currency_id)
        self._add_selector_row(form, "purchase.form.return_invoice_id", source_invoice_id, self._select_purchase_invoice_id)
        self._add_selector_row(form, "purchase.form.order_id", order_id, self._select_purchase_order_id)
        self._add_selector_row(form, "purchase.form.order_line_id", order_line_id, lambda field: self._select_purchase_order_line_id(field, order_id))
        self._add_selector_row(form, "purchase.form.product_id", product_id, lambda field: self._select_product_id(field, price_target=purchase_price))
        for key, widget in (
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

        def optional_int(widget: QLineEdit) -> int | None:
            text = widget.text().strip()
            return int(text) if text else None

        def action() -> None:
            line: dict[str, object] = {
                "product_id": int(product_id.text().strip()),
                "quantity": quantity.text().strip() or "1",
                "price_cur": purchase_price.text().strip() or "0",
            }
            order_line = optional_int(order_line_id)
            if order_line is not None:
                line["purchase_order_line_id"] = order_line
            payload: dict[str, object] = {
                "counterparty_id": int(supplier_id.text().strip()),
                "warehouse_id": int(warehouse_id.text().strip()),
                "currency_id": int(currency_id.text().strip() or self._default_currency_id()),
                "currency_rate": "1",
                "return_invoice_id": int(source_invoice_id.text().strip()),
                "lines": [line],
            }
            linked_order = optional_int(order_id)
            if linked_order is not None:
                payload["purchase_order_id"] = linked_order
            invoice = self.api_client.create_purchase_return(payload)
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
        self._add_selector_row(form, "purchase.form.supplier_id", supplier_id, self._select_counterparty_id)
        self._add_selector_row(form, "purchase.form.invoice_id", invoice_id, self._select_purchase_invoice_id)
        form.addRow(self.translator.text("purchase.form.payment_amount"), amount)
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

    def create_sale_dialog(self) -> None:
        """Create and post a one-line sale."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("sales.create_sale"))
        form = QFormLayout(dialog)
        cash_register_id = QLineEdit()
        cash_shift_id = QLineEdit()
        customer_id = QLineEdit()
        warehouse_id = QLineEdit()
        currency_id = QLineEdit()
        product_id = QLineEdit()
        quantity = QLineEdit("1")
        sale_price = QLineEdit("0")
        payment_type = QLineEdit("cash")
        paid_cash = QLineEdit("0")
        paid_transfer = QLineEdit("0")
        debt_amount = QLineEdit("0")
        self._add_selector_row(form, "sales.form.cash_register_id", cash_register_id, self._select_cash_register_id)
        self._add_selector_row(form, "sales.form.cash_shift_id", cash_shift_id, self._select_cash_shift_id)
        self._add_selector_row(form, "sales.form.customer_id", customer_id, self._select_counterparty_id)
        self._add_selector_row(form, "sales.form.warehouse_id", warehouse_id, self._select_warehouse_id)
        self._add_selector_row(form, "sales.form.currency_id", currency_id, self._select_currency_id)
        self._add_selector_row(form, "sales.form.product_id", product_id, lambda field: self._select_product_id(field, price_target=sale_price))
        for key, widget in (
            ("sales.form.quantity", quantity),
            ("sales.form.price", sale_price),
            ("sales.form.payment_type", payment_type),
            ("sales.form.paid_cash", paid_cash),
            ("sales.form.paid_transfer", paid_transfer),
            ("sales.form.debt_amount", debt_amount),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def optional_int(widget: QLineEdit) -> int | None:
            text = widget.text().strip()
            return int(text) if text else None

        def action() -> None:
            sale = self.api_client.create_sale(
                {
                    "sale_type": "retail",
                    "cash_register_id": optional_int(cash_register_id),
                    "cash_shift_id": optional_int(cash_shift_id),
                    "counterparty_id": optional_int(customer_id),
                    "warehouse_id": int(warehouse_id.text().strip()),
                    "currency_id": int(currency_id.text().strip() or self._default_currency_id()),
                    "payment_type": payment_type.text().strip() or "cash",
                    "paid_cash_tmt": paid_cash.text().strip() or "0",
                    "paid_transfer_tmt": paid_transfer.text().strip() or "0",
                    "debt_amount_tmt": debt_amount.text().strip() or "0",
                    "lines": [
                        {
                            "product_id": int(product_id.text().strip()),
                            "quantity": quantity.text().strip() or "1",
                            "price_final": sale_price.text().strip() or "0",
                        }
                    ],
                }
            )
            self.api_client.post_sale(int(sale["id"]))
            self.refresh_sales()

        self._run_api(action)

    def create_sale_return_dialog(self) -> None:
        """Create and post a one-line sale return."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("sales.create_return"))
        form = QFormLayout(dialog)
        sale_id = QLineEdit()
        sale_line_id = QLineEdit()
        cash_register_id = QLineEdit()
        cash_shift_id = QLineEdit()
        quantity = QLineEdit("1")
        refund_method = QLineEdit("debt_correction")
        refund_cash = QLineEdit("0")
        refund_transfer = QLineEdit("0")
        receivable_correction = QLineEdit("0")
        self._add_selector_row(form, "sales.form.sale_id", sale_id, self._select_sale_id)
        self._add_selector_row(form, "sales.form.sale_line_id", sale_line_id, lambda field: self._select_sale_line_id(field, sale_id))
        self._add_selector_row(form, "sales.form.cash_register_id", cash_register_id, self._select_cash_register_id)
        self._add_selector_row(form, "sales.form.cash_shift_id", cash_shift_id, self._select_cash_shift_id)
        for key, widget in (
            ("sales.form.quantity", quantity),
            ("sales.form.refund_method", refund_method),
            ("sales.form.refund_cash", refund_cash),
            ("sales.form.refund_transfer", refund_transfer),
            ("sales.form.receivable_correction", receivable_correction),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def optional_int(widget: QLineEdit) -> int | None:
            text = widget.text().strip()
            return int(text) if text else None

        def action() -> None:
            payload: dict[str, object] = {
                "sale_id": int(sale_id.text().strip()),
                "refund_method": refund_method.text().strip() or "debt_correction",
                "refund_cash_tmt": refund_cash.text().strip() or "0",
                "refund_transfer_tmt": refund_transfer.text().strip() or "0",
                "receivable_correction_tmt": receivable_correction.text().strip() or "0",
                "lines": [
                    {
                        "source_sale_line_id": int(sale_line_id.text().strip()),
                        "quantity": quantity.text().strip() or "1",
                    }
                ],
            }
            register = optional_int(cash_register_id)
            shift = optional_int(cash_shift_id)
            if register is not None:
                payload["cash_register_id"] = register
            if shift is not None:
                payload["cash_shift_id"] = shift
            sale_return = self.api_client.create_sale_return(payload)
            self.api_client.post_sale_return(int(sale_return["id"]))
            self.refresh_sales()
            self.refresh_warehouse()

        self._run_api(action)


    def create_customer_payment_dialog(self) -> None:
        """Create an incoming customer payment."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("sales.create_payment"))
        form = QFormLayout(dialog)
        customer_id = QLineEdit()
        sale_id = QLineEdit()
        shift_id = QLineEdit()
        amount = QLineEdit("0")
        self._add_selector_row(form, "sales.form.customer_id", customer_id, self._select_counterparty_id)
        self._add_selector_row(form, "sales.form.sale_id", sale_id, self._select_sale_id)
        self._add_selector_row(form, "sales.form.cash_shift_id", shift_id, self._select_cash_shift_id)
        form.addRow(self.translator.text("sales.form.paid_cash"), amount)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            sale_text = sale_id.text().strip()
            payload: dict[str, object] = {
                "counterparty_id": int(customer_id.text().strip()),
                "direction": "incoming",
                "payment_method": "cash",
                "amount_tmt": amount.text().strip() or "0",
            }
            shift_text = shift_id.text().strip()
            if shift_text:
                payload["cash_shift_id"] = int(shift_text)
            if sale_text:
                payload["allocations"] = [
                    {
                        "doc_type": "sale",
                        "doc_id": int(sale_text),
                        "allocated_amount": amount.text().strip() or "0",
                    }
                ]
            self.api_client.create_payment(payload)
            self.refresh_sales()

        self._run_api(action)

    def cancel_sale_dialog(self) -> None:
        """Cancel a sale by id."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("sales.cancel"))
        form = QFormLayout(dialog)
        sale_id = QLineEdit()
        self._add_selector_row(form, "sales.form.sale_id", sale_id, self._select_sale_id)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            self.api_client.cancel_sale(int(sale_id.text().strip()))
            self.refresh_sales()

        self._run_api(action)

    def cashier_scan_barcode(self) -> None:
        """Scan or resolve a barcode into the cart entry fields."""

        barcode = self.hardware.scan(self.cashier_barcode_input.text().strip() or None)
        self.cashier_barcode_input.setText(barcode)

        def action() -> None:
            product = self.api_client.find_product_by_barcode(barcode)
            self._cashier_set_product_inputs(product)

        self._run_api(action)

    def cashier_add_item_from_inputs(self) -> None:
        """Add the current product entry to the cashier cart."""

        def action() -> None:
            barcode = self.cashier_barcode_input.text().strip()
            if barcode and not self.cashier_product_id_input.text().strip():
                self._cashier_set_product_inputs(self.api_client.find_product_by_barcode(barcode))
            self.cashier_cart.append(self._cashier_cart_row_from_inputs())
            self._refresh_cashier_cart_table()

        self._run_api(action)

    def cashier_update_selected_item(self) -> None:
        """Update the selected cart row from entry fields."""

        def action() -> None:
            row = self._cashier_selected_row()
            self.cashier_cart[row] = self._cashier_cart_row_from_inputs()
            self._refresh_cashier_cart_table()
            self.cashier_cart_table.selectRow(row)

        self._run_api(action)

    def cashier_remove_selected_item(self) -> None:
        """Remove the selected cart row."""

        try:
            row = self._cashier_selected_row()
        except ValueError:
            return
        del self.cashier_cart[row]
        self._refresh_cashier_cart_table()

    def cashier_clear_cart(self) -> None:
        """Clear all cart rows and receipt preview."""

        self.cashier_cart.clear()
        self.cashier_receipt_preview.clear()
        self._refresh_cashier_cart_table()

    def cashier_load_selected_cart_item(self) -> None:
        """Load the selected cart row into editable fields."""

        row = self.cashier_cart_table.currentRow()
        if row < 0 or row >= len(self.cashier_cart):
            return
        item = self.cashier_cart[row]
        self.cashier_product_id_input.setText(str(item.get("product_id", "")))
        self.cashier_product_name_input.setText(str(item.get("product_name", "")))
        self.cashier_quantity_input.setText(str(item.get("quantity", "1")))
        self.cashier_price_input.setText(str(item.get("price_final", "0")))
        self.cashier_discount_input.setText(str(item.get("discount_percent", "0")))

    def cashier_checkout(self) -> None:
        """Create, post, and preview a cashier sale from the current cart."""

        def action() -> None:
            if not self.cashier_cart:
                raise ValueError("Cashier cart is empty.")
            total = self._cashier_cart_total()
            payment_type = self.cashier_payment_type_combo.currentText() or "cash"
            paid_cash = Decimal("0.00")
            paid_transfer = Decimal("0.00")
            debt_amount = Decimal("0.00")
            if payment_type == "cash":
                paid_cash = total
                self.cashier_paid_cash_input.setText(str(total))
            elif payment_type == "transfer":
                paid_transfer = total
                self.cashier_paid_transfer_input.setText(str(total))
            elif payment_type == "debt":
                debt_amount = total
                self.cashier_debt_amount_input.setText(str(total))
            else:
                paid_cash = self._cashier_decimal_text(self.cashier_paid_cash_input.text())
                paid_transfer = self._cashier_decimal_text(self.cashier_paid_transfer_input.text())
                debt_amount = self._cashier_decimal_text(self.cashier_debt_amount_input.text())
                if (paid_cash + paid_transfer + debt_amount).quantize(Decimal("0.01")) != total:
                    raise ValueError("Mixed payment parts must equal cart total.")
            customer_id = self._cashier_optional_int(self.cashier_customer_id_input)
            if debt_amount > Decimal("0.00") and customer_id is None:
                raise ValueError("Customer ID is required for debt sales.")
            cash_register_id = self._cashier_optional_int(self.cashier_register_id_input)
            cash_shift_id = self._cashier_optional_int(self.cashier_shift_id_input)
            warehouse_id = self._cashier_optional_int(self.cashier_warehouse_id_input)
            if warehouse_id is None:
                raise ValueError("Warehouse ID is required.")
            currency_id = self._cashier_optional_int(self.cashier_currency_id_input) or self._default_currency_id()
            payload: dict[str, object] = {
                "sale_type": "retail",
                "cash_register_id": cash_register_id,
                "cash_shift_id": cash_shift_id,
                "counterparty_id": customer_id,
                "warehouse_id": warehouse_id,
                "currency_id": currency_id,
                "payment_type": payment_type,
                "paid_cash_tmt": str(paid_cash),
                "paid_transfer_tmt": str(paid_transfer),
                "debt_amount_tmt": str(debt_amount),
                "lines": [
                    {
                        "product_id": int(item["product_id"]),
                        "quantity": str(item["quantity"]),
                        "price_final": str(item["price_final"]),
                        "discount_percent": str(item["discount_percent"]),
                    }
                    for item in self.cashier_cart
                ],
            }
            sale = self.api_client.create_sale(payload)
            posted = self.api_client.post_sale(int(sale["id"]))
            receipt_lines = self._cashier_receipt_lines(posted)
            self.cashier_receipt_preview.setPlainText("\n".join(receipt_lines))
            if paid_cash > Decimal("0.00"):
                self.hardware.open_drawer()
            self.hardware.register_operation(total)
            self.cashier_cart.clear()
            self._refresh_cashier_cart_table()
            self.refresh_sales()
            self.refresh_cashier()
            self.refresh_warehouse()

        self._run_api(action)

    def cashier_print_receipt(self) -> None:
        """Send the current receipt preview to the configured printer adapter."""

        lines = [line for line in self.cashier_receipt_preview.toPlainText().splitlines() if line.strip()]
        if not lines:
            lines = self._cashier_receipt_lines(None)
            self.cashier_receipt_preview.setPlainText("\n".join(lines))
        self.cashier_text.appendPlainText(self.hardware.print_receipt(lines))

    def cashier_x_report(self) -> None:
        """Fetch and display the current shift X-report."""

        def action() -> None:
            shift_id = self._cashier_optional_int(self.cashier_shift_id_input)
            if shift_id is None:
                raise ValueError("Shift ID is required.")
            report = self.api_client.get_cash_shift_x_report(shift_id)
            self._show_cashier_report(report)

        self._run_api(action)

    def cashier_z_report(self) -> None:
        """Create and display a shift Z-report."""

        def action() -> None:
            shift_id = self._cashier_optional_int(self.cashier_shift_id_input)
            if shift_id is None:
                raise ValueError("Shift ID is required.")
            payload: dict[str, object] = {}
            closing_amount = self.cashier_closing_amount_input.text().strip()
            if closing_amount:
                payload["closing_amount"] = closing_amount
            report = self.api_client.create_cash_shift_z_report(shift_id, payload)
            self._show_cashier_report(report)
            self.refresh_cashier()

        self._run_api(action)

    def _show_cashier_report(self, report: dict[str, object]) -> None:
        """Render an X/Z report into the cashier text and receipt preview panes."""

        self.cashier_text.setPlainText(json.dumps(report, indent=2, ensure_ascii=False))
        self.cashier_receipt_preview.setPlainText("\n".join(self._cashier_report_lines(report)))

    def _cashier_set_product_inputs(self, product: dict[str, object]) -> None:
        """Populate product entry fields from a catalog payload."""

        self.cashier_product_id_input.setText(str(product.get("id", "")))
        self.cashier_product_name_input.setText(str(product.get("name") or product.get("name_ru") or product.get("sku") or ""))
        self.cashier_price_input.setText(str(product.get("retail_price") or "0"))

    def _cashier_cart_row_from_inputs(self) -> dict[str, object]:
        """Build one cart row from entry fields."""

        product_id = self._cashier_optional_int(self.cashier_product_id_input)
        if product_id is None:
            raise ValueError("Product ID is required.")
        quantity = self._cashier_decimal_text(self.cashier_quantity_input.text(), Decimal("1.0000"))
        price_final = self._cashier_decimal_text(self.cashier_price_input.text())
        discount_percent = self._cashier_decimal_text(self.cashier_discount_input.text())
        if quantity <= Decimal("0.00"):
            raise ValueError("Quantity must be greater than zero.")
        if price_final < Decimal("0.00"):
            raise ValueError("Price cannot be negative.")
        if discount_percent < Decimal("0.00") or discount_percent > Decimal("100.00"):
            raise ValueError("Discount percent must be between 0 and 100.")
        return {
            "product_id": product_id,
            "product_name": self.cashier_product_name_input.text().strip() or f"Product {product_id}",
            "quantity": quantity,
            "price_final": price_final,
            "discount_percent": discount_percent,
        }

    def _cashier_selected_row(self) -> int:
        """Return the selected cart row index."""

        row = self.cashier_cart_table.currentRow()
        if row < 0 or row >= len(self.cashier_cart):
            raise ValueError("Select a cart row first.")
        return row

    def _cashier_optional_int(self, widget: QLineEdit) -> int | None:
        """Parse an optional integer input."""

        text = widget.text().strip()
        return int(text) if text else None

    def _cashier_decimal_text(self, text: str, default: Decimal = Decimal("0.00")) -> Decimal:
        """Parse a decimal input with a default for blank values."""

        value = text.strip()
        return Decimal(value) if value else default

    def _cashier_line_amount(self, item: dict[str, object]) -> Decimal:
        """Return one cart row amount after percentage discount."""

        quantity = Decimal(str(item["quantity"]))
        price_final = Decimal(str(item["price_final"]))
        discount_percent = Decimal(str(item["discount_percent"]))
        amount = quantity * price_final * (Decimal("100.00") - discount_percent) / Decimal("100.00")
        return amount.quantize(Decimal("0.01"))

    def _cashier_cart_total(self) -> Decimal:
        """Return the current cart total."""

        return sum((self._cashier_line_amount(item) for item in self.cashier_cart), Decimal("0.00")).quantize(Decimal("0.01"))

    def _refresh_cashier_cart_table(self) -> None:
        """Refresh cart table rows and total label."""

        self.cashier_cart_table.setRowCount(len(self.cashier_cart))
        for row, item in enumerate(self.cashier_cart):
            values = [
                item.get("product_name"),
                item.get("quantity"),
                item.get("price_final"),
                item.get("discount_percent"),
                self._cashier_line_amount(item),
            ]
            for col, value in enumerate(values):
                self.cashier_cart_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.cashier_total_label.setText(f"{self.translator.text('cashier.cart.total')}: {self._cashier_cart_total()} TMT")

    def _cashier_receipt_lines(self, sale: dict[str, object] | None) -> list[str]:
        """Build receipt-preview lines for a posted sale or current cart."""

        lines = ["ERP Accounting", "Receipt"]
        if sale:
            lines.append(f"Sale: {sale.get('doc_number', sale.get('id', ''))}")
            sale_lines = sale.get("lines", [])
            if isinstance(sale_lines, list):
                for item in sale_lines:
                    if isinstance(item, dict):
                        name = item.get("product_name") or item.get("service_name_ru") or item.get("product_id")
                        lines.append(f"{name} x {item.get('quantity')} = {item.get('amount_tmt')} TMT")
            lines.append(f"Total: {sale.get('total_amount_tmt', '0.00')} TMT")
            lines.append(f"Payment: {sale.get('payment_type', '')}")
            return lines
        for item in self.cashier_cart:
            lines.append(f"{item.get('product_name')} x {item.get('quantity')} = {self._cashier_line_amount(item)} TMT")
        lines.append(f"Total: {self._cashier_cart_total()} TMT")
        return lines

    def _cashier_report_lines(self, report: dict[str, object]) -> list[str]:
        """Build printable X/Z report lines."""

        return [
            "ERP Accounting",
            f"{report.get('report_type', '')} report",
            f"Shift: {report.get('shift_id', '')} ({report.get('shift_status', '')})",
            f"Register: {report.get('cash_register_name') or report.get('cash_register_id', '')}",
            f"Sales cash: {report.get('sale_cash_tmt', '0.00')} TMT",
            f"Incoming cash payments: {report.get('incoming_cash_payments_tmt', '0.00')} TMT",
            f"Collections: {report.get('collections_tmt', '0.00')} TMT",
            f"Expected cash: {report.get('expected_cash_tmt', '0.00')} TMT",
            f"Actual cash: {report.get('actual_cash_tmt') or '-'} TMT",
            f"Variance: {report.get('variance_tmt') or '-'} TMT",
        ]

    def create_cash_register_dialog(self) -> None:
        """Create a cash register."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("cashier.create_register"))
        form = QFormLayout(dialog)
        name = QLineEdit()
        warehouse_id = QLineEdit()
        form.addRow(self.translator.text("cashier.form.register_name"), name)
        self._add_selector_row(form, "cashier.form.warehouse_id", warehouse_id, self._select_warehouse_id)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            self.api_client.create_cash_register({"name": name.text().strip(), "warehouse_id": int(warehouse_id.text().strip())})
            self.refresh_cashier()

        self._run_api(action)

    def open_cash_shift_dialog(self) -> None:
        """Open a cash shift."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("cashier.open_shift"))
        form = QFormLayout(dialog)
        register_id = QLineEdit()
        opening_amount = QLineEdit("0")
        self._add_selector_row(form, "cashier.form.register_id", register_id, self._select_cash_register_id)
        form.addRow(self.translator.text("cashier.form.opening_amount"), opening_amount)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            self.api_client.open_cash_shift(
                {
                    "cash_register_id": int(register_id.text().strip()),
                    "opening_amount": opening_amount.text().strip() or "0",
                }
            )
            self.refresh_cashier()

        self._run_api(action)

    def close_cash_shift_dialog(self) -> None:
        """Close a cash shift."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("cashier.close_shift"))
        form = QFormLayout(dialog)
        shift_id = QLineEdit()
        closing_amount = QLineEdit("0")
        self._add_selector_row(form, "cashier.form.shift_id", shift_id, self._select_cash_shift_id)
        form.addRow(self.translator.text("cashier.form.closing_amount"), closing_amount)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            self.api_client.close_cash_shift(int(shift_id.text().strip()), {"closing_amount": closing_amount.text().strip() or "0"})
            self.refresh_cashier()

        self._run_api(action)

    def cash_operation_dialog(self) -> None:
        """Create a cash collection or transfer."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("cashier.cash_operation"))
        form = QFormLayout(dialog)
        shift_id = QLineEdit()
        register_id = QLineEdit()
        operation_type = QLineEdit("collection")
        amount = QLineEdit("0")
        target_register_id = QLineEdit()
        self._add_selector_row(form, "cashier.form.shift_id", shift_id, self._select_cash_shift_id)
        self._add_selector_row(form, "cashier.form.register_id", register_id, self._select_cash_register_id)
        form.addRow(self.translator.text("cashier.form.operation_type"), operation_type)
        form.addRow(self.translator.text("cashier.form.amount"), amount)
        self._add_selector_row(form, "cashier.form.target_register_id", target_register_id, self._select_cash_register_id)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            payload: dict[str, object] = {
                "cash_shift_id": int(shift_id.text().strip()),
                "cash_register_from_id": int(register_id.text().strip()),
                "operation_type": operation_type.text().strip() or "collection",
                "amount_tmt": amount.text().strip() or "0",
            }
            target_text = target_register_id.text().strip()
            if target_text:
                payload["cash_register_to_id"] = int(target_text)
            self.api_client.create_cash_operation(payload)
            self.refresh_cashier()

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
        self._add_selector_row(form, "warehouse.form.warehouse_id", warehouse_id, self._select_warehouse_id)
        self._add_selector_row(form, "warehouse.form.product_id", product_id, lambda field: self._select_product_id(field, price_target=unit_cost))
        for key, widget in (
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
        self._add_selector_row(form, "warehouse.form.source_warehouse_id", source_warehouse_id, self._select_warehouse_id)
        self._add_selector_row(form, "warehouse.form.target_warehouse_id", target_warehouse_id, self._select_warehouse_id)
        self._add_selector_row(form, "warehouse.form.product_id", product_id, self._select_product_id)
        form.addRow(self.translator.text("warehouse.form.quantity"), quantity)
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
        self._add_selector_row(form, "warehouse.form.warehouse_id", warehouse_id, self._select_warehouse_id)
        self._add_selector_row(form, "warehouse.form.product_id", product_id, self._select_product_id)
        for key, widget in (
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
        self._add_selector_row(form, "users.form.role", role, self._select_role_name)
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

    def _set_sales_table_headers(self) -> None:
        """Apply translated column headers to the sales table."""

        self.sales_table.setHorizontalHeaderLabels([self.translator.text(key) for key in SALES_TABLE_HEADER_KEYS])

    def _set_cashier_table_headers(self) -> None:
        """Apply translated column headers to the cashier table."""

        self.cashier_table.setHorizontalHeaderLabels([self.translator.text(key) for key in CASHIER_TABLE_HEADER_KEYS])

    def _set_cashier_cart_table_headers(self) -> None:
        """Apply translated column headers to the cashier cart table."""

        self.cashier_cart_table.setHorizontalHeaderLabels([self.translator.text(key) for key in CASHIER_CART_HEADER_KEYS])

    def retranslate(self) -> None:
        """Apply active translations to visible labels."""

        self.setWindowTitle(self.translator.text("app.title"))
        self._set_users_table_headers()
        self._set_catalog_table_headers()
        self._set_warehouse_table_headers()
        self._set_counterparties_table_headers()
        self._set_pricing_table_headers()
        self._set_purchase_table_headers()
        self._set_sales_table_headers()
        self._set_cashier_table_headers()
        if hasattr(self, "cashier_cart_table"):
            self._set_cashier_cart_table_headers()
            self._refresh_cashier_cart_table()
        if hasattr(self, "catalog_search"):
            self.catalog_search.setPlaceholderText(self.translator.text("catalog.search"))
        if hasattr(self, "counterparty_search"):
            self.counterparty_search.setPlaceholderText(self.translator.text("counterparties.search"))
        for line_edit in self.findChildren(QLineEdit):
            placeholder_key = line_edit.property("placeholderKey")
            if placeholder_key:
                line_edit.setPlaceholderText(self.translator.text(str(placeholder_key)))
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
        """Hide unavailable pages and disable actions blocked by role permissions."""

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

        action_permissions: dict[str, tuple[str, ...]] = {
            "users.create": ("admin.manage_users",),
            "settings.save": ("settings.edit",),
            "catalog.create_group": ("goods.create",),
            "catalog.create_product": ("goods.create",),
            "catalog.create_service": ("goods.create",),
            "warehouse.create_warehouse": ("warehouse.create",),
            "warehouse.opening_inventory": ("warehouse.inventory_create", "warehouse.inventory_post"),
            "warehouse.transfer": ("warehouse.transfer_create", "warehouse.transfer_send", "warehouse.transfer_receive"),
            "warehouse.writeoff": ("warehouse.writeoff_create", "warehouse.writeoff_post"),
            "counterparties.create": ("counterparty.create",),
            "pricing.create_price_list": ("pricing.price_list_create",),
            "pricing.add_price": ("pricing.price_list_edit",),
            "purchase.create_order": ("purchase.order_create",),
            "purchase.create_invoice": ("purchase.invoice_create", "purchase.post"),
            "purchase.create_return": ("purchase.return", "purchase.post"),
            "purchase.create_payment": ("counterparty.payment_create",),
            "sales.create_sale": ("sale.create", "sale.post"),
            "sales.create_payment": ("counterparty.payment_create",),
            "sales.create_return": ("sale_return.create", "sale_return.post"),
            "sales.cancel": ("sale.cancel",),
            "cashier.create_register": ("cashier.register_manage",),
            "cashier.open_shift": ("cashier.shift_open",),
            "cashier.close_shift": ("cashier.shift_close",),
            "cashier.cash_operation": ("cashier.cash_operation",),
            "cashier.cart.checkout": ("sale.create", "sale.post"),
            "cashier.cart.print": ("cashier.print",),
            "cashier.cart.z_report": ("cashier.shift_close",),
            "reports.export": ("reports.export",),
            "reports.save_filter": ("reports.filters_manage",),
        }
        for button in self.findChildren(QPushButton):
            text_key = button.property("textKey")
            required = action_permissions.get(str(text_key)) if text_key else None
            if not required:
                continue
            allowed = all(permission in permissions for permission in required)
            button.setEnabled(allowed)
            button.setToolTip("" if allowed else self.translator.text("common.permission_required"))

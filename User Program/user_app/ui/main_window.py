"""Main endpoint-client shell."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from typing import Any, Callable, Sequence

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QResizeEvent, QFontMetrics
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
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
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QHeaderView,
    QLayout,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
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

ApiRow = dict[str, Any]
TableColumn = tuple[str | Callable[[ApiRow], object], str]
Metric = tuple[str, object]
SelectorColumn = tuple[str, str]


class MainWindow(QWidget):
    """Role-aware main shell for the endpoint client."""

    logout_requested = pyqtSignal()
    language_changed = pyqtSignal(str)

    def __init__(self, api_client: ApiClient, translator: Translator) -> None:
        super().__init__()
        self.api_client = api_client
        self.translator = translator
        self.hardware = HardwareSimulator()
        self.cashier_cart: list[ApiRow] = []
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
                background: #eef3f8;
                color: #152238;
                font-size: 10pt;
            }
            QListWidget#Sidebar {
                background: #ffffff;
                border: 1px solid #d8e1ec;
                border-radius: 12px;
                padding: 8px;
            }
            QListWidget#Sidebar::item {
                border-radius: 8px;
                color: #475569;
                margin: 2px 0;
                padding: 10px 12px;
            }
            QListWidget#Sidebar::item:hover {
                background: #f1f5f9;
                color: #0f172a;
            }
            QListWidget#Sidebar::item:selected {
                background: #e0edff;
                color: #1557c0;
                font-weight: 700;
            }
            QStackedWidget {
                background: transparent;
            }
            QLabel#PageTitle {
                color: #0f172a;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#SectionTitle {
                color: #172033;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#MutedLabel {
                color: #64748b;
                font-size: 9pt;
            }
            QFrame#Card {
                background: #ffffff;
                border: 1px solid #dce5ef;
                border-radius: 10px;
            }
            QFrame#MetricCard {
                background: #ffffff;
                border: 1px solid #dce5ef;
                border-radius: 10px;
            }
            QLabel#MetricTitle {
                color: #64748b;
                font-size: 9pt;
                font-weight: 700;
            }
            QLabel#MetricValue {
                color: #0f172a;
                font-size: 16px;
                font-weight: 800;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                color: #1557c0;
                font-weight: 700;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background: #f8fafc;
                border-color: #94a3b8;
            }
            QPushButton#PrimaryButton {
                background: #1f6feb;
                border-color: #1f6feb;
                color: #ffffff;
            }
            QPushButton#PrimaryButton:hover {
                background: #1557c0;
                border-color: #1557c0;
            }
            QPushButton:disabled {
                background: #f1f5f9;
                border-color: #e2e8f0;
                color: #94a3b8;
            }
            QPlainTextEdit,
            QLineEdit,
            QComboBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px 8px;
            }
            QLineEdit:focus,
            QComboBox:focus {
                border-color: #1f6feb;
            }
            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #dce5ef;
                border-radius: 10px;
                gridline-color: #e7edf4;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }
            QHeaderView::section {
                background: #f8fafc;
                border: 0;
                border-bottom: 1px solid #dce5ef;
                color: #475569;
                font-weight: 700;
                padding: 8px;
            }
            QScrollArea {
                background: transparent;
                border: 0;
            }
            QScrollBar:vertical {
                background: #eef3f8;
                border: 0;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                border-radius: 5px;
                min-height: 28px;
            }
            QFrame#UsersToolbar,
            QFrame#UsersStatCard,
            QFrame#UsersStatCardTotal,
            QFrame#UsersStatCardActive,
            QFrame#UsersStatCardInactive,
            QFrame#UsersProfileCard,
            QFrame#UsersDetailsCard,
            QFrame#UsersFormCard,
            QFrame#UsersEmptyState {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            QFrame#UsersToolbar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f8fafc);
            }
            QFrame#UsersStatCardTotal {
                border-left: 4px solid #3b82f6;
            }
            QFrame#UsersStatCardActive {
                border-left: 4px solid #22c55e;
            }
            QFrame#UsersStatCardInactive {
                border-left: 4px solid #f59e0b;
            }
            QLabel#UsersPageHeading {
                color: #0f172a;
                font-size: 22px;
                font-weight: 800;
                letter-spacing: 0.3px;
            }
            QLabel#UsersSubtitle,
            QLabel#UsersVisibleCount {
                color: #94a3b8;
                font-size: 9pt;
            }
            QLabel#UsersStatTitle,
            QLabel#UsersFieldLabel {
                color: #64748b;
                font-size: 8pt;
                font-weight: 700;
            }
            QLabel#UsersStatValue {
                color: #0f172a;
                font-size: 24px;
                font-weight: 800;
            }
            QLabel#UsersAvatar {
                background: #e0edff;
                border: 1px solid #bfdbfe;
                border-radius: 28px;
                color: #1557c0;
                font-size: 18px;
                font-weight: 800;
                min-height: 56px;
                max-height: 56px;
                min-width: 56px;
                max-width: 56px;
            }
            QLabel#UsersBadgeActive,
            QLabel#UsersBadgeInactive,
            QLabel#UsersRoleBadge {
                border-radius: 10px;
                font-size: 9pt;
                font-weight: 800;
                padding: 4px 12px;
            }
            QLabel#UsersBadgeActive {
                background: #dcfce7;
                color: #166534;
            }
            QLabel#UsersBadgeInactive {
                background: #f1f5f9;
                color: #475569;
            }
            QLabel#UsersRoleBadge {
                background: #fff7ed;
                color: #9a3412;
            }
            QLabel#UsersFormError {
                background: #fef2f2;
                border: 1px solid #fecaca;
                border-radius: 8px;
                color: #991b1b;
                font-weight: 700;
                padding: 8px 10px;
            }
            QPushButton#UsersFilterButton {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                color: #475569;
                font-weight: 600;
                padding: 7px 14px;
            }
            QPushButton#UsersFilterButton:hover {
                background: #f1f5f9;
                border-color: #cbd5e1;
                color: #334155;
            }
            QPushButton#UsersFilterButton:checked {
                background: #dbeafe;
                border-color: #93c5fd;
                color: #1d4ed8;
                font-weight: 600;
            }
            QPushButton#UsersInlineButton,
            QPushButton#UsersInlineDangerButton,
            QToolButton#UsersPasswordToggle {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                color: #1557c0;
                padding: 6px 9px;
            }
            QPushButton#UsersInlineButton:hover,
            QToolButton#UsersPasswordToggle:hover {
                background: #f8fafc;
                border-color: #94a3b8;
            }
            QPushButton#UsersInlineDangerButton {
                color: #b91c1c;
            }
            QTableWidget#UsersTable {
                border-radius: 10px;
                padding-left: 16px;
                padding-right: 16px;
            }
            QTableWidget#UsersTable QScrollBar:vertical {
                width: 0px;
            }
            QTableWidget#UsersTable::item:hover {
                background: #eff6ff;
            }
            QFrame#UsersPaginationBar {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            QPushButton#UsersPaginationButton {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                color: #475569;
                font-weight: 600;
                min-width: 34px;
                min-height: 34px;
                padding: 4px 10px;
            }
            QPushButton#UsersPaginationButton:hover {
                background: #f1f5f9;
                border-color: #cbd5e1;
                color: #1e293b;
            }
            QPushButton#UsersPaginationButton:disabled {
                background: #f8fafc;
                border-color: #f1f5f9;
                color: #cbd5e1;
            }
            QPushButton#UsersPaginationButtonActive {
                background: #1f6feb;
                border: 1px solid #1f6feb;
                border-radius: 6px;
                color: #ffffff;
                font-weight: 700;
                min-width: 34px;
                min-height: 34px;
                padding: 4px 10px;
            }
            QLabel#UsersPaginationInfo {
                color: #64748b;
                font-size: 9pt;
                font-weight: 600;
            }
            QComboBox#UsersPageSizeCombo {
                min-width: 70px;
                padding: 4px 8px;
            }
            QFrame#UsersFormCardModern {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                border-top: 3px solid qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #8b5cf6);
            }
            QFrame#UsersFormCardModernEdit {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                border-top: 3px solid qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #22c55e, stop:1 #14b8a6);
            }
            QLabel#UsersFormAvatarCircle {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #dbeafe, stop:1 #ede9fe);
                border: 2px solid #bfdbfe;
                border-radius: 40px;
                color: #3b82f6;
                font-size: 26px;
                font-weight: 800;
                min-height: 80px;
                max-height: 80px;
                min-width: 80px;
                max-width: 80px;
            }
            QLabel#UsersFormAvatarCircleEdit {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #dcfce7, stop:1 #d1fae5);
                border: 2px solid #86efac;
                border-radius: 40px;
                color: #16a34a;
                font-size: 26px;
                font-weight: 800;
                min-height: 80px;
                max-height: 80px;
                min-width: 80px;
                max-width: 80px;
            }
            QLabel#UsersFormSectionIcon {
                color: #3b82f6;
                font-size: 16px;
                font-weight: 800;
                min-width: 20px;
                max-width: 20px;
            }
            QLabel#UsersFormSectionHeader {
                color: #0f172a;
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QLabel#UsersFormFieldLabel {
                color: #64748b;
                font-size: 9pt;
                font-weight: 700;
                padding-bottom: 2px;
            }
            QFrame#UsersFormSectionCard {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QLineEdit#UsersFormInput {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                color: #0f172a;
                font-size: 10pt;
                padding: 10px 14px;
            }
            QLineEdit#UsersFormInput:focus {
                border-color: #3b82f6;
            }
            QLineEdit#UsersFormInput:read-only {
                background: #f1f5f9;
                color: #94a3b8;
            }
            QComboBox#UsersFormCombo {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                color: #0f172a;
                font-size: 10pt;
                padding: 10px 14px;
            }
            QComboBox#UsersFormCombo:focus {
                border-color: #3b82f6;
            }
            QComboBox#UsersFormCombo::drop-down {
                border: none;
                width: 30px;
            }
            QToolButton#UsersFormPasswordToggle {
                background: transparent;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                color: #64748b;
                font-size: 9pt;
                font-weight: 600;
                padding: 8px 12px;
            }
            QToolButton#UsersFormPasswordToggle:hover {
                background: #f1f5f9;
                border-color: #3b82f6;
                color: #3b82f6;
            }
            QProgressBar {
                background: #e2e8f0;
                border: none;
                border-radius: 3px;
                max-height: 6px;
                min-height: 6px;
            }
            QProgressBar::chunk {
                border-radius: 3px;
            }
            QProgressBar#UsersPasswordStrengthBarWeak::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ef4444, stop:1 #f87171);
            }
            QProgressBar#UsersPasswordStrengthBarMedium::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f59e0b, stop:1 #fbbf24);
            }
            QProgressBar#UsersPasswordStrengthBarGood::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #8b5cf6);
            }
            QProgressBar#UsersPasswordStrengthBarStrong::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #22c55e, stop:1 #4ade80);
            }
            QLabel#UsersPasswordStrengthLabel {
                font-size: 8pt;
                font-weight: 700;
            }
            QLabel#UsersPasswordStrengthLabelWeak {
                color: #ef4444;
                font-size: 8pt;
                font-weight: 700;
            }
            QLabel#UsersPasswordStrengthLabelMedium {
                color: #f59e0b;
                font-size: 8pt;
                font-weight: 700;
            }
            QLabel#UsersPasswordStrengthLabelGood {
                color: #3b82f6;
                font-size: 8pt;
                font-weight: 700;
            }
            QLabel#UsersPasswordStrengthLabelStrong {
                color: #22c55e;
                font-size: 8pt;
                font-weight: 700;
            }
            QCheckBox#UsersFormToggle {
                spacing: 0px;
            }
            QCheckBox#UsersFormToggle::indicator {
                width: 44px;
                height: 24px;
                border-radius: 12px;
                background: #cbd5e1;
                border: 2px solid #94a3b8;
            }
            QCheckBox#UsersFormToggle::indicator:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #8b5cf6);
                border-color: #3b82f6;
            }
            QCheckBox#UsersFormToggle::indicator:hover {
                border-color: #3b82f6;
            }
            QLabel#UsersFormToggleLabel {
                color: #475569;
                font-size: 10pt;
                font-weight: 600;
            }
            QLabel#UsersFormToggleLabelActive {
                color: #16a34a;
                font-size: 10pt;
                font-weight: 700;
            }
            QPushButton#UsersFormBackButton {
                background: transparent;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                color: #475569;
                font-weight: 700;
                padding: 8px 16px;
            }
            QPushButton#UsersFormBackButton:hover {
                background: #f1f5f9;
                border-color: #94a3b8;
                color: #0f172a;
            }
            QPushButton#UsersFormCancelButton {
                background: transparent;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                color: #64748b;
                font-weight: 700;
                padding: 10px 24px;
            }
            QPushButton#UsersFormCancelButton:hover {
                background: #f8fafc;
                border-color: #94a3b8;
                color: #475569;
            }
            QPushButton#UsersFormSaveButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #8b5cf6);
                border: none;
                border-radius: 10px;
                color: #ffffff;
                font-size: 10pt;
                font-weight: 800;
                padding: 10px 32px;
            }
            QPushButton#UsersFormSaveButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563eb, stop:1 #7c3aed);
            }
            QPushButton#UsersFormSaveButton:disabled {
                background: #cbd5e1;
                color: #94a3b8;
            }
            QLabel#UsersFormSubtitle {
                color: #94a3b8;
                font-size: 9pt;
                font-weight: 500;
            }
            
            /* Users View Detail Page Styles */
            QFrame#UsersProfileCardModern {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f8fafc);
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }
            QFrame#UsersDetailsCardModern {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }
            QLabel#UsersDetailAvatar {
                border: 4px solid #ffffff;
                border-radius: 60px;
                color: #ffffff;
                font-size: 32px;
                font-weight: 800;
                min-height: 120px;
                max-height: 120px;
                min-width: 120px;
                max-width: 120px;
            }
            QLabel#UsersDetailAvatar[active="true"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #3b82f6, stop:1 #8b5cf6);
            }
            QLabel#UsersDetailAvatar[active="false"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #475569, stop:1 #64748b);
            }
            QFrame#UsersFieldRow {
                background: transparent;
                border: none;
                border-bottom: 1px solid #f1f5f9;
            }
            QFrame#UsersFieldRow:hover {
                background: #f8fafc;
            }
            QLabel#UsersFieldValue {
                color: #0f172a;
                font-size: 11pt;
                font-weight: 600;
            }
            QPushButton#UsersCopyButton {
                background: #f1f5f9;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                color: #64748b;
                font-size: 8pt;
                font-weight: 600;
                padding: 4px 8px;
                min-width: 70px;
            }
            QPushButton#UsersCopyButton:hover {
                background: #e2e8f0;
                border-color: #cbd5e1;
                color: #0f172a;
            }
            QPushButton#UsersCopyButton[copied="true"] {
                background: #dcfce7;
                border-color: #bbf7d0;
                color: #166534;
            }
            QPushButton#UsersStatusToggleButton[status_active="true"] {
                background: transparent;
                border: 1px solid #fca5a5;
                border-radius: 10px;
                color: #b91c1c;
                font-weight: 700;
                padding: 8px 16px;
            }
            QPushButton#UsersStatusToggleButton[status_active="true"]:hover {
                background: #fef2f2;
                border-color: #ef4444;
                color: #991b1b;
            }
            QPushButton#UsersStatusToggleButton[status_active="false"] {
                background: transparent;
                border: 1px solid #86efac;
                border-radius: 10px;
                color: #15803d;
                font-weight: 700;
                padding: 8px 16px;
            }
            QPushButton#UsersStatusToggleButton[status_active="false"]:hover {
                background: #f0fdf4;
                border-color: #22c55e;
                color: #166534;
            }
            QFrame#RolesToolbar,
            QFrame#RolesStatCardTotal,
            QFrame#RolesStatCardPermissions,
            QFrame#RolesStatCardGranted,
            QFrame#RolesPermissionsDrawer,
            QFrame#RolesEmptyState,
            QFrame#RolesPermissionsEmptyState {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QFrame#RolesToolbar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f8fafc);
            }
            QFrame#RolesStatCardTotal {
                border-left: 4px solid #3b82f6;
            }
            QFrame#RolesStatCardPermissions {
                border-left: 4px solid #8b5cf6;
            }
            QFrame#RolesStatCardGranted {
                border-left: 4px solid #14b8a6;
            }
            QLabel#RolesPageHeading {
                color: #0f172a;
                font-size: 22px;
                font-weight: 800;
                letter-spacing: 0.3px;
            }
            QLabel#RolesDrawerHeading {
                color: #0f172a;
                font-size: 17px;
                font-weight: 800;
            }
            QLabel#RolesSubtitle,
            QLabel#RolesVisibleCount,
            QLabel#RolesDrawerDescription,
            QLabel#RolesPermissionDescription,
            QLabel#RolesEmptyBody {
                color: #64748b;
                font-size: 9pt;
            }
            QLabel#RolesStatTitle {
                color: #64748b;
                font-size: 8pt;
                font-weight: 700;
            }
            QLabel#RolesStatValue {
                color: #0f172a;
                font-size: 24px;
                font-weight: 800;
            }
            QLabel#RolesPermissionCountBadge {
                background: #ccfbf1;
                border-radius: 11px;
                color: #0f766e;
                font-size: 9pt;
                font-weight: 800;
                padding: 5px 10px;
            }
            QFrame#RolesListCard {
                background: transparent;
                border: 0;
            }
            QTableWidget#RolesTable {
                border: 1px solid #dce5ef;
                border-radius: 10px;
                padding-left: 16px;
                padding-right: 16px;
            }
            QTableWidget#RolesTable QScrollBar:vertical {
                width: 0px;
            }
            QTableWidget#RolesTable::item:hover {
                background: #eff6ff;
            }
            QFrame#RolesPaginationBar {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            QPushButton#RolesPaginationButton {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                color: #475569;
                font-weight: 600;
                min-width: 34px;
                min-height: 34px;
                padding: 4px 10px;
            }
            QPushButton#RolesPaginationButton:hover {
                background: #f1f5f9;
                border-color: #cbd5e1;
                color: #1e293b;
            }
            QPushButton#RolesPaginationButton:disabled {
                background: #f8fafc;
                border-color: #f1f5f9;
                color: #cbd5e1;
            }
            QPushButton#RolesPaginationButtonActive {
                background: #1f6feb;
                border: 1px solid #1f6feb;
                border-radius: 6px;
                color: #ffffff;
                font-weight: 700;
                min-width: 34px;
                min-height: 34px;
                padding: 4px 10px;
            }
            QLabel#RolesPaginationInfo {
                color: #64748b;
                font-size: 9pt;
                font-weight: 600;
            }
            QComboBox#RolesPageSizeCombo {
                min-width: 70px;
                padding: 4px 8px;
            }
            QFrame#RolesPermissionsDrawer {
                border-top: 3px solid #14b8a6;
            }
            QPushButton#RolesDrawerClose {
                background: transparent;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                color: #64748b;
                font-size: 15px;
                min-height: 30px;
                min-width: 30px;
                max-height: 30px;
                max-width: 30px;
                padding: 0;
            }
            QPushButton#RolesDrawerClose:hover {
                background: #f1f5f9;
                color: #0f172a;
            }
            QPushButton#RolesBackButton {
                background: transparent;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                color: #475569;
                padding: 7px 12px;
            }
            QFrame#RolesPermissionCard {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            QFrame#RolesPermissionCard:hover {
                background: #f0fdfa;
                border-color: #99f6e4;
            }
            QLabel#RolesPermissionModule {
                background: #ede9fe;
                border-radius: 8px;
                color: #6d28d9;
                font-size: 8pt;
                font-weight: 800;
                padding: 3px 7px;
            }
            QLabel#RolesPermissionCode {
                color: #0f172a;
                font-size: 10pt;
                font-weight: 700;
            }
            QScrollArea#RolesPermissionScroll {
                background: transparent;
                border: 0;
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
        self.nav.setObjectName("Sidebar")
        self.nav.setFixedWidth(238)
        self.nav.setSpacing(2)
        self.stack.setObjectName("ContentStack")
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
        self.language_combo.currentIndexChanged.connect(
            lambda: self.language_changed.emit(str(self.language_combo.currentData()))
        )
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
        layout.setSpacing(14)
        title = QLabel(self.translator.text(title_key))
        title.setObjectName("PageTitle")
        title.setProperty("titleKey", title_key)
        layout.addWidget(title)
        return page, layout, title

    def _make_card(
        self, title: str | None = None, *, title_key: str | None = None
    ) -> tuple[QFrame, QVBoxLayout]:
        """Create one reusable content card."""

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)
        label_text = self.translator.text(title_key) if title_key else title
        if label_text:
            label = QLabel(label_text)
            label.setObjectName("SectionTitle")
            if title_key:
                label.setProperty("titleKey", title_key)
            card_layout.addWidget(label)
        return card, card_layout

    def _metric_area(self) -> tuple[QWidget, QHBoxLayout]:
        """Create a horizontal metric area that can be repopulated."""

        area = QWidget()
        layout = QHBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        return area, layout

    def _ui(self, key: str) -> str:
        """Return a localized label for the refreshed UI."""

        return self.translator.text(f"ui.{key}")

    def _report_code_text(self, code: str) -> str:
        """Return a localized display label for one report code."""

        return self.translator.text(f"report_code.{code}")

    def _debt_type_text(self, code: str | None) -> str:
        """Return a localized display label for one report debt type."""

        return "" if code is None else self.translator.text(f"debt_type.{code}")

    def _clear_layout(self, layout: QLayout) -> None:
        """Remove all child widgets/layouts from a layout."""

        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                continue
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)

    def _configure_table(self, table: QTableWidget) -> None:
        """Apply consistent desktop-table behavior."""

        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setShowGrid(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        vertical_header = table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
            vertical_header.setDefaultSectionSize(34)
        horizontal_header = table.horizontalHeader()
        if horizontal_header is not None:
            horizontal_header.setStretchLastSection(True)
            horizontal_header.setDefaultAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            horizontal_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def _table_item(self, value: object) -> QTableWidgetItem:
        """Return a non-editable table item with formatted text."""

        item = QTableWidgetItem(self._format_value(value))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _populate_table(
        self,
        table: QTableWidget,
        rows: Sequence[ApiRow],
        columns: Sequence[TableColumn],
    ) -> None:
        """Render a list of API dictionaries into a table."""

        table.setSortingEnabled(False)
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels([label for _key, label in columns])
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, (key, _label) in enumerate(columns):
                value = key(row) if callable(key) else row.get(key)
                item = self._table_item(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                table.setItem(row_index, column_index, item)
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)

    def _api_list(
        self, method_name: str, *args: object, **kwargs: object
    ) -> list[ApiRow]:
        """Return an API list when the staged client/server method exists."""

        method = getattr(self.api_client, method_name, None)
        if method is None:
            return []
        rows = method(*args, **kwargs)
        return rows if isinstance(rows, list) else []

    def _selected_table_row(self, table: QTableWidget) -> ApiRow | None:
        """Return the API row attached to the selected table row."""

        selected = table.selectedItems()
        if not selected:
            return None
        row_data = selected[0].data(Qt.ItemDataRole.UserRole)
        return row_data if isinstance(row_data, dict) else None

    def _record_name(self, row: ApiRow) -> str:
        """Return a compact human name for a row."""

        for key in (
            "name",
            "name_ru",
            "username",
            "full_name",
            "doc_number",
            "code",
            "sku",
            "number",
        ):
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        return f"#{row.get('id', '')}"

    def _install_record_actions(
        self,
        table: QTableWidget,
        *,
        view: Callable[[ApiRow], None],
        edit: Callable[[ApiRow], None] | None = None,
        lifecycle: Callable[[ApiRow], None] | None = None,
        lifecycle_label: Callable[[ApiRow], str] | None = None,
        edit_enabled: Callable[[ApiRow], bool] | None = None,
        lifecycle_enabled: Callable[[ApiRow], bool] | None = None,
    ) -> None:
        """Attach a localized right-click menu and double-click view action."""

        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda position, current_table=table: self._show_record_context_menu(
                current_table,
                position,
                view=view,
                edit=edit,
                lifecycle=lifecycle,
                lifecycle_label=lifecycle_label,
                edit_enabled=edit_enabled,
                lifecycle_enabled=lifecycle_enabled,
            )
        )
        table.itemDoubleClicked.connect(
            lambda _item, current_table=table: self._view_selected_record(
                current_table, view
            )
        )

    def _show_record_context_menu(
        self,
        table: QTableWidget,
        position: QPoint,
        *,
        view: Callable[[ApiRow], None],
        edit: Callable[[ApiRow], None] | None,
        lifecycle: Callable[[ApiRow], None] | None,
        lifecycle_label: Callable[[ApiRow], str] | None,
        edit_enabled: Callable[[ApiRow], bool] | None,
        lifecycle_enabled: Callable[[ApiRow], bool] | None,
    ) -> None:
        """Show the context menu for one record table."""

        index = table.indexAt(position)
        if index.isValid():
            table.selectRow(index.row())
        row = self._selected_table_row(table)
        if row is None:
            return
        menu = QMenu(table)
        view_action = menu.addAction(self.translator.text("crud.view"))
        edit_action = (
            menu.addAction(self.translator.text("crud.edit"))
            if edit is not None
            else None
        )
        lifecycle_action = None
        if lifecycle is not None:
            label = (
                lifecycle_label(row)
                if lifecycle_label
                else self.translator.text("crud.deactivate")
            )
            lifecycle_action = menu.addAction(label)
        if edit_action is not None:
            can_edit = edit_enabled(row) if edit_enabled else True
            edit_action.setEnabled(can_edit)
            if not can_edit:
                edit_action.setToolTip(self.translator.text("crud.edit_disabled"))
                edit_action.setStatusTip(self.translator.text("crud.edit_disabled"))
        if lifecycle_action is not None:
            lifecycle_action.setEnabled(
                lifecycle_enabled(row) if lifecycle_enabled else True
            )
        viewport = table.viewport()
        if viewport is None:
            return
        chosen = menu.exec(viewport.mapToGlobal(position))
        if chosen == view_action:
            view(row)
        elif edit_action is not None and chosen == edit_action and edit is not None:
            edit(row)
        elif (
            lifecycle_action is not None
            and chosen == lifecycle_action
            and lifecycle is not None
        ):
            lifecycle(row)

    def _view_selected_record(
        self, table: QTableWidget, view: Callable[[ApiRow], None]
    ) -> None:
        """Open the selected row in the detail dialog."""

        row = self._selected_table_row(table)
        if row is not None:
            view(row)

    def _show_record_details(self, title: str, row: ApiRow) -> None:
        """Show scalar fields and related list data for a record."""

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(720, 520)
        layout = QVBoxLayout(dialog)
        header = QLabel(self._record_name(row))
        header.setObjectName("PageTitle")
        layout.addWidget(header)

        scalar_rows = [
            {"field": self._humanize_key(key), "value": value}
            for key, value in row.items()
            if not isinstance(value, (list, dict, tuple))
        ]
        table = QTableWidget(0, 2)
        self._configure_table(table)
        self._populate_table(
            table,
            scalar_rows,
            [("field", self._ui("field")), ("value", self._ui("value"))],
        )
        layout.addWidget(table, 1)

        for key, value in row.items():
            if isinstance(value, list) and all(
                isinstance(item, dict) for item in value
            ):
                label = QLabel(self._humanize_key(key))
                label.setObjectName("SectionTitle")
                layout.addWidget(label)
                nested_rows = [dict(item) for item in value]
                nested = QTableWidget(0, 1)
                self._configure_table(nested)
                self._populate_table(
                    nested,
                    nested_rows,
                    self._columns_from_rows(nested_rows) or [("id", "ID")],
                )
                layout.addWidget(nested, 1)
            elif isinstance(value, dict):
                label = QLabel(self._humanize_key(key))
                label.setObjectName("SectionTitle")
                layout.addWidget(label)
                nested_rows = [
                    {"field": self._humanize_key(str(child_key)), "value": child_value}
                    for child_key, child_value in value.items()
                ]
                nested = QTableWidget(0, 2)
                self._configure_table(nested)
                self._populate_table(
                    nested,
                    nested_rows,
                    [("field", self._ui("field")), ("value", self._ui("value"))],
                )
                layout.addWidget(nested, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _simple_record_form(
        self,
        title: str,
        fields: list[tuple[str, str, object]],
        *,
        omit_blank: tuple[str, ...] = (),
    ) -> ApiRow | None:
        """Show a simple localized edit form and return parsed values."""

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(520, 360)
        form = QFormLayout(dialog)
        widgets: dict[str, tuple[QLineEdit, object]] = {}
        for key, label, value in fields:
            field = QLineEdit("" if value is None else str(value))
            field.setPlaceholderText(label)
            widgets[key] = (field, value)
            form.addRow(label, field)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        payload: ApiRow = {}
        for key, (field, original) in widgets.items():
            text = field.text().strip()
            if key in omit_blank and not text:
                continue
            payload[key] = self._parse_record_field(text, original, key)
        return payload

    def _parse_record_field(self, text: str, original: object, key: str) -> object:
        """Parse one string from a CRUD form into a practical API value."""

        if (
            isinstance(original, bool)
            or key.startswith("is_")
            or key in {"active", "is_shared"}
        ):
            return text.casefold() in {"1", "true", "yes", "y", "on", "да", "hawa"}
        if key.endswith("_id") or key in {"role_flags", "sort_order"}:
            return int(text) if text else None
        if original is None:
            return text or None
        return text

    def _confirm_record_action(
        self, row: ApiRow, action_label: str, *, hard_delete: bool = False
    ) -> bool:
        """Ask the user to confirm a lifecycle or delete action."""

        name = self._record_name(row)
        if hard_delete:
            message = self.translator.text("crud.confirm_delete").format(name=name)
        else:
            message = self.translator.text("crud.confirm_action").format(
                action=action_label.lower(), name=name
            )
        result = QMessageBox.question(
            self,
            action_label,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def _active_lifecycle_label(self, row: ApiRow) -> str:
        """Return Activate or Deactivate for rows with is_active."""

        return self.translator.text(
            "crud.deactivate" if row.get("is_active") else "crud.activate"
        )

    def _format_value(self, value: object) -> str:
        """Format API values for human-facing widgets."""

        if value is None or value == "":
            return "-"
        if isinstance(value, bool):
            return self._ui("yes") if value else self._ui("no")
        if isinstance(value, list):
            if not value:
                return "-"
            if all(not isinstance(item, (dict, list, tuple)) for item in value):
                return ", ".join(str(item) for item in value)
            return f"{len(value)} {self._ui('items')}"
        if isinstance(value, dict):
            return f"{len(value)} {self._ui('fields')}" if value else "-"
        return str(value)

    def _humanize_key(self, key: str) -> str:
        """Convert snake-case API keys into compact labels."""

        translation_key = f"field.{key}"
        translated = self.translator.text(translation_key)
        if translated != translation_key:
            return translated
        return key.replace("_", " ").replace("-", " ").strip().title() or key

    def _safe_decimal(self, value: object) -> Decimal:
        """Parse a decimal-ish API value for summary cards."""

        try:
            return Decimal(str(value or "0"))
        except Exception:
            return Decimal("0")

    def _sum_rows(self, rows: Sequence[ApiRow], key: str) -> Decimal:
        """Sum one numeric field from API rows."""

        return sum((self._safe_decimal(row.get(key)) for row in rows), Decimal("0"))

    def _render_metric_cards(
        self, layout: QHBoxLayout, metrics: Sequence[Metric]
    ) -> None:
        """Render metric cards into an existing horizontal layout."""

        self._clear_layout(layout)
        if not metrics:
            muted = QLabel(self._ui("no_summary"))
            muted.setObjectName("MutedLabel")
            layout.addWidget(muted)
            layout.addStretch(1)
            return
        for title, value in metrics:
            card = QFrame()
            card.setObjectName("MetricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)
            title_label = QLabel(title)
            title_label.setObjectName("MetricTitle")
            value_label = QLabel(self._format_value(value))
            value_label.setObjectName("MetricValue")
            value_label.setWordWrap(True)
            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            layout.addWidget(card, 1)
        layout.addStretch(1)

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
        rows_provider: Callable[[], list[ApiRow]],
        target: QLineEdit,
        columns: Sequence[SelectorColumn],
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
        dialog = ReferenceSelectorDialog(
            title,
            rows,
            list(columns),
            search_placeholder=self.translator.text("common.search"),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_row()
        if not selected:
            return
        target.setText(str(selected.get(id_field, "") or ""))
        if display_target is not None and display_fields:
            values = [
                str(selected.get(field, "") or "")
                for field in display_fields
                if selected.get(field) not in (None, "")
            ]
            display_target.setText(" - ".join(values))
        if (
            price_target is not None
            and price_field is not None
            and selected.get(price_field) is not None
        ):
            price_target.setText(str(selected.get(price_field)))

    def _select_product_id(
        self,
        target: QLineEdit,
        name_target: QLineEdit | None = None,
        price_target: QLineEdit | None = None,
    ) -> None:
        """Select a product and copy its id to a line edit."""

        self._select_reference(
            self.translator.text("catalog.title"),
            lambda: self.api_client.get_products(),
            target,
            [
                ("id", "ID"),
                ("sku", self._ui("sku")),
                ("name", self._ui("name")),
                ("retail_price", self._ui("price")),
            ],
            display_target=name_target,
            display_fields=("sku", "name"),
            price_target=price_target,
            price_field="retail_price",
        )

    def _select_warehouse_id(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("warehouse.title"),
            lambda: self.api_client.get_warehouses(),
            target,
            [("id", "ID"), ("code", self._ui("code")), ("name", self._ui("name"))],
        )

    def _select_counterparty_id(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("counterparties.title"),
            lambda: self.api_client.get_counterparties(include_debt=True),
            target,
            [
                ("id", "ID"),
                ("code", self._ui("code")),
                ("name", self._ui("name")),
                ("counterparty_type", self._ui("type")),
                ("debt_balance_tmt", self._ui("debt")),
            ],
        )

    def _select_currency_id(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("pricing.form.currency_id"),
            lambda: self.api_client.get_currencies(),
            target,
            [("id", "ID"), ("code", self._ui("code")), ("name", self._ui("name"))],
        )

    def _select_price_list_id(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("pricing.create_price_list"),
            lambda: self.api_client.get_price_lists(),
            target,
            [
                ("id", "ID"),
                ("name_ru", self._ui("name")),
                ("currency_code", self._ui("currency")),
                ("is_default", self._ui("default")),
            ],
        )

    def _select_cash_register_id(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("cashier.create_register"),
            lambda: self.api_client.get_cash_registers(),
            target,
            [
                ("id", "ID"),
                ("name", self._ui("name")),
                ("warehouse_id", self._ui("warehouse")),
                ("is_active", self._ui("active")),
            ],
        )

    def _select_cash_shift_id(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("cashier.form.shift_id"),
            lambda: self.api_client.get_cash_shifts(),
            target,
            [
                ("id", "ID"),
                ("cash_register_name", self._ui("register")),
                ("opened_at", self._ui("opened")),
                ("status", self._ui("status")),
            ],
        )

    def _select_purchase_invoice_id(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("purchase.create_invoice"),
            lambda: self.api_client.get_purchase_invoices(),
            target,
            [
                ("id", "ID"),
                ("doc_number", self._ui("number")),
                ("counterparty_name", self._ui("supplier")),
                ("total_amount_tmt", self._ui("total")),
                ("status", self._ui("status")),
            ],
        )

    def _select_purchase_order_id(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("purchase.create_order"),
            lambda: self.api_client.get_purchase_orders(),
            target,
            [
                ("id", "ID"),
                ("doc_number", self._ui("number")),
                ("counterparty_name", self._ui("supplier")),
                ("total_amount_tmt", self._ui("total")),
                ("status", self._ui("status")),
            ],
        )

    def _select_purchase_order_line_id(
        self, target: QLineEdit, order_id: QLineEdit
    ) -> None:
        """Select a line from the selected purchase order."""

        order_text = order_id.text().strip()
        if not order_text:
            QMessageBox.warning(
                self,
                self.translator.text("common.error"),
                self.translator.text("purchase.form.order_id"),
            )
            return
        try:
            order = next(
                (
                    row
                    for row in self.api_client.get_purchase_orders()
                    if int(row.get("id", 0)) == int(order_text)
                ),
                None,
            )
        except (ApiClientError, ValueError) as exc:
            QMessageBox.critical(self, self.translator.text("common.error"), str(exc))
            return
        if not order:
            QMessageBox.warning(
                self,
                self.translator.text("common.error"),
                self.translator.text("purchase.form.order_id"),
            )
            return
        lines = list(order.get("lines", []))
        self._select_reference(
            self.translator.text("purchase.form.order_line_id"),
            lambda: lines,
            target,
            [
                ("id", "ID"),
                ("product_name", self._ui("product")),
                ("quantity_ordered", self._ui("quantity_short")),
                ("amount_tmt", self._ui("amount")),
            ],
        )

    def _select_sale_id(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("sales.create_sale"),
            lambda: self.api_client.get_sales(),
            target,
            [
                ("id", "ID"),
                ("doc_number", self._ui("number")),
                ("counterparty_name", self._ui("customer")),
                ("total_amount_tmt", self._ui("total")),
                ("status", self._ui("status")),
            ],
        )

    def _select_sale_line_id(self, target: QLineEdit, sale_id: QLineEdit) -> None:
        """Select a line from the selected sale document."""

        sale_text = sale_id.text().strip()
        if not sale_text:
            QMessageBox.warning(
                self,
                self.translator.text("common.error"),
                self.translator.text("sales.form.sale_id"),
            )
            return
        try:
            sale = next(
                (
                    row
                    for row in self.api_client.get_sales()
                    if int(row.get("id", 0)) == int(sale_text)
                ),
                None,
            )
        except (ApiClientError, ValueError) as exc:
            QMessageBox.critical(self, self.translator.text("common.error"), str(exc))
            return
        if not sale:
            QMessageBox.warning(
                self,
                self.translator.text("common.error"),
                self.translator.text("sales.form.sale_id"),
            )
            return
        lines = list(sale.get("lines", []))
        self._select_reference(
            self.translator.text("sales.form.sale_line_id"),
            lambda: lines,
            target,
            [
                ("id", "ID"),
                ("product_name", self._ui("product")),
                ("quantity", self._ui("quantity_short")),
                ("amount_tmt", self._ui("amount")),
            ],
        )

    def _select_role_name(self, target: QLineEdit) -> None:
        self._select_reference(
            self.translator.text("roles.title"),
            lambda: self.api_client.get_roles(),
            target,
            [("name", self._ui("role")), ("description", self._ui("description"))],
            id_field="name",
        )

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
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        self.banner_app_name.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #0f172a;"
        )

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
            card_title.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #64748b; text-transform: uppercase;"
            )
            card_layout.addWidget(card_title)

            return card, card_title, card_layout

        # Card 1: User Card
        self.user_card, self.user_card_title, user_layout = create_card(
            "dashboard.current_user"
        )
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
        self.user_name_val.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #0f172a;"
        )
        self.user_id_val = QLabel("ID: -")
        self.user_id_val.setStyleSheet("font-size: 12px; color: #64748b;")

        user_text_layout.addWidget(self.user_name_val)
        user_text_layout.addWidget(self.user_id_val)

        user_info_layout.addWidget(self.user_avatar)
        user_info_layout.addLayout(user_text_layout, 1)
        user_layout.addLayout(user_info_layout)
        user_layout.addStretch(1)

        # Card 2: Server Time Card
        self.time_card, self.time_card_title, time_layout = create_card(
            "dashboard.server_time"
        )
        time_info_layout = QHBoxLayout()
        time_info_layout.setSpacing(12)

        self.time_icon = QLabel("🕒")
        self.time_icon.setStyleSheet("font-size: 24px;")

        time_text_layout = QVBoxLayout()
        self.time_val = QLabel("--:--:--")
        self.time_val.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #0f172a;"
        )
        self.date_val = QLabel("----- -- --")
        self.date_val.setStyleSheet("font-size: 12px; color: #64748b;")

        time_text_layout.addWidget(self.time_val)
        time_text_layout.addWidget(self.date_val)

        time_info_layout.addWidget(self.time_icon)
        time_info_layout.addLayout(time_text_layout, 1)
        time_layout.addLayout(time_info_layout)
        time_layout.addStretch(1)

        # Card 3: Permissions Card
        self.perm_card, self.perm_card_title, perm_layout = create_card(
            "dashboard.permissions"
        )
        perm_info_layout = QHBoxLayout()
        perm_info_layout.setSpacing(12)

        self.perm_icon = QLabel("🔑")
        self.perm_icon.setStyleSheet("font-size: 24px;")

        perm_text_layout = QVBoxLayout()
        self.perm_val = QLabel("Authorized")
        self.perm_val.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #0f172a;"
        )
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
        self.tip_title.setStyleSheet(
            "font-weight: bold; color: #1e40af; font-size: 13px;"
        )
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

    def _build_roles_page(self) -> QWidget:
        """Build the responsive Roles and Permissions list workflow."""

        page, layout, _title = self._page("roles.title")
        _title.hide()

        self.roles_rows: list[ApiRow] = []
        self.roles_filtered_rows: list[ApiRow] = []
        self.roles_permission_catalog: dict[str, ApiRow] = {}
        self.roles_selected_role_id: object | None = None
        self.roles_current_page = 0
        self.roles_page_size = 10
        self.roles_narrow_mode = False
        self.roles_drawer_animation: QPropertyAnimation | None = None

        toolbar = QFrame()
        toolbar.setObjectName("RolesToolbar")
        toolbar_layout = QGridLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 14, 16, 14)
        toolbar_layout.setHorizontalSpacing(12)
        toolbar_layout.setVerticalSpacing(12)

        title_box = QWidget()
        title_layout = QVBoxLayout(title_box)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(3)
        title = QLabel(self.translator.text("roles.title"))
        title.setObjectName("RolesPageHeading")
        title.setProperty("titleKey", "roles.title")
        subtitle = QLabel(self.translator.text("roles.subtitle"))
        subtitle.setObjectName("RolesSubtitle")
        subtitle.setProperty("titleKey", "roles.subtitle")
        subtitle.setWordWrap(True)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        actions_box = QWidget()
        actions_layout = QHBoxLayout(actions_box)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        actions_layout.addStretch(1)
        refresh = QPushButton(self.translator.text("roles.refresh"))
        refresh.setProperty("textKey", "roles.refresh")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.refresh_roles)
        create = QPushButton(self.translator.text("roles.create"))
        create.setObjectName("PrimaryButton")
        create.setProperty("textKey", "roles.create")
        create.setCursor(Qt.CursorShape.PointingHandCursor)
        create.clicked.connect(self.create_role_dialog)
        actions_layout.addWidget(refresh)
        actions_layout.addWidget(create)

        self.roles_search = QLineEdit()
        self.roles_search.setProperty("placeholderKey", "roles.search_placeholder")
        self.roles_search.setPlaceholderText(
            self.translator.text("roles.search_placeholder")
        )
        self.roles_search.setClearButtonEnabled(True)
        self.roles_search.textChanged.connect(self._apply_roles_filter)

        toolbar_layout.addWidget(title_box, 0, 0)
        toolbar_layout.addWidget(actions_box, 0, 1)
        toolbar_layout.addWidget(self.roles_search, 1, 0, 1, 2)
        toolbar_layout.setColumnStretch(0, 1)

        self.roles_stats_widget = QWidget()
        roles_stats_layout = QHBoxLayout(self.roles_stats_widget)
        roles_stats_layout.setContentsMargins(0, 0, 0, 0)
        roles_stats_layout.setSpacing(10)
        total_card, self.roles_total_value = self._make_roles_stat_card(
            "roles.stats.total", "RolesStatCardTotal"
        )
        permission_card, self.roles_available_permissions_value = (
            self._make_roles_stat_card(
                "roles.stats.available_permissions", "RolesStatCardPermissions"
            )
        )
        granted_card, self.roles_granted_permissions_value = (
            self._make_roles_stat_card(
                "roles.stats.selected_granted", "RolesStatCardGranted"
            )
        )
        roles_stats_layout.addWidget(total_card, 1)
        roles_stats_layout.addWidget(permission_card, 1)
        roles_stats_layout.addWidget(granted_card, 1)

        self.roles_table = QTableWidget(0, 3)
        self.roles_table.setObjectName("RolesTable")
        self._configure_table(self.roles_table)
        self.roles_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        roles_vertical_header = self.roles_table.verticalHeader()
        if roles_vertical_header is not None:
            roles_vertical_header.setDefaultSectionSize(46)
        self._set_roles_table_headers()
        self.roles_table.itemSelectionChanged.connect(
            self._render_selected_role_permissions
        )
        self._install_record_actions(
            self.roles_table,
            view=lambda row: self._show_record_details(
                self.translator.text("roles.title"), row
            ),
            edit=self.edit_role_dialog,
            lifecycle=self.delete_role_action,
            lifecycle_label=lambda _row: self.translator.text("crud.delete"),
        )

        self.roles_empty_state = self._build_roles_empty_state()
        self.roles_table_stack = QStackedWidget()
        self.roles_table_stack.addWidget(self.roles_table)
        self.roles_table_stack.addWidget(self.roles_empty_state)

        self.roles_permissions_drawer = self._build_roles_permissions_drawer()
        self.roles_permissions_drawer.hide()
        self.roles_permissions_drawer.setMinimumWidth(0)
        self.roles_permissions_drawer.setMaximumWidth(0)

        self.roles_table_container = QWidget()
        self.roles_table_container_layout = QHBoxLayout(self.roles_table_container)
        self.roles_table_container_layout.setContentsMargins(0, 0, 0, 0)
        self.roles_table_container_layout.setSpacing(12)
        self.roles_table_container_layout.addWidget(self.roles_table_stack, 7)
        self.roles_table_container_layout.addWidget(self.roles_permissions_drawer, 3)

        list_card = QFrame()
        list_card.setObjectName("RolesListCard")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(14)
        list_meta = QHBoxLayout()
        list_meta.setContentsMargins(0, 0, 0, 0)
        self.roles_visible_count_label = QLabel()
        self.roles_visible_count_label.setObjectName("RolesVisibleCount")
        list_meta.addWidget(self.roles_visible_count_label)
        list_meta.addStretch(1)
        list_layout.addLayout(list_meta)
        list_layout.addWidget(self.roles_table_container, 1)
        self.roles_pagination_bar = self._build_roles_pagination_bar()
        list_layout.addWidget(self.roles_pagination_bar)
        self.roles_list_card = list_card

        self.roles_desktop_page = QWidget()
        self.roles_desktop_layout = QVBoxLayout(self.roles_desktop_page)
        self.roles_desktop_layout.setContentsMargins(0, 0, 0, 0)
        self.roles_desktop_layout.addWidget(self.roles_list_card, 1)

        self.roles_narrow_detail_page = QWidget()
        self.roles_narrow_detail_layout = QVBoxLayout(
            self.roles_narrow_detail_page
        )
        self.roles_narrow_detail_layout.setContentsMargins(0, 0, 0, 0)
        self.roles_narrow_detail_layout.setSpacing(0)

        self.roles_content_stack = QStackedWidget()
        self.roles_content_stack.addWidget(self.roles_desktop_page)
        self.roles_content_stack.addWidget(self.roles_narrow_detail_page)

        layout.addWidget(toolbar)
        layout.addWidget(self.roles_stats_widget)
        layout.addWidget(self.roles_content_stack, 1)
        return page

    def _make_roles_stat_card(
        self, title_key: str, card_name: str
    ) -> tuple[QFrame, QLabel]:
        """Create one Roles summary card."""

        card = QFrame()
        card.setObjectName(card_name)
        card.setMinimumHeight(76)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(15, 23, 42, 12))
        shadow.setOffset(0, 3)
        card.setGraphicsEffect(shadow)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(3)
        title = QLabel(self.translator.text(title_key))
        title.setObjectName("RolesStatTitle")
        title.setProperty("titleKey", title_key)
        value = QLabel("0")
        value.setObjectName("RolesStatValue")
        card_layout.addWidget(title)
        card_layout.addWidget(value)
        card_layout.addStretch(1)
        return card, value

    def _build_roles_empty_state(self) -> QFrame:
        """Create the empty state used by the Roles list."""

        frame = QFrame()
        frame.setObjectName("RolesEmptyState")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(22, 22, 22, 22)
        frame_layout.setSpacing(6)
        frame_layout.addStretch(1)
        self.roles_empty_title = QLabel()
        self.roles_empty_title.setObjectName("RolesPageHeading")
        self.roles_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.roles_empty_body = QLabel()
        self.roles_empty_body.setObjectName("RolesEmptyBody")
        self.roles_empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.roles_empty_body.setWordWrap(True)
        frame_layout.addWidget(self.roles_empty_title)
        frame_layout.addWidget(self.roles_empty_body)
        frame_layout.addStretch(1)
        return frame

    def _build_roles_permissions_drawer(self) -> QFrame:
        """Create the selected-role permission detail card."""

        drawer = QFrame()
        drawer.setObjectName("RolesPermissionsDrawer")
        drawer_layout = QVBoxLayout(drawer)
        drawer_layout.setContentsMargins(18, 16, 18, 16)
        drawer_layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.roles_drawer_back = QPushButton(
            self.translator.text("roles.back_to_roles")
        )
        self.roles_drawer_back.setObjectName("RolesBackButton")
        self.roles_drawer_back.setProperty("textKey", "roles.back_to_roles")
        self.roles_drawer_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.roles_drawer_back.clicked.connect(self._close_role_permissions)
        self.roles_drawer_back.hide()
        header.addWidget(self.roles_drawer_back)
        header.addStretch(1)
        self.roles_drawer_close = QPushButton("\u00d7")
        self.roles_drawer_close.setObjectName("RolesDrawerClose")
        self.roles_drawer_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.roles_drawer_close.setToolTip(
            self.translator.text("roles.close_permissions")
        )
        self.roles_drawer_close.clicked.connect(self._close_role_permissions)
        header.addWidget(self.roles_drawer_close)
        drawer_layout.addLayout(header)

        self.roles_drawer_title = QLabel()
        self.roles_drawer_title.setObjectName("RolesDrawerHeading")
        self.roles_drawer_title.setWordWrap(True)
        self.roles_drawer_description = QLabel()
        self.roles_drawer_description.setObjectName("RolesDrawerDescription")
        self.roles_drawer_description.setWordWrap(True)
        drawer_layout.addWidget(self.roles_drawer_title)
        drawer_layout.addWidget(self.roles_drawer_description)

        summary = QHBoxLayout()
        summary_label = QLabel(self.translator.text("roles.drawer.assigned"))
        summary_label.setObjectName("RolesSubtitle")
        summary_label.setProperty("titleKey", "roles.drawer.assigned")
        self.roles_drawer_count = QLabel("0")
        self.roles_drawer_count.setObjectName("RolesPermissionCountBadge")
        summary.addWidget(summary_label)
        summary.addStretch(1)
        summary.addWidget(self.roles_drawer_count)
        drawer_layout.addLayout(summary)

        self.roles_permission_search = QLineEdit()
        self.roles_permission_search.setProperty(
            "placeholderKey", "roles.permissions.search_placeholder"
        )
        self.roles_permission_search.setPlaceholderText(
            self.translator.text("roles.permissions.search_placeholder")
        )
        self.roles_permission_search.setClearButtonEnabled(True)
        self.roles_permission_search.textChanged.connect(
            self._render_role_permission_cards
        )
        self.roles_permission_module_filter = QComboBox()
        self.roles_permission_module_filter.currentIndexChanged.connect(
            lambda _index: self._render_role_permission_cards()
        )
        drawer_layout.addWidget(self.roles_permission_search)
        drawer_layout.addWidget(self.roles_permission_module_filter)

        self.roles_permission_scroll = QScrollArea()
        self.roles_permission_scroll.setObjectName("RolesPermissionScroll")
        self.roles_permission_scroll.setWidgetResizable(True)
        self.roles_permission_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.roles_permission_cards_container = QWidget()
        self.roles_permission_cards_layout = QVBoxLayout(
            self.roles_permission_cards_container
        )
        self.roles_permission_cards_layout.setContentsMargins(0, 0, 4, 0)
        self.roles_permission_cards_layout.setSpacing(8)
        self.roles_permission_scroll.setWidget(
            self.roles_permission_cards_container
        )
        drawer_layout.addWidget(self.roles_permission_scroll, 1)
        return drawer

    def _build_settings_page(self) -> QWidget:
        """Build settings page."""

        page, layout, _title = self._page("settings.title")
        self.settings_text = QPlainTextEdit()
        self.settings_text.hide()
        self.settings_values: ApiRow = {}
        self.settings_fields: dict[tuple[str, ...], QLineEdit] = {}
        action_row = QHBoxLayout()
        refresh = QPushButton()
        refresh.setProperty("textKey", "dashboard.refresh")
        refresh.clicked.connect(self.refresh_settings)
        save = QPushButton()
        save.setProperty("textKey", "settings.save")
        save.clicked.connect(self.save_settings)
        action_row.addWidget(refresh)
        action_row.addWidget(save)
        action_row.addStretch(1)
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_forms_container = QWidget()
        self.settings_forms_layout = QVBoxLayout(self.settings_forms_container)
        self.settings_forms_layout.setContentsMargins(0, 0, 12, 0)
        self.settings_forms_layout.setSpacing(12)
        self.settings_scroll.setWidget(self.settings_forms_container)
        layout.addLayout(action_row)
        layout.addWidget(self.settings_scroll, 1)
        return page

    def _build_hardware_page(self) -> QWidget:
        """Build hardware simulator page."""

        page, layout, _title = self._page("hardware.title")
        self.hardware_text = QPlainTextEdit()
        self.hardware_text.setReadOnly(True)
        actions: list[tuple[str, Callable[[], object]]] = [
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
        for widget in (
            self.catalog_search,
            refresh,
            create_group,
            create_product,
            create_service,
            find_barcode,
        ):
            action_row.addWidget(widget)
        action_row.addStretch(1)

        self.catalog_table = QTableWidget(0, len(CATALOG_TABLE_HEADER_KEYS))
        self._configure_table(self.catalog_table)
        self._set_catalog_table_headers()
        self._install_record_actions(
            self.catalog_table,
            view=lambda row: self._show_record_details(
                self.translator.text("catalog.title"), row
            ),
            edit=self.edit_product_dialog,
            lifecycle=self.toggle_product_active_action,
            lifecycle_label=self._active_lifecycle_label,
        )
        self.product_groups_table = QTableWidget(0, 5)
        self._configure_table(self.product_groups_table)
        self._install_record_actions(
            self.product_groups_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.product_groups"), row
            ),
            edit=self.edit_product_group_dialog,
            lifecycle=self.toggle_product_group_active_action,
            lifecycle_label=self._active_lifecycle_label,
        )
        self.services_table = QTableWidget(0, 6)
        self._configure_table(self.services_table)
        self._install_record_actions(
            self.services_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.services"), row
            ),
            edit=self.edit_service_dialog,
            lifecycle=self.toggle_service_active_action,
            lifecycle_label=self._active_lifecycle_label,
        )
        tabs = QTabWidget()
        tabs.addTab(self.catalog_table, self.translator.text("tabs.products"))
        tabs.addTab(
            self.product_groups_table, self.translator.text("tabs.product_groups")
        )
        tabs.addTab(self.services_table, self.translator.text("tabs.services"))
        self.catalog_tabs = tabs
        layout.addLayout(action_row)
        layout.addWidget(tabs, 1)
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
        for widget in (
            refresh,
            create_warehouse,
            opening_inventory,
            transfer,
            writeoff,
        ):
            action_row.addWidget(widget)
        action_row.addStretch(1)

        self.warehouse_table = QTableWidget(0, len(WAREHOUSE_TABLE_HEADER_KEYS))
        self._configure_table(self.warehouse_table)
        self._set_warehouse_table_headers()
        self._install_record_actions(
            self.warehouse_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.balances"), row
            ),
        )
        self.warehouses_table = QTableWidget(0, 5)
        self._configure_table(self.warehouses_table)
        self._install_record_actions(
            self.warehouses_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.warehouses"), row
            ),
            edit=self.edit_warehouse_dialog,
            lifecycle=self.toggle_warehouse_active_action,
            lifecycle_label=self._active_lifecycle_label,
        )
        self.warehouse_movements_text = QPlainTextEdit()
        self.warehouse_movements_text.setReadOnly(True)
        self.warehouse_movements_text.hide()
        self.warehouse_movements_table = QTableWidget(0, 8)
        self._configure_table(self.warehouse_movements_table)
        self._install_record_actions(
            self.warehouse_movements_table,
            view=lambda row: self._show_record_details(
                self.translator.text("warehouse.movements"), row
            ),
        )
        self.inventories_table = QTableWidget(0, 6)
        self._configure_table(self.inventories_table)
        self._install_record_actions(
            self.inventories_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.inventories"), row
            ),
            edit=self.edit_inventory_dialog,
            lifecycle=self.cancel_inventory_action,
            lifecycle_label=lambda _row: self.translator.text("crud.cancel"),
            edit_enabled=lambda row: row.get("status") in {"draft", "in_progress"},
            lifecycle_enabled=lambda row: row.get("status") in {"draft", "in_progress"},
        )
        self.stock_transfers_table = QTableWidget(0, 6)
        self._configure_table(self.stock_transfers_table)
        self._install_record_actions(
            self.stock_transfers_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.transfers"), row
            ),
            edit=self.edit_stock_transfer_dialog,
            lifecycle=self.reject_stock_transfer_action,
            lifecycle_label=lambda _row: self.translator.text("crud.cancel"),
            edit_enabled=lambda row: row.get("status") == "draft",
            lifecycle_enabled=lambda row: row.get("status") == "in_transit",
        )
        self.stock_writeoffs_table = QTableWidget(0, 6)
        self._configure_table(self.stock_writeoffs_table)
        self._install_record_actions(
            self.stock_writeoffs_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.writeoffs"), row
            ),
            edit=self.edit_stock_writeoff_dialog,
            lifecycle=self.cancel_stock_writeoff_action,
            lifecycle_label=lambda _row: self.translator.text("crud.cancel"),
            edit_enabled=lambda row: row.get("status") == "draft",
            lifecycle_enabled=lambda row: row.get("status") != "cancelled",
        )
        tabs = QTabWidget()
        tabs.addTab(self.warehouses_table, self.translator.text("tabs.warehouses"))
        tabs.addTab(self.warehouse_table, self.translator.text("tabs.balances"))
        tabs.addTab(
            self.warehouse_movements_table, self.translator.text("tabs.movements")
        )
        tabs.addTab(self.inventories_table, self.translator.text("tabs.inventories"))
        tabs.addTab(self.stock_transfers_table, self.translator.text("tabs.transfers"))
        tabs.addTab(self.stock_writeoffs_table, self.translator.text("tabs.writeoffs"))
        self.warehouse_tabs = tabs
        layout.addLayout(action_row)
        layout.addWidget(tabs, 1)
        return page

    def _build_counterparties_page(self) -> QWidget:
        """Build counterparties page."""

        page, layout, _title = self._page("counterparties.title")
        action_row = QHBoxLayout()
        self.counterparty_search = QLineEdit()
        self.counterparty_search.setPlaceholderText(
            self.translator.text("counterparties.search")
        )
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
        self._configure_table(self.counterparties_table)
        self._set_counterparties_table_headers()
        self._install_record_actions(
            self.counterparties_table,
            view=lambda row: self._show_record_details(
                self.translator.text("counterparties.title"), row
            ),
            edit=self.edit_counterparty_dialog,
            lifecycle=self.toggle_counterparty_active_action,
            lifecycle_label=self._active_lifecycle_label,
        )
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
        self._configure_table(self.pricing_table)
        self._set_pricing_table_headers()
        self._install_record_actions(
            self.pricing_table,
            view=lambda row: self._show_record_details(
                self.translator.text("pricing.title"), row
            ),
            edit=self.edit_price_list_dialog,
            lifecycle=self.toggle_price_list_active_action,
            lifecycle_label=self._active_lifecycle_label,
        )
        self.price_items_table = QTableWidget(0, 7)
        self._configure_table(self.price_items_table)
        self._install_record_actions(
            self.price_items_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.price_items"), row
            ),
            edit=self.edit_price_item_dialog,
            lifecycle=self.delete_price_item_action,
            lifecycle_label=lambda _row: self.translator.text("crud.delete"),
        )
        pricing_tabs = QTabWidget()
        pricing_tabs.addTab(
            self.pricing_table, self.translator.text("tabs.price_lists")
        )
        pricing_tabs.addTab(
            self.price_items_table, self.translator.text("tabs.price_items")
        )
        self.pricing_tabs = pricing_tabs
        layout.addLayout(action_row)
        layout.addWidget(pricing_tabs, 1)
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
        for widget in (
            refresh,
            create_order,
            create_invoice,
            create_return,
            create_payment,
        ):
            action_row.addWidget(widget)
        action_row.addStretch(1)
        self.purchase_table = QTableWidget(0, len(PURCHASE_TABLE_HEADER_KEYS))
        self._configure_table(self.purchase_table)
        self._set_purchase_table_headers()
        self._install_record_actions(
            self.purchase_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.invoices"), row
            ),
            edit=self.edit_purchase_invoice_dialog,
            lifecycle=self.cancel_purchase_invoice_action,
            lifecycle_label=lambda _row: self.translator.text("crud.cancel"),
            edit_enabled=lambda row: row.get("status") == "draft",
            lifecycle_enabled=lambda row: row.get("status") != "cancelled",
        )
        self.purchase_orders_table = QTableWidget(0, len(PURCHASE_TABLE_HEADER_KEYS))
        self._configure_table(self.purchase_orders_table)
        self._install_record_actions(
            self.purchase_orders_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.orders"), row
            ),
            edit=self.edit_purchase_order_dialog,
            lifecycle=self.cancel_purchase_order_action,
            lifecycle_label=lambda _row: self.translator.text("crud.cancel"),
            edit_enabled=lambda row: row.get("status") in {"draft", "sent"},
            lifecycle_enabled=lambda row: (
                row.get("status") not in {"cancelled", "received", "partial"}
            ),
        )
        self.purchase_debt_text = QPlainTextEdit()
        self.purchase_debt_text.setReadOnly(True)
        self.purchase_debt_text.hide()
        self.purchase_debt_metrics, self.purchase_debt_metrics_layout = (
            self._metric_area()
        )
        self.purchase_debt_table = QTableWidget(0, 8)
        self._configure_table(self.purchase_debt_table)
        self._install_record_actions(
            self.purchase_debt_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.debt"), row
            ),
        )
        purchase_tabs = QTabWidget()
        purchase_tabs.addTab(
            self.purchase_orders_table, self.translator.text("tabs.orders")
        )
        purchase_tabs.addTab(self.purchase_table, self.translator.text("tabs.invoices"))
        purchase_tabs.addTab(
            self.purchase_debt_table, self.translator.text("tabs.debt")
        )
        self.purchase_tabs = purchase_tabs
        layout.addLayout(action_row)
        layout.addWidget(self.purchase_debt_metrics)
        layout.addWidget(purchase_tabs, 1)
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
        for widget in (
            refresh,
            create_sale,
            create_return,
            create_payment,
            cancel_sale,
        ):
            action_row.addWidget(widget)
        action_row.addStretch(1)
        self.sales_table = QTableWidget(0, len(SALES_TABLE_HEADER_KEYS))
        self._configure_table(self.sales_table)
        self._set_sales_table_headers()
        self._install_record_actions(
            self.sales_table,
            view=lambda row: self._show_record_details(
                self.translator.text("sales.title"), row
            ),
            edit=self.edit_sale_dialog,
            lifecycle=self.cancel_sale_action,
            lifecycle_label=lambda _row: self.translator.text("crud.cancel"),
            edit_enabled=lambda row: row.get("status") == "draft",
            lifecycle_enabled=lambda row: row.get("status") != "cancelled",
        )
        self.sale_returns_table = QTableWidget(0, len(SALES_TABLE_HEADER_KEYS))
        self._configure_table(self.sale_returns_table)
        self._install_record_actions(
            self.sale_returns_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.returns"), row
            ),
            edit=self.edit_sale_return_dialog,
            lifecycle=self.cancel_sale_return_action,
            lifecycle_label=lambda _row: self.translator.text("crud.cancel"),
            edit_enabled=lambda row: row.get("status") == "draft",
            lifecycle_enabled=lambda row: row.get("status") != "cancelled",
        )
        self.sales_debt_text = QPlainTextEdit()
        self.sales_debt_text.setReadOnly(True)
        self.sales_debt_text.hide()
        self.sales_debt_metrics, self.sales_debt_metrics_layout = self._metric_area()
        self.sales_debt_table = QTableWidget(0, 8)
        self._configure_table(self.sales_debt_table)
        self._install_record_actions(
            self.sales_debt_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.debt"), row
            ),
        )
        sales_tabs = QTabWidget()
        sales_tabs.addTab(self.sales_table, self.translator.text("tabs.sales"))
        sales_tabs.addTab(self.sale_returns_table, self.translator.text("tabs.returns"))
        sales_tabs.addTab(self.sales_debt_table, self.translator.text("tabs.debt"))
        self.sales_tabs = sales_tabs
        layout.addLayout(action_row)
        layout.addWidget(self.sales_debt_metrics)
        layout.addWidget(sales_tabs, 1)
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
        for widget in (
            refresh,
            create_register,
            open_shift,
            close_shift,
            cash_operation,
        ):
            action_row.addWidget(widget)
        action_row.addStretch(1)

        self.cashier_table = QTableWidget(0, len(CASHIER_TABLE_HEADER_KEYS))
        self._configure_table(self.cashier_table)
        self._set_cashier_table_headers()
        self._install_record_actions(
            self.cashier_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.shifts"), row
            ),
            lifecycle=self.close_cash_shift_action,
            lifecycle_label=lambda _row: self.translator.text("crud.close"),
            lifecycle_enabled=lambda row: row.get("status") == "open",
        )
        self.cash_registers_table = QTableWidget(0, 5)
        self._configure_table(self.cash_registers_table)
        self._install_record_actions(
            self.cash_registers_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.registers"), row
            ),
            edit=self.edit_cash_register_dialog,
            lifecycle=self.toggle_cash_register_active_action,
            lifecycle_label=self._active_lifecycle_label,
        )
        self.cashier_text = QPlainTextEdit()
        self.cashier_text.setReadOnly(True)
        self.cashier_text.hide()
        self.cashier_report_status = QLabel(self._ui("cash_flow_snapshot"))
        self.cashier_report_status.setProperty("titleKey", "ui.cash_flow_snapshot")
        self.cashier_report_status.setObjectName("SectionTitle")
        self.cashier_report_metrics, self.cashier_report_metrics_layout = (
            self._metric_area()
        )
        self.cashier_report_table = QTableWidget(0, 3)
        self._configure_table(self.cashier_report_table)
        self._install_record_actions(
            self.cashier_report_table,
            view=lambda row: self._show_record_details(
                self.translator.text("ui.cash_flow_snapshot"), row
            ),
        )
        cashier_tabs = QTabWidget()
        cashier_tabs.addTab(
            self.cash_registers_table, self.translator.text("tabs.registers")
        )
        cashier_tabs.addTab(self.cashier_table, self.translator.text("tabs.shifts"))
        cashier_tabs.addTab(
            self.cashier_report_table, self.translator.text("tabs.reports")
        )
        self.cashier_tabs = cashier_tabs

        cart_title = QLabel(self.translator.text("cashier.cart.title"))
        cart_title.setProperty("bodyKey", "cashier.cart.title")
        cart_title.setObjectName("SectionTitle")

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
        self._configure_table(self.cashier_cart_table)
        self.cashier_cart_table.setMinimumHeight(170)
        self.cashier_cart_table.itemSelectionChanged.connect(
            self.cashier_load_selected_cart_item
        )
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
            picker.clicked.connect(
                lambda _checked=False, field=target, pick=selector: pick(field)
            )
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
        layout.addWidget(self.cashier_report_status)
        layout.addWidget(self.cashier_report_metrics)
        layout.addWidget(cashier_tabs, 1)
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
        for code in (
            "dashboard",
            "stock",
            "sales",
            "purchases",
            "debts",
            "cash-flow",
            "profit-loss",
        ):
            self.report_code.addItem(self._report_code_text(code), code)
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
        self.report_debt_type.addItem(self._debt_type_text("receivable"), "receivable")
        self.report_debt_type.addItem(self._debt_type_text("payable"), "payable")

        filters = QFormLayout()
        filters.addRow(self.translator.text("reports.report_code"), self.report_code)
        filters.addRow(self.translator.text("reports.date_from"), self.report_date_from)
        filters.addRow(self.translator.text("reports.date_to"), self.report_date_to)
        self._add_selector_row(
            filters,
            "reports.warehouse_id",
            self.report_warehouse_id,
            self._select_warehouse_id,
        )
        self._add_selector_row(
            filters,
            "reports.counterparty_id",
            self.report_counterparty_id,
            self._select_counterparty_id,
        )
        self._add_selector_row(
            filters,
            "reports.product_id",
            self.report_product_id,
            self._select_product_id,
        )
        self._add_selector_row(
            filters,
            "reports.cash_register_id",
            self.report_cash_register_id,
            self._select_cash_register_id,
        )
        self._add_selector_row(
            filters,
            "reports.cash_shift_id",
            self.report_cash_shift_id,
            self._select_cash_shift_id,
        )
        filters.addRow(self.translator.text("reports.debt_type"), self.report_debt_type)
        filters.addRow(
            self.translator.text("reports.filter_name"), self.report_filter_name
        )

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
        self.reports_text.hide()
        filter_card, filter_layout = self._make_card(title_key="ui.filters")
        filter_layout.addLayout(filters)
        self.report_status_label = QLabel(self._ui("report_ready_prompt"))
        self.report_status_label.setProperty("bodyKey", "ui.report_ready_prompt")
        self.report_status_label.setObjectName("MutedLabel")
        self.report_metrics, self.report_metrics_layout = self._metric_area()
        self.report_rows_table = QTableWidget(0, 1)
        self._configure_table(self.report_rows_table)
        self._install_record_actions(
            self.report_rows_table,
            view=lambda row: self._show_record_details(
                self.translator.text("tabs.report_rows"), row
            ),
        )
        self.report_saved_filters_table = QTableWidget(0, 4)
        self._configure_table(self.report_saved_filters_table)
        self._set_report_saved_filters_table_headers()
        self._install_record_actions(
            self.report_saved_filters_table,
            view=lambda row: self._show_record_details(
                self.translator.text("ui.saved_filters"), row
            ),
            edit=self.edit_report_filter_dialog,
            lifecycle=self.delete_report_filter_action,
            lifecycle_label=lambda _row: self.translator.text("crud.delete"),
        )
        report_tabs = QTabWidget()
        report_tabs.addTab(
            self.report_rows_table, self.translator.text("tabs.report_rows")
        )
        report_tabs.addTab(
            self.report_saved_filters_table, self.translator.text("tabs.saved_filters")
        )
        self.report_tabs = report_tabs
        layout.addWidget(filter_card)
        layout.addLayout(actions)
        layout.addWidget(self.report_status_label)
        layout.addWidget(self.report_metrics)
        layout.addWidget(report_tabs, 1)
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

    def _columns_from_rows(
        self, rows: Sequence[ApiRow], preferred: tuple[str, ...] = ()
    ) -> list[SelectorColumn]:
        """Build readable table columns from API row dictionaries."""

        keys: list[str] = []
        for key in preferred:
            if any(key in row for row in rows):
                keys.append(key)
        for row in rows:
            for key in row:
                if key not in keys and key != "xlsx_base64":
                    keys.append(key)
        return [(key, self._humanize_key(key)) for key in keys]

    def _build_roles_pagination_bar(self) -> QFrame:
        """Build pagination controls for the role table."""

        bar = QFrame()
        bar.setObjectName("RolesPaginationBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 10, 16, 10)
        bar_layout.setSpacing(8)

        size_label = QLabel(self.translator.text("roles.pagination.per_page"))
        size_label.setObjectName("RolesPaginationInfo")
        size_label.setProperty("titleKey", "roles.pagination.per_page")
        self.roles_page_size_combo = QComboBox()
        self.roles_page_size_combo.setObjectName("RolesPageSizeCombo")
        self.roles_page_size_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for size in (5, 10, 15, 25):
            self.roles_page_size_combo.addItem(str(size), size)
        self.roles_page_size_combo.setCurrentIndex(1)
        self.roles_page_size_combo.currentIndexChanged.connect(
            lambda _index: self._change_roles_page_size(
                int(self.roles_page_size_combo.currentData() or 10)
            )
        )
        bar_layout.addWidget(size_label)
        bar_layout.addWidget(self.roles_page_size_combo)
        bar_layout.addStretch(1)

        self.roles_pagination_info = QLabel()
        self.roles_pagination_info.setObjectName("RolesPaginationInfo")
        bar_layout.addWidget(self.roles_pagination_info)
        bar_layout.addStretch(1)

        self.roles_page_nav_layout = QHBoxLayout()
        self.roles_page_nav_layout.setSpacing(4)
        self.roles_btn_first = QPushButton("\u00ab")
        self.roles_btn_prev = QPushButton("\u2039")
        self.roles_btn_next = QPushButton("\u203a")
        self.roles_btn_last = QPushButton("\u00bb")
        for button in (
            self.roles_btn_first,
            self.roles_btn_prev,
            self.roles_btn_next,
            self.roles_btn_last,
        ):
            button.setObjectName("RolesPaginationButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.roles_btn_first.clicked.connect(lambda: self._go_to_roles_page(0))
        self.roles_btn_prev.clicked.connect(
            lambda: self._go_to_roles_page(self.roles_current_page - 1)
        )
        self.roles_btn_next.clicked.connect(
            lambda: self._go_to_roles_page(self.roles_current_page + 1)
        )
        self.roles_btn_last.clicked.connect(
            lambda: self._go_to_roles_page(self._roles_total_pages() - 1)
        )
        self.roles_page_nav_layout.addWidget(self.roles_btn_first)
        self.roles_page_nav_layout.addWidget(self.roles_btn_prev)
        self.roles_page_buttons_container = QWidget()
        self.roles_page_buttons_layout = QHBoxLayout(
            self.roles_page_buttons_container
        )
        self.roles_page_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.roles_page_buttons_layout.setSpacing(4)
        self.roles_page_nav_layout.addWidget(self.roles_page_buttons_container)
        self.roles_page_nav_layout.addWidget(self.roles_btn_next)
        self.roles_page_nav_layout.addWidget(self.roles_btn_last)
        bar_layout.addLayout(self.roles_page_nav_layout)
        return bar

    def _apply_roles_filter(self, _text: str = "") -> None:
        """Filter role rows by name, description, or permission code."""

        if not hasattr(self, "roles_table"):
            return
        self.roles_current_page = 0
        query = self.roles_search.text().strip().casefold()
        filtered: list[ApiRow] = []
        for role in self.roles_rows:
            permissions = role.get("permissions") or []
            haystack = " ".join(
                [
                    str(role.get("name") or ""),
                    str(role.get("description") or ""),
                    " ".join(str(code) for code in permissions),
                ]
            ).casefold()
            if not query or query in haystack:
                filtered.append(role)
        self.roles_filtered_rows = filtered
        self._render_roles_table()

    def _render_roles_table(self) -> None:
        """Render the current page of filtered roles."""

        total = len(self.roles_filtered_rows)
        total_pages = self._roles_total_pages()
        self.roles_current_page = min(
            self.roles_current_page, max(0, total_pages - 1)
        )
        start = self.roles_current_page * self.roles_page_size
        end = min(start + self.roles_page_size, total)
        page_rows = self.roles_filtered_rows[start:end]
        selected_id = self.roles_selected_role_id

        self.roles_table.blockSignals(True)
        self.roles_table.setSortingEnabled(False)
        self.roles_table.clearSelection()
        self.roles_table.setRowCount(len(page_rows))
        selected_row = -1
        for row_index, role in enumerate(page_rows):
            values = (
                role.get("id"),
                role.get("name"),
                role.get("description"),
            )
            for column_index, value in enumerate(values):
                item = self._table_item(value)
                item.setData(Qt.ItemDataRole.UserRole, role)
                self.roles_table.setItem(row_index, column_index, item)
            self.roles_table.setRowHeight(row_index, 46)
            if selected_id is not None and str(role.get("id")) == str(selected_id):
                selected_row = row_index
        self._configure_roles_table_columns()
        if selected_row >= 0:
            self.roles_table.selectRow(selected_row)
        self.roles_table.blockSignals(False)

        if selected_id is not None and selected_row < 0:
            self._close_role_permissions(clear_selection=True, animate=False)
        self.roles_visible_count_label.setText(
            self.translator.text("roles.visible_count").format(
                visible=total, total=len(self.roles_rows)
            )
        )
        self._update_roles_empty_state(total)
        self._update_roles_pagination()

    def _update_roles_empty_state(self, visible_count: int) -> None:
        """Switch between the role table and its empty state."""

        if visible_count:
            self.roles_table_stack.setCurrentWidget(self.roles_table)
            return
        has_roles = bool(self.roles_rows)
        self.roles_empty_title.setText(
            self.translator.text(
                "roles.empty.filtered_title"
                if has_roles
                else "roles.empty.no_roles_title"
            )
        )
        self.roles_empty_body.setText(
            self.translator.text(
                "roles.empty.filtered_body"
                if has_roles
                else "roles.empty.no_roles_body"
            )
        )
        self.roles_table_stack.setCurrentWidget(self.roles_empty_state)

    def _roles_total_pages(self) -> int:
        """Return the number of pages required by the filtered role rows."""

        total = len(self.roles_filtered_rows)
        return max(1, (total + self.roles_page_size - 1) // self.roles_page_size)

    def _update_roles_pagination(self) -> None:
        """Refresh role pagination text, buttons, and active page."""

        total = len(self.roles_filtered_rows)
        total_pages = self._roles_total_pages()
        start = self.roles_current_page * self.roles_page_size + 1
        end = min(start + self.roles_page_size - 1, total)
        if total == 0:
            start = 0
            end = 0
        self.roles_pagination_info.setText(
            self.translator.text("roles.pagination.showing").format(
                start=start, end=end, total=total
            )
        )
        self.roles_btn_first.setEnabled(self.roles_current_page > 0)
        self.roles_btn_prev.setEnabled(self.roles_current_page > 0)
        self.roles_btn_next.setEnabled(self.roles_current_page < total_pages - 1)
        self.roles_btn_last.setEnabled(self.roles_current_page < total_pages - 1)

        while self.roles_page_buttons_layout.count():
            child = self.roles_page_buttons_layout.takeAt(0)
            if child is not None and child.widget() is not None:
                child.widget().deleteLater()
        max_visible = 5
        first_page = max(
            0,
            min(
                self.roles_current_page - max_visible // 2,
                total_pages - max_visible,
            ),
        )
        for page_index in range(
            first_page, min(total_pages, first_page + max_visible)
        ):
            button = QPushButton(str(page_index + 1))
            button.setObjectName(
                "RolesPaginationButtonActive"
                if page_index == self.roles_current_page
                else "RolesPaginationButton"
            )
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, page=page_index: self._go_to_roles_page(page)
            )
            self.roles_page_buttons_layout.addWidget(button)

    def _go_to_roles_page(self, page: int) -> None:
        """Navigate to a role table page."""

        self.roles_current_page = max(0, min(page, self._roles_total_pages() - 1))
        self._render_roles_table()

    def _change_roles_page_size(self, size: int) -> None:
        """Change the role page size and return to the first page."""

        self.roles_page_size = max(1, size)
        self.roles_current_page = 0
        self._render_roles_table()

    def _configure_roles_table_columns(self) -> None:
        """Apply responsive sizing to role table columns."""

        header = self.roles_table.horizontalHeader()
        if header is None:
            return
        for i in range(self.roles_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

    def _selected_role(self) -> ApiRow | None:
        """Return the currently selected role from loaded state."""

        if self.roles_selected_role_id is None:
            return None
        for role in self.roles_rows:
            if str(role.get("id")) == str(self.roles_selected_role_id):
                return role
        return None

    def _render_selected_role_permissions(self) -> None:
        """Open and render permissions for the selected role."""

        role = self._selected_table_row(self.roles_table)
        if role is None:
            return
        self.roles_selected_role_id = role.get("id")
        permissions = [str(code) for code in role.get("permissions") or []]
        self.roles_drawer_title.setText(str(role.get("name") or "-"))
        self.roles_drawer_description.setText(
            str(
                role.get("description")
                or self.translator.text("roles.drawer.no_description")
            )
        )
        self.roles_drawer_count.setText(str(len(permissions)))
        self.roles_granted_permissions_value.setText(str(len(permissions)))
        self.roles_permission_search.blockSignals(True)
        self.roles_permission_search.clear()
        self.roles_permission_search.blockSignals(False)
        self._populate_role_permission_module_filter(permissions)
        self._render_role_permission_cards()
        self._open_role_permissions()

    def _permission_rows_for_selected_role(self) -> list[ApiRow]:
        """Return metadata-enriched permissions assigned to the selected role."""

        role = self._selected_role()
        if role is None:
            return []
        rows: list[ApiRow] = []
        for value in role.get("permissions") or []:
            code = str(value)
            metadata = self.roles_permission_catalog.get(code, {})
            rows.append(
                {
                    "code": code,
                    "module": metadata.get("module")
                    or (code.split(".", 1)[0] if "." in code else "-"),
                    "description": metadata.get("description") or "",
                }
            )
        return sorted(rows, key=lambda row: (str(row["module"]), str(row["code"])))

    def _populate_role_permission_module_filter(
        self, permissions: Sequence[str]
    ) -> None:
        """Populate module choices for the selected role."""

        selected = self.roles_permission_module_filter.currentData()
        modules = sorted(
            {
                str(
                    self.roles_permission_catalog.get(code, {}).get("module")
                    or (code.split(".", 1)[0] if "." in code else "-")
                )
                for code in permissions
            }
        )
        self.roles_permission_module_filter.blockSignals(True)
        self.roles_permission_module_filter.clear()
        self.roles_permission_module_filter.addItem(
            self.translator.text("roles.permissions.all_modules"), "all"
        )
        for module in modules:
            self.roles_permission_module_filter.addItem(module, module)
        index = self.roles_permission_module_filter.findData(selected)
        self.roles_permission_module_filter.setCurrentIndex(index if index >= 0 else 0)
        self.roles_permission_module_filter.blockSignals(False)

    def _render_role_permission_cards(self, _value: object = None) -> None:
        """Render assigned permissions using the active search and module filter."""

        if not hasattr(self, "roles_permission_cards_layout"):
            return
        self._clear_layout(self.roles_permission_cards_layout)
        query = self.roles_permission_search.text().strip().casefold()
        module_filter = self.roles_permission_module_filter.currentData()
        visible: list[ApiRow] = []
        for permission in self._permission_rows_for_selected_role():
            if module_filter not in (None, "all") and str(
                permission.get("module")
            ) != str(module_filter):
                continue
            haystack = " ".join(
                str(permission.get(key) or "")
                for key in ("code", "module", "description")
            ).casefold()
            if query and query not in haystack:
                continue
            visible.append(permission)

        if not visible:
            empty = QFrame()
            empty.setObjectName("RolesPermissionsEmptyState")
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(16, 24, 16, 24)
            empty_title = QLabel(
                self.translator.text("roles.permissions.empty_title")
            )
            empty_title.setObjectName("RolesDrawerHeading")
            empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_body = QLabel(
                self.translator.text("roles.permissions.empty_body")
            )
            empty_body.setObjectName("RolesEmptyBody")
            empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_body.setWordWrap(True)
            empty_layout.addWidget(empty_title)
            empty_layout.addWidget(empty_body)
            self.roles_permission_cards_layout.addWidget(empty)
            self.roles_permission_cards_layout.addStretch(1)
            return

        for permission in visible:
            card = QFrame()
            card.setObjectName("RolesPermissionCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(6)
            top = QHBoxLayout()
            code = QLabel(str(permission.get("code") or "-"))
            code.setObjectName("RolesPermissionCode")
            code.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            module = QLabel(str(permission.get("module") or "-"))
            module.setObjectName("RolesPermissionModule")
            top.addWidget(code, 1)
            top.addWidget(module)
            card_layout.addLayout(top)
            description = str(permission.get("description") or "")
            if description:
                description_label = QLabel(description)
                description_label.setObjectName("RolesPermissionDescription")
                description_label.setWordWrap(True)
                card_layout.addWidget(description_label)
            self.roles_permission_cards_layout.addWidget(card)
        self.roles_permission_cards_layout.addStretch(1)

    def _open_role_permissions(self) -> None:
        """Open the permission detail in docked or narrow mode."""

        self._update_roles_responsive_layout()
        self.roles_permissions_drawer.show()
        if self.roles_narrow_mode:
            self.roles_content_stack.setCurrentWidget(
                self.roles_narrow_detail_page
            )
            self.roles_permissions_drawer.setMaximumWidth(16777215)
            return
        self.roles_content_stack.setCurrentWidget(self.roles_desktop_page)
        target_width = int(self.roles_table_container.width() * 0.3)
        if target_width < 100:
            target_width = 420
        self._animate_roles_drawer(target_width)

    def _close_role_permissions(
        self, *, clear_selection: bool = True, animate: bool = True
    ) -> None:
        """Close the selected-role detail and clear selection state."""

        if clear_selection:
            self.roles_selected_role_id = None
            self.roles_table.blockSignals(True)
            self.roles_table.clearSelection()
            self.roles_table.blockSignals(False)
        self.roles_granted_permissions_value.setText("0")
        if self.roles_narrow_mode:
            self.roles_content_stack.setCurrentWidget(self.roles_desktop_page)
            self.roles_permissions_drawer.hide()
            return
        if animate and self.roles_permissions_drawer.isVisible():
            self.roles_permissions_drawer.setMaximumWidth(self.roles_permissions_drawer.width())
            self._animate_roles_drawer(0, hide_when_finished=True)
        else:
            self.roles_permissions_drawer.setMaximumWidth(0)
            self.roles_permissions_drawer.hide()

    def _animate_roles_drawer(
        self, target_width: int, *, hide_when_finished: bool = False
    ) -> None:
        """Animate the docked drawer's maximum width."""

        if self.roles_drawer_animation is not None:
            self.roles_drawer_animation.stop()
        animation = QPropertyAnimation(
            self.roles_permissions_drawer, b"maximumWidth", self
        )
        animation.setDuration(180)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(self.roles_permissions_drawer.maximumWidth())
        animation.setEndValue(target_width)
        if hide_when_finished:
            animation.finished.connect(self.roles_permissions_drawer.hide)
        else:
            def on_finished():
                if not self.roles_narrow_mode and self.roles_permissions_drawer.isVisible() and self._selected_role() is not None:
                    self.roles_permissions_drawer.setMaximumWidth(16777215)
            animation.finished.connect(on_finished)
        self.roles_drawer_animation = animation
        animation.start()

    def _update_roles_responsive_layout(self) -> None:
        """Move the permission card between docked and narrow detail layouts."""

        if not hasattr(self, "roles_permissions_drawer") or not hasattr(self, "roles_table_container_layout"):
            return
        narrow = self.width() < 1280
        if narrow == self.roles_narrow_mode and (
            self.roles_table_container_layout.indexOf(self.roles_permissions_drawer) >= 0
            or self.roles_narrow_detail_layout.indexOf(
                self.roles_permissions_drawer
            )
            >= 0
        ):
            return
        if self.roles_drawer_animation is not None:
            self.roles_drawer_animation.stop()
        self.roles_narrow_mode = narrow
        self.roles_table_container_layout.removeWidget(self.roles_permissions_drawer)
        self.roles_narrow_detail_layout.removeWidget(
            self.roles_permissions_drawer
        )
        selected = self._selected_role() is not None
        if narrow:
            self.roles_narrow_detail_layout.addWidget(
                self.roles_permissions_drawer
            )
            self.roles_drawer_back.show()
            self.roles_drawer_close.hide()
            self.roles_permissions_drawer.setMaximumWidth(16777215)
            if selected:
                self.roles_permissions_drawer.show()
                self.roles_content_stack.setCurrentWidget(
                    self.roles_narrow_detail_page
                )
            else:
                self.roles_permissions_drawer.hide()
                self.roles_content_stack.setCurrentWidget(
                    self.roles_desktop_page
                )
            return
        self.roles_table_container_layout.addWidget(self.roles_permissions_drawer, 3)
        self.roles_drawer_back.hide()
        self.roles_drawer_close.show()
        self.roles_content_stack.setCurrentWidget(self.roles_desktop_page)
        if selected:
            self.roles_permissions_drawer.show()
            self.roles_permissions_drawer.setMaximumWidth(16777215)
        else:
            self.roles_permissions_drawer.setMaximumWidth(0)
            self.roles_permissions_drawer.hide()

    def _render_settings_forms(self, settings: ApiRow) -> None:
        """Render editable settings forms without exposing raw JSON."""

        self.settings_fields = {}
        self._clear_layout(self.settings_forms_layout)
        if not settings:
            empty = QLabel(self._ui("no_settings"))
            empty.setObjectName("MutedLabel")
            self.settings_forms_layout.addWidget(empty)
            self.settings_forms_layout.addStretch(1)
            return

        for key in sorted(settings):
            value = settings[key]
            card, card_layout = self._make_card(self._humanize_key(key))
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            if isinstance(value, dict):
                for child_key in sorted(value):
                    child_value = value[child_key]
                    self._add_settings_field(form, (key, child_key), child_value)
            else:
                self._add_settings_field(form, (key,), value)
            card_layout.addLayout(form)
            self.settings_forms_layout.addWidget(card)
        self.settings_forms_layout.addStretch(1)

    def _add_settings_field(
        self, form: QFormLayout, path: tuple[str, ...], value: object
    ) -> None:
        """Add one editable or read-only settings field."""

        label = self._humanize_key(path[-1])
        if isinstance(value, (dict, list, tuple)):
            preview = QLabel(self._format_value(value))
            preview.setObjectName("MutedLabel")
            form.addRow(label, preview)
            return
        field = QLineEdit("" if value is None else str(value))
        field.setProperty("settingsPath", ".".join(path))
        field.setPlaceholderText(label)
        self.settings_fields[path] = field
        form.addRow(label, field)

    def _setting_value_from_text(self, text: str, original: object) -> object:
        """Parse settings form text using the original value type."""

        value = text.strip()
        if isinstance(original, bool):
            return value.casefold() in {"1", "true", "yes", "y", "on"}
        if isinstance(original, int) and not isinstance(original, bool):
            return int(value or "0")
        if isinstance(original, float):
            return float(value or "0")
        if isinstance(original, Decimal):
            return str(Decimal(value or "0"))
        if original is None:
            return value or None
        return value

    def _settings_value_at_path(self, path: tuple[str, ...]) -> object:
        """Return the original settings value for a rendered field path."""

        current: object = self.settings_values
        for part in path:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def _render_debt_ledger(
        self,
        rows: list[ApiRow],
        table: QTableWidget,
        metrics_layout: QHBoxLayout,
        *,
        title: str,
    ) -> None:
        """Render receivable/payable ledger rows and summaries."""

        self._populate_table(
            table,
            rows,
            [
                ("doc_date", self._ui("date")),
                ("doc_number", self._ui("document")),
                ("doc_type", self._ui("type")),
                ("debt_type", self._ui("debt")),
                ("debit_tmt", self._ui("debit")),
                ("credit_tmt", self._ui("credit")),
                ("running_balance_tmt", self._ui("balance")),
                ("note", self._ui("note")),
            ],
        )
        balance = rows[0].get("running_balance_tmt") if rows else "0.00"
        self._render_metric_cards(
            metrics_layout,
            [
                (title, len(rows)),
                (self._ui("debit_tmt"), f"{self._sum_rows(rows, 'debit_tmt')}"),
                (self._ui("credit_tmt"), f"{self._sum_rows(rows, 'credit_tmt')}"),
                (self._ui("current_balance"), balance),
            ],
        )

    def _render_cash_report(self, report: ApiRow, *, title: str | None = None) -> None:
        """Render cashier cash-flow or shift report data."""

        self.cashier_report_status.setText(title or self._ui("cash_flow_snapshot"))
        metric_keys = [
            key
            for key, value in report.items()
            if key != "rows" and not isinstance(value, (dict, list, tuple))
        ]
        metrics = [
            (self._humanize_key(key), report.get(key)) for key in metric_keys[:6]
        ]
        self._render_metric_cards(self.cashier_report_metrics_layout, metrics)
        rows = report.get("rows")
        if isinstance(rows, list) and all(isinstance(row, dict) for row in rows):
            typed_rows = [dict(row) for row in rows]
            columns = self._columns_from_rows(
                typed_rows, ("metric", "label", "amount_tmt", "value")
            ) or [("message", self._ui("message"))]
            self._populate_table(self.cashier_report_table, typed_rows, columns)
        else:
            summary_rows = [
                {"metric": self._humanize_key(key), "value": report.get(key)}
                for key in metric_keys
            ]
            self._populate_table(
                self.cashier_report_table,
                summary_rows,
                [("metric", self._ui("metric")), ("value", self._ui("value"))],
            )

    def _render_report_view(
        self,
        *,
        code: str,
        filters: dict[str, str],
        saved_filters: list[ApiRow],
        report: object,
    ) -> None:
        """Render report data as metrics, rows, and saved-filter tables."""

        filter_text = ", ".join(
            f"{self._humanize_key(key)}={value}" for key, value in filters.items()
        ) or self._ui("no_filters")
        self.report_status_label.setText(
            f"{self._report_code_text(code)} {self._ui('report_suffix')} - {filter_text}"
        )
        self._populate_table(
            self.report_saved_filters_table,
            saved_filters,
            [
                ("name", self._ui("name")),
                ("report_code", self._ui("report")),
                (
                    lambda row: (
                        self._ui("shared")
                        if row.get("is_shared")
                        else self._ui("private")
                    ),
                    self._ui("scope"),
                ),
                ("updated_at", self._ui("updated")),
            ],
        )

        if isinstance(report, list):
            rows = [dict(row) for row in report if isinstance(row, dict)]
            self._render_metric_cards(
                self.report_metrics_layout, [(self._ui("rows"), len(rows))]
            )
            self._populate_table(
                self.report_rows_table,
                rows,
                self._columns_from_rows(rows) or [("message", self._ui("message"))],
            )
            return

        if isinstance(report, dict):
            metric_keys = [
                key
                for key, value in report.items()
                if key != "rows" and not isinstance(value, (dict, list, tuple))
            ]
            metrics = [
                (self._humanize_key(key), report.get(key)) for key in metric_keys
            ]
            rows_payload = report.get("rows")
            rows = (
                [dict(row) for row in rows_payload if isinstance(row, dict)]
                if isinstance(rows_payload, list)
                else []
            )
            if not metrics:
                metrics = [(self._ui("rows"), len(rows))]
            self._render_metric_cards(self.report_metrics_layout, metrics)
            if rows:
                self._populate_table(
                    self.report_rows_table, rows, self._columns_from_rows(rows)
                )
            else:
                summary_rows = [
                    {"metric": self._humanize_key(key), "value": report.get(key)}
                    for key in metric_keys
                ]
                self._populate_table(
                    self.report_rows_table,
                    summary_rows,
                    [("metric", self._ui("metric")), ("value", self._ui("value"))],
                )
            return

        self._render_metric_cards(
            self.report_metrics_layout,
            [(self._ui("result"), self._format_value(report))],
        )
        self._populate_table(
            self.report_rows_table, [], [("message", self._ui("message"))]
        )

    def _render_report_result(self, payload: ApiRow, *, title: str) -> None:
        """Render export/save responses without showing JSON."""

        self.report_status_label.setText(title)
        rows_payload = payload.get("rows")
        rows = (
            [dict(row) for row in rows_payload if isinstance(row, dict)]
            if isinstance(rows_payload, list)
            else []
        )
        metric_keys = [key for key in payload if key not in {"rows", "xlsx_base64"}]
        self._render_metric_cards(
            self.report_metrics_layout,
            [(self._humanize_key(key), payload.get(key)) for key in metric_keys],
        )
        if rows:
            self._populate_table(
                self.report_rows_table, rows, self._columns_from_rows(rows)
            )
        else:
            self._populate_table(
                self.report_rows_table,
                [
                    {"field": self._humanize_key(key), "value": payload.get(key)}
                    for key in metric_keys
                ],
                [("field", self._ui("field")), ("value", self._ui("value"))],
            )

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
            status_text = (
                "РАБОТАЕТ" if lang == "ru" else "DEŇIZ" if lang == "tk" else "RUNNING"
            )
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
        self.user_id_val.setText(
            f"ID: {current_user_id}" if current_user_id != "" else "ID: -"
        )

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
        self.perm_val.setText(
            "AUTHORIZED"
            if lang == "en"
            else "АВТОРИЗОВАН"
            if lang == "ru"
            else "YGTYYARLY"
        )
        self.perm_desc.setText(
            "Session Token Valid"
            if lang == "en"
            else "Токен сессии действителен"
            if lang == "ru"
            else "Sessiýa tokeni dogry"
        )

    def _set_dashboard_offline(self, error_msg: str) -> None:
        """Adjust dashboard to represent offline/error state."""

        lang = self.translator.language
        offline_text = (
            "ОФФЛАЙН" if lang == "ru" else "OFLAYN" if lang == "tk" else "OFFLINE"
        )
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

        self.perm_val.setText(
            "OFFLINE" if lang == "en" else "ОФФЛАЙН" if lang == "ru" else "OFLAYN"
        )
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

    def refresh_catalog(self) -> None:
        """Refresh product catalog table."""

        def action() -> None:
            products = self.api_client.get_products(
                self.catalog_search.text().strip() or None
            )
            self._populate_table(
                self.catalog_table,
                products,
                [
                    ("id", self.translator.text("catalog.table.id")),
                    (
                        lambda row: row.get("sku") or row.get("code"),
                        self.translator.text("catalog.table.code"),
                    ),
                    (
                        lambda row: row.get("name") or row.get("name_ru"),
                        self.translator.text("catalog.table.name"),
                    ),
                    ("retail_price", self.translator.text("catalog.table.price")),
                    ("is_active", self.translator.text("catalog.table.active")),
                ],
            )
            groups = self._api_list("get_product_groups")
            self._populate_table(
                self.product_groups_table,
                groups,
                [
                    ("id", "ID"),
                    ("code", self._ui("code")),
                    ("name_ru", self._ui("name")),
                    ("parent_id", self._humanize_key("parent_id")),
                    ("is_active", self._ui("active")),
                ],
            )
            services = self._api_list("get_services")
            self._populate_table(
                self.services_table,
                services,
                [
                    ("id", "ID"),
                    ("code", self._ui("code")),
                    ("name_ru", self._ui("name")),
                    ("service_type", self._ui("type")),
                    ("default_price", self._ui("price")),
                    ("is_active", self._ui("active")),
                ],
            )

        self._run_api(action)

    def refresh_warehouse(self) -> None:
        """Refresh warehouse balances and movement log."""

        def action() -> None:
            warehouses = self._api_list("get_warehouses")
            self._populate_table(
                self.warehouses_table,
                warehouses,
                [
                    ("id", "ID"),
                    ("code", self._ui("code")),
                    ("name", self._ui("name")),
                    ("location", self._humanize_key("location")),
                    ("is_active", self._ui("active")),
                ],
            )
            balances = self.api_client.get_stock_balances()
            self._populate_table(
                self.warehouse_table,
                balances,
                [
                    ("id", self.translator.text("warehouse.table.id")),
                    (
                        lambda row: (
                            row.get("warehouse_name") or row.get("warehouse_code")
                        ),
                        self.translator.text("warehouse.table.warehouse"),
                    ),
                    (
                        lambda row: row.get("product_name") or row.get("product_sku"),
                        self.translator.text("warehouse.table.product"),
                    ),
                    ("quantity", self.translator.text("warehouse.table.quantity")),
                    ("avg_cost_tmt", self.translator.text("warehouse.table.avg_cost")),
                ],
            )
            movements = self.api_client.get_stock_movements()
            self.warehouse_movements_text.setPlainText(
                json.dumps(movements, indent=2, ensure_ascii=False)
            )
            self._populate_table(
                self.warehouse_movements_table,
                movements,
                [
                    ("movement_date", self._ui("date")),
                    ("warehouse_name", self._ui("warehouse")),
                    ("product_name", self._ui("product")),
                    ("movement_type", self._ui("type")),
                    (
                        lambda row: (
                            f"{row.get('document_type') or '-'} #{row.get('document_id') or '-'}"
                        ),
                        self._ui("document"),
                    ),
                    ("quantity", self._ui("quantity_short")),
                    ("unit_cost_tmt", self._ui("unit_cost")),
                    ("amount_tmt", self._ui("amount")),
                ],
            )
            inventories = self._api_list("get_inventories")
            self._populate_table(
                self.inventories_table,
                inventories,
                [
                    ("id", "ID"),
                    ("warehouse_name", self._ui("warehouse")),
                    ("status", self._ui("status")),
                    ("note", self._ui("note")),
                    ("posted_at", self._humanize_key("posted_at")),
                    (lambda row: len(row.get("lines") or []), self._ui("items")),
                ],
            )
            transfers = self._api_list("get_stock_transfers")
            self._populate_table(
                self.stock_transfers_table,
                transfers,
                [
                    ("id", "ID"),
                    (
                        "source_warehouse_name",
                        self._humanize_key("source_warehouse_id"),
                    ),
                    (
                        "target_warehouse_name",
                        self._humanize_key("target_warehouse_id"),
                    ),
                    ("status", self._ui("status")),
                    ("sent_at", self._humanize_key("sent_at")),
                    (lambda row: len(row.get("lines") or []), self._ui("items")),
                ],
            )
            writeoffs = self._api_list("get_stock_writeoffs")
            self._populate_table(
                self.stock_writeoffs_table,
                writeoffs,
                [
                    ("id", "ID"),
                    ("warehouse_name", self._ui("warehouse")),
                    ("reason_code", self._humanize_key("reason_code")),
                    ("status", self._ui("status")),
                    ("posted_at", self._humanize_key("posted_at")),
                    (lambda row: len(row.get("lines") or []), self._ui("items")),
                ],
            )

        self._run_api(action)

    def refresh_counterparties(self) -> None:
        """Refresh counterparties table with debt balances."""

        def action() -> None:
            rows = self.api_client.get_counterparties(
                self.counterparty_search.text().strip() or None, include_debt=True
            )
            self._populate_table(
                self.counterparties_table,
                rows,
                [
                    ("id", self.translator.text("counterparties.table.id")),
                    ("code", self.translator.text("counterparties.table.code")),
                    ("name", self.translator.text("counterparties.table.name")),
                    ("role_flags", self.translator.text("counterparties.table.role")),
                    (
                        lambda row: (
                            f"R {(row.get('debt') or {}).get('receivable', '0.00')} / P {(row.get('debt') or {}).get('payable', '0.00')}"
                        ),
                        self.translator.text("counterparties.table.debt"),
                    ),
                ],
            )

        self._run_api(action)

    def refresh_pricing(self) -> None:
        """Refresh price-list table."""

        def action() -> None:
            rows = self.api_client.get_price_lists()
            self._populate_table(
                self.pricing_table,
                rows,
                [
                    ("id", self.translator.text("pricing.table.id")),
                    ("name_ru", self.translator.text("pricing.table.name")),
                    (
                        lambda row: row.get("currency_code") or row.get("currency_id"),
                        self.translator.text("pricing.table.currency"),
                    ),
                    ("is_default", self.translator.text("pricing.table.default")),
                ],
            )
            items: list[ApiRow] = []
            for price_list in rows:
                price_list_id = price_list.get("id")
                if price_list_id is None:
                    continue
                for item in self._api_list("get_price_list_items", int(price_list_id)):
                    item["price_list_name_ru"] = price_list.get("name_ru")
                    items.append(item)
            self._populate_table(
                self.price_items_table,
                items,
                [
                    ("id", "ID"),
                    ("price_list_name_ru", self._humanize_key("price_list_id")),
                    (
                        lambda row: (
                            row.get("product_name") or row.get("service_name_ru")
                        ),
                        self._ui("product"),
                    ),
                    ("price_tmt", self._ui("price")),
                    ("valid_from", self._humanize_key("valid_from")),
                    ("valid_to", self._humanize_key("valid_to")),
                    ("uom_code", self._humanize_key("uom_id")),
                ],
            )

        self._run_api(action)

    def refresh_purchase(self) -> None:
        """Refresh purchase invoices and payable ledger."""

        def action() -> None:
            orders = self._api_list("get_purchase_orders")
            self._populate_table(
                self.purchase_orders_table,
                orders,
                [
                    ("id", self.translator.text("purchase.table.id")),
                    ("doc_number", self.translator.text("purchase.table.number")),
                    (
                        "counterparty_name",
                        self.translator.text("purchase.table.supplier"),
                    ),
                    ("total_amount_tmt", self.translator.text("purchase.table.total")),
                    ("status", self.translator.text("purchase.table.status")),
                    (lambda row: "-", self.translator.text("purchase.table.payment")),
                ],
            )
            invoices = self.api_client.get_purchase_invoices()
            self._populate_table(
                self.purchase_table,
                invoices,
                [
                    ("id", self.translator.text("purchase.table.id")),
                    ("doc_number", self.translator.text("purchase.table.number")),
                    (
                        "counterparty_name",
                        self.translator.text("purchase.table.supplier"),
                    ),
                    ("total_amount_tmt", self.translator.text("purchase.table.total")),
                    ("status", self.translator.text("purchase.table.status")),
                    ("payment_status", self.translator.text("purchase.table.payment")),
                ],
            )
            ledger = self.api_client.get_debt_ledger(debt_type="payable")
            self.purchase_debt_text.setPlainText(
                json.dumps(ledger, indent=2, ensure_ascii=False)
            )
            self._render_debt_ledger(
                ledger,
                self.purchase_debt_table,
                self.purchase_debt_metrics_layout,
                title=self._ui("payable_entries"),
            )

        self._run_api(action)

    def refresh_sales(self) -> None:
        """Refresh sales and receivable ledger."""

        def action() -> None:
            rows = self.api_client.get_sales()
            self._populate_table(
                self.sales_table,
                rows,
                [
                    ("id", self.translator.text("sales.table.id")),
                    ("doc_number", self.translator.text("sales.table.number")),
                    ("sale_type", self.translator.text("sales.table.type")),
                    ("counterparty_name", self.translator.text("sales.table.customer")),
                    ("total_amount_tmt", self.translator.text("sales.table.total")),
                    ("status", self.translator.text("sales.table.status")),
                    ("payment_type", self.translator.text("sales.table.payment")),
                ],
            )
            returns = self._api_list("get_sale_returns")
            self._populate_table(
                self.sale_returns_table,
                returns,
                [
                    ("id", self.translator.text("sales.table.id")),
                    ("doc_number", self.translator.text("sales.table.number")),
                    (lambda row: "return", self.translator.text("sales.table.type")),
                    ("counterparty_name", self.translator.text("sales.table.customer")),
                    ("total_amount_tmt", self.translator.text("sales.table.total")),
                    ("status", self.translator.text("sales.table.status")),
                    ("refund_method", self.translator.text("sales.table.payment")),
                ],
            )
            ledger = self.api_client.get_debt_ledger(debt_type="receivable")
            self.sales_debt_text.setPlainText(
                json.dumps(ledger, indent=2, ensure_ascii=False)
            )
            self._render_debt_ledger(
                ledger,
                self.sales_debt_table,
                self.sales_debt_metrics_layout,
                title=self._ui("receivable_entries"),
            )

        self._run_api(action)

    def refresh_cashier(self) -> None:
        """Refresh cashier shifts and cash-flow snapshot."""

        def action() -> None:
            registers = self._api_list("get_cash_registers")
            self._populate_table(
                self.cash_registers_table,
                registers,
                [
                    ("id", "ID"),
                    ("name", self._ui("name")),
                    ("warehouse_name", self._ui("warehouse")),
                    ("warehouse_id", self._humanize_key("warehouse_id")),
                    ("is_active", self._ui("active")),
                ],
            )
            rows = self.api_client.get_cash_shifts()
            self._populate_table(
                self.cashier_table,
                rows,
                [
                    ("id", self.translator.text("cashier.table.id")),
                    (
                        lambda row: (
                            row.get("cash_register_name") or row.get("cash_register_id")
                        ),
                        self.translator.text("cashier.table.register"),
                    ),
                    ("opened_at", self.translator.text("cashier.table.opened_at")),
                    ("opening_amount", self.translator.text("cashier.table.opening")),
                    ("closing_amount", self.translator.text("cashier.table.closing")),
                    ("status", self.translator.text("cashier.table.status")),
                ],
            )
            report = self.api_client.get_cash_flow_report()
            self.cashier_text.setPlainText(
                json.dumps(report, indent=2, ensure_ascii=False)
            )
            self._render_cash_report(report)

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
            payload = {
                "report_code": code,
                "filters": filters,
                "saved_filters": saved_filters,
                "report": report,
            }
            self.reports_text.setPlainText(
                json.dumps(
                    payload,
                    indent=2,
                    ensure_ascii=False,
                )
            )
            self._render_report_view(
                code=code, filters=filters, saved_filters=saved_filters, report=report
            )

        self._run_api(action)

    def export_current_report(self) -> None:
        """Export the selected report and show the export payload metadata."""

        def action() -> None:
            code = self._selected_report_code()
            payload = self.api_client.export_report(
                code, self._current_report_filters()
            )
            self.reports_text.setPlainText(
                json.dumps(payload, indent=2, ensure_ascii=False)
            )
            filename = payload.get("filename") or self.translator.text("reports.export")
            self._render_report_result(
                payload, title=f"{self._ui('export_ready')}: {filename}"
            )

        self._run_api(action)

    def save_current_report_filter(self) -> None:
        """Save the current report filters as a server-side preset."""

        name = self.report_filter_name.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                self.translator.text("common.error"),
                self.translator.text("reports.filter_name"),
            )
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
            self.reports_text.setPlainText(
                json.dumps(payload, indent=2, ensure_ascii=False)
            )
            self._render_report_result(
                payload,
                title=f"{self._ui('filter_saved')}: {payload.get('name', name)}",
            )

        self._run_api(action)

    def _default_currency_id(self) -> int:
        """Return the seeded TMT currency id, or the first available currency id."""

        currencies = self.api_client.get_currencies()
        for currency in currencies:
            if currency.get("code") == "TMT":
                return int(currency["id"])
        if not currencies:
            raise ValueError(self.translator.text("error.no_currencies"))
        return int(currencies[0]["id"])

    def _first_line(self, row: ApiRow) -> ApiRow:
        """Return the first related line from a document row."""

        lines = row.get("lines")
        if isinstance(lines, list) and lines and isinstance(lines[0], dict):
            return dict(lines[0])
        return {}

    def _toggle_active(
        self,
        row: ApiRow,
        updater: Callable[[int, ApiRow], ApiRow],
        refresh: Callable[[], object],
    ) -> None:
        """Toggle is_active for one master-data row."""

        target_active = not bool(row.get("is_active"))
        label = self.translator.text(
            "crud.activate" if target_active else "crud.deactivate"
        )
        if self._confirm_record_action(row, label):
            self._run_api(
                lambda: (
                    updater(int(row["id"]), {"is_active": target_active}),
                    refresh(),
                )
            )

    def _line_payload_from_flat(self, payload: ApiRow, *, sale: bool = False) -> ApiRow:
        """Extract a one-line document payload from a flat form payload."""

        keys = {
            "product_id",
            "service_id",
            "expense_category_id",
            "purchase_order_line_id",
            "product_uom_id",
            "uom_id",
            "quantity",
            "price_cur",
            "price_final",
            "discount_percent",
            "unit_cost_tmt",
        }
        line = {key: payload.pop(key) for key in list(payload) if key in keys}
        if sale:
            line.setdefault(
                "line_type",
                "product" if line.get("product_id") is not None else "service",
            )
            line.setdefault("price_list_price", line.get("price_final") or "0")
            line.setdefault("discount_amount", "0")
            line.setdefault("price_override", False)
        return line

    def _confirming_api_action(
        self,
        row: ApiRow,
        label_key: str,
        api_call: Callable[[], object],
        refresh: Callable[[], object],
    ) -> None:
        """Confirm, run an API call, and refresh the relevant page."""

        label = self.translator.text(label_key)
        if not self._confirm_record_action(row, label):
            return

        def action() -> None:
            api_call()
            refresh()

        self._run_api(action)

    def create_role_dialog(self) -> None:
        """Create a custom role."""

        payload = self._simple_record_form(
            self.translator.text("roles.create"),
            [
                ("name", self._ui("name"), ""),
                ("description", self._ui("description"), ""),
                ("permissions", self._ui("permissions"), ""),
            ],
        )
        if payload is None:
            return
        permissions = [
            part.strip()
            for part in str(payload.pop("permissions", ""))
            .replace("\n", ",")
            .split(",")
            if part.strip()
        ]
        self._run_api(
            lambda: (
                self.api_client.create_role({**payload, "permissions": permissions}),
                self.refresh_roles(),
            )
        )

    def edit_role_dialog(self, row: ApiRow) -> None:
        """Edit a role description and permissions."""

        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                ("description", self._ui("description"), row.get("description")),
                (
                    "permissions",
                    self._ui("permissions"),
                    ", ".join(str(item) for item in row.get("permissions") or []),
                ),
            ],
        )
        if payload is None:
            return
        permissions = [
            part.strip()
            for part in str(payload.pop("permissions", ""))
            .replace("\n", ",")
            .split(",")
            if part.strip()
        ]
        self._run_api(
            lambda: (
                self.api_client.update_role(
                    int(row["id"]), {**payload, "permissions": permissions}
                ),
                self.refresh_roles(),
            )
        )

    def delete_role_action(self, row: ApiRow) -> None:
        """Delete an unused custom role."""

        label = self.translator.text("crud.delete")
        if self._confirm_record_action(row, label, hard_delete=True):
            self._run_api(
                lambda: (
                    self.api_client.delete_role(int(row["id"])),
                    self.refresh_roles(),
                )
            )

    def edit_product_dialog(self, row: ApiRow) -> None:
        """Edit a product."""

        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                (
                    "name",
                    self.translator.text("catalog.form.name_ru"),
                    row.get("name") or row.get("name_ru"),
                ),
                (
                    "name_tk",
                    self.translator.text("catalog.form.name_tk"),
                    row.get("name_tk"),
                ),
                ("unit", self._humanize_key("unit"), row.get("unit")),
                (
                    "retail_price",
                    self.translator.text("catalog.form.price"),
                    row.get("retail_price"),
                ),
                (
                    "last_known_cost",
                    self._humanize_key("last_known_cost"),
                    row.get("last_known_cost"),
                ),
                ("min_stock", self._humanize_key("min_stock"), row.get("min_stock")),
                (
                    "description",
                    self._humanize_key("description"),
                    row.get("description"),
                ),
                ("is_active", self._ui("active"), row.get("is_active")),
            ],
        )
        if payload is not None:
            self._run_api(
                lambda: (
                    self.api_client.update_product(int(row["id"]), payload),
                    self.refresh_catalog(),
                )
            )

    def toggle_product_active_action(self, row: ApiRow) -> None:
        self._toggle_active(row, self.api_client.update_product, self.refresh_catalog)

    def edit_product_group_dialog(self, row: ApiRow) -> None:
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                (
                    "name_ru",
                    self.translator.text("catalog.form.name_ru"),
                    row.get("name_ru"),
                ),
                (
                    "name_tk",
                    self.translator.text("catalog.form.name_tk"),
                    row.get("name_tk"),
                ),
                ("parent_id", self._humanize_key("parent_id"), row.get("parent_id")),
                ("sort_order", self._humanize_key("sort_order"), row.get("sort_order")),
                ("is_active", self._ui("active"), row.get("is_active")),
            ],
        )
        if payload is not None:
            self._run_api(
                lambda: (
                    self.api_client.update_product_group(int(row["id"]), payload),
                    self.refresh_catalog(),
                )
            )

    def toggle_product_group_active_action(self, row: ApiRow) -> None:
        self._toggle_active(
            row, self.api_client.update_product_group, self.refresh_catalog
        )

    def edit_service_dialog(self, row: ApiRow) -> None:
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                (
                    "name_ru",
                    self.translator.text("catalog.form.name_ru"),
                    row.get("name_ru"),
                ),
                (
                    "name_tk",
                    self.translator.text("catalog.form.name_tk"),
                    row.get("name_tk"),
                ),
                ("service_type", self._ui("type"), row.get("service_type")),
                (
                    "expense_category_id",
                    self._humanize_key("expense_category_id"),
                    row.get("expense_category_id"),
                ),
                ("default_price", self._ui("price"), row.get("default_price")),
                ("is_active", self._ui("active"), row.get("is_active")),
            ],
        )
        if payload is not None:
            self._run_api(
                lambda: (
                    self.api_client.update_service(int(row["id"]), payload),
                    self.refresh_catalog(),
                )
            )

    def toggle_service_active_action(self, row: ApiRow) -> None:
        self._toggle_active(row, self.api_client.update_service, self.refresh_catalog)

    def edit_warehouse_dialog(self, row: ApiRow) -> None:
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                ("name", self.translator.text("warehouse.form.name"), row.get("name")),
                (
                    "location",
                    self.translator.text("warehouse.form.location"),
                    row.get("location"),
                ),
                ("is_active", self._ui("active"), row.get("is_active")),
            ],
        )
        if payload is not None:
            self._run_api(
                lambda: (
                    self.api_client.update_warehouse(int(row["id"]), payload),
                    self.refresh_warehouse(),
                )
            )

    def toggle_warehouse_active_action(self, row: ApiRow) -> None:
        self._toggle_active(
            row, self.api_client.update_warehouse, self.refresh_warehouse
        )

    def edit_counterparty_dialog(self, row: ApiRow) -> None:
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                (
                    "name",
                    self.translator.text("counterparties.form.name"),
                    row.get("name"),
                ),
                (
                    "role_flags",
                    self.translator.text("counterparties.form.role"),
                    row.get("role_flags"),
                ),
                ("counterparty_type", self._ui("type"), row.get("counterparty_type")),
                (
                    "phone",
                    self.translator.text("counterparties.form.phone"),
                    row.get("phone"),
                ),
                ("email", self._humanize_key("email"), row.get("email")),
                ("tax_id", self._humanize_key("tax_id"), row.get("tax_id")),
                (
                    "address",
                    self.translator.text("counterparties.form.address"),
                    row.get("address"),
                ),
                (
                    "price_list_id",
                    self._humanize_key("price_list_id"),
                    row.get("price_list_id"),
                ),
                (
                    "discount_percent",
                    self._humanize_key("discount_percent"),
                    row.get("discount_percent"),
                ),
                (
                    "credit_limit_tmt",
                    self._humanize_key("credit_limit_tmt"),
                    row.get("credit_limit_tmt"),
                ),
                ("note", self._ui("note"), row.get("note")),
                ("is_active", self._ui("active"), row.get("is_active")),
            ],
        )
        if payload is not None:
            self._run_api(
                lambda: (
                    self.api_client.update_counterparty(int(row["id"]), payload),
                    self.refresh_counterparties(),
                )
            )

    def toggle_counterparty_active_action(self, row: ApiRow) -> None:
        self._toggle_active(
            row, self.api_client.update_counterparty, self.refresh_counterparties
        )

    def edit_price_list_dialog(self, row: ApiRow) -> None:
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                (
                    "name_ru",
                    self.translator.text("pricing.form.name"),
                    row.get("name_ru"),
                ),
                (
                    "name_tk",
                    self.translator.text("catalog.form.name_tk"),
                    row.get("name_tk"),
                ),
                (
                    "currency_id",
                    self.translator.text("pricing.form.currency_id"),
                    row.get("currency_id"),
                ),
                (
                    "is_default",
                    self.translator.text("pricing.table.default"),
                    row.get("is_default"),
                ),
                ("is_active", self._ui("active"), row.get("is_active")),
                ("note", self._ui("note"), row.get("note")),
            ],
        )
        if payload is not None:
            self._run_api(
                lambda: (
                    self.api_client.update_price_list(int(row["id"]), payload),
                    self.refresh_pricing(),
                )
            )

    def toggle_price_list_active_action(self, row: ApiRow) -> None:
        self._toggle_active(
            row, self.api_client.update_price_list, self.refresh_pricing
        )

    def edit_price_item_dialog(self, row: ApiRow) -> None:
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                (
                    "product_id",
                    self.translator.text("pricing.form.product_id"),
                    row.get("product_id"),
                ),
                ("service_id", self._humanize_key("service_id"), row.get("service_id")),
                ("uom_id", self._humanize_key("uom_id"), row.get("uom_id")),
                (
                    "price_tmt",
                    self.translator.text("pricing.form.price"),
                    row.get("price_tmt"),
                ),
                (
                    "valid_from",
                    self.translator.text("pricing.form.valid_from"),
                    row.get("valid_from"),
                ),
                ("valid_to", self._humanize_key("valid_to"), row.get("valid_to")),
            ],
        )
        if payload is not None:
            self._run_api(
                lambda: (
                    self.api_client.update_price_list_item(int(row["id"]), payload),
                    self.refresh_pricing(),
                )
            )

    def delete_price_item_action(self, row: ApiRow) -> None:
        label = self.translator.text("crud.delete")
        if self._confirm_record_action(row, label, hard_delete=True):
            self._run_api(
                lambda: (
                    self.api_client.delete_price_list_item(int(row["id"])),
                    self.refresh_pricing(),
                )
            )

    def edit_purchase_order_dialog(self, row: ApiRow) -> None:
        line = self._first_line(row)
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                ("doc_date", self._ui("date"), row.get("doc_date")),
                (
                    "counterparty_id",
                    self.translator.text("purchase.form.supplier_id"),
                    row.get("counterparty_id"),
                ),
                (
                    "warehouse_id",
                    self.translator.text("purchase.form.warehouse_id"),
                    row.get("warehouse_id"),
                ),
                (
                    "currency_id",
                    self.translator.text("purchase.form.currency_id"),
                    row.get("currency_id"),
                ),
                (
                    "currency_rate",
                    self._humanize_key("currency_rate"),
                    row.get("currency_rate"),
                ),
                ("note", self._ui("note"), row.get("note")),
                (
                    "product_id",
                    self.translator.text("purchase.form.product_id"),
                    line.get("product_id"),
                ),
                (
                    "service_id",
                    self._humanize_key("service_id"),
                    line.get("service_id"),
                ),
                (
                    "expense_category_id",
                    self._humanize_key("expense_category_id"),
                    line.get("expense_category_id"),
                ),
                (
                    "quantity",
                    self.translator.text("purchase.form.quantity"),
                    line.get("quantity_ordered"),
                ),
                (
                    "price_cur",
                    self.translator.text("purchase.form.price"),
                    line.get("price_cur"),
                ),
            ],
        )
        if payload is None:
            return
        line_payload = self._line_payload_from_flat(payload)
        update_payload = {**payload, "lines": [line_payload]}
        self._run_api(
            lambda: (
                self.api_client.update_purchase_order(int(row["id"]), update_payload),
                self.refresh_purchase(),
            )
        )

    def cancel_purchase_order_action(self, row: ApiRow) -> None:
        self._confirming_api_action(
            row,
            "crud.cancel",
            lambda: self.api_client.cancel_purchase_order(int(row["id"])),
            self.refresh_purchase,
        )

    def edit_purchase_invoice_dialog(self, row: ApiRow) -> None:
        line = self._first_line(row)
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                ("doc_number", self._ui("number"), row.get("doc_number")),
                ("doc_date", self._ui("date"), row.get("doc_date")),
                (
                    "counterparty_id",
                    self.translator.text("purchase.form.supplier_id"),
                    row.get("counterparty_id"),
                ),
                (
                    "warehouse_id",
                    self.translator.text("purchase.form.warehouse_id"),
                    row.get("warehouse_id"),
                ),
                (
                    "currency_id",
                    self.translator.text("purchase.form.currency_id"),
                    row.get("currency_id"),
                ),
                (
                    "currency_rate",
                    self._humanize_key("currency_rate"),
                    row.get("currency_rate"),
                ),
                (
                    "purchase_order_id",
                    self.translator.text("purchase.form.order_id"),
                    row.get("purchase_order_id"),
                ),
                (
                    "return_invoice_id",
                    self.translator.text("purchase.form.return_invoice_id"),
                    row.get("return_invoice_id"),
                ),
                (
                    "is_return",
                    self.translator.text("purchase.create_return"),
                    row.get("is_return"),
                ),
                ("note", self._ui("note"), row.get("note")),
                (
                    "product_id",
                    self.translator.text("purchase.form.product_id"),
                    line.get("product_id"),
                ),
                (
                    "service_id",
                    self._humanize_key("service_id"),
                    line.get("service_id"),
                ),
                (
                    "expense_category_id",
                    self._humanize_key("expense_category_id"),
                    line.get("expense_category_id"),
                ),
                (
                    "purchase_order_line_id",
                    self.translator.text("purchase.form.order_line_id"),
                    line.get("purchase_order_line_id"),
                ),
                (
                    "quantity",
                    self.translator.text("purchase.form.quantity"),
                    line.get("quantity"),
                ),
                (
                    "price_cur",
                    self.translator.text("purchase.form.price"),
                    line.get("price_cur"),
                ),
            ],
        )
        if payload is None:
            return
        line_payload = self._line_payload_from_flat(payload)
        update_payload = {**payload, "lines": [line_payload]}
        self._run_api(
            lambda: (
                self.api_client.update_purchase_invoice(int(row["id"]), update_payload),
                self.refresh_purchase(),
            )
        )

    def cancel_purchase_invoice_action(self, row: ApiRow) -> None:
        self._confirming_api_action(
            row,
            "crud.cancel",
            lambda: self.api_client.cancel_purchase_invoice(int(row["id"])),
            self.refresh_purchase,
        )

    def edit_inventory_dialog(self, row: ApiRow) -> None:
        line = self._first_line(row)
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                (
                    "product_id",
                    self.translator.text("warehouse.form.product_id"),
                    line.get("product_id"),
                ),
                (
                    "qty_actual",
                    self.translator.text("warehouse.form.quantity"),
                    line.get("qty_actual"),
                ),
                (
                    "unit_cost_tmt",
                    self.translator.text("warehouse.form.unit_cost"),
                    line.get("unit_cost_tmt"),
                ),
            ],
        )
        if payload is not None:
            self._run_api(
                lambda: (
                    self.api_client.replace_inventory_lines(int(row["id"]), [payload]),
                    self.refresh_warehouse(),
                )
            )

    def cancel_inventory_action(self, row: ApiRow) -> None:
        self._confirming_api_action(
            row,
            "crud.cancel",
            lambda: self.api_client.cancel_inventory(int(row["id"])),
            self.refresh_warehouse,
        )

    def edit_stock_transfer_dialog(self, row: ApiRow) -> None:
        line = self._first_line(row)
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                (
                    "source_warehouse_id",
                    self.translator.text("warehouse.form.source_warehouse_id"),
                    row.get("source_warehouse_id"),
                ),
                (
                    "target_warehouse_id",
                    self.translator.text("warehouse.form.target_warehouse_id"),
                    row.get("target_warehouse_id"),
                ),
                ("note", self._ui("note"), row.get("note")),
                (
                    "product_id",
                    self.translator.text("warehouse.form.product_id"),
                    line.get("product_id"),
                ),
                (
                    "quantity",
                    self.translator.text("warehouse.form.quantity"),
                    line.get("quantity"),
                ),
                (
                    "unit_cost_tmt",
                    self.translator.text("warehouse.form.unit_cost"),
                    line.get("unit_cost_tmt"),
                ),
            ],
        )
        if payload is None:
            return
        line_payload = self._line_payload_from_flat(payload)
        update_payload = {**payload, "lines": [line_payload]}
        self._run_api(
            lambda: (
                self.api_client.update_stock_transfer(int(row["id"]), update_payload),
                self.refresh_warehouse(),
            )
        )

    def reject_stock_transfer_action(self, row: ApiRow) -> None:
        self._confirming_api_action(
            row,
            "crud.cancel",
            lambda: self.api_client.reject_stock_transfer(int(row["id"])),
            self.refresh_warehouse,
        )

    def edit_stock_writeoff_dialog(self, row: ApiRow) -> None:
        line = self._first_line(row)
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                (
                    "warehouse_id",
                    self.translator.text("warehouse.form.warehouse_id"),
                    row.get("warehouse_id"),
                ),
                (
                    "reason_code",
                    self.translator.text("warehouse.form.reason"),
                    row.get("reason_code"),
                ),
                ("note", self._ui("note"), row.get("note")),
                (
                    "product_id",
                    self.translator.text("warehouse.form.product_id"),
                    line.get("product_id"),
                ),
                (
                    "quantity",
                    self.translator.text("warehouse.form.quantity"),
                    line.get("quantity"),
                ),
                (
                    "unit_cost_tmt",
                    self.translator.text("warehouse.form.unit_cost"),
                    line.get("unit_cost_tmt"),
                ),
            ],
        )
        if payload is None:
            return
        line_payload = self._line_payload_from_flat(payload)
        update_payload = {**payload, "lines": [line_payload]}
        self._run_api(
            lambda: (
                self.api_client.update_stock_writeoff(int(row["id"]), update_payload),
                self.refresh_warehouse(),
            )
        )

    def cancel_stock_writeoff_action(self, row: ApiRow) -> None:
        self._confirming_api_action(
            row,
            "crud.cancel",
            lambda: self.api_client.cancel_stock_writeoff(int(row["id"])),
            self.refresh_warehouse,
        )

    def edit_cash_register_dialog(self, row: ApiRow) -> None:
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                (
                    "name",
                    self.translator.text("cashier.form.register_name"),
                    row.get("name"),
                ),
                (
                    "warehouse_id",
                    self.translator.text("cashier.form.warehouse_id"),
                    row.get("warehouse_id"),
                ),
                ("is_active", self._ui("active"), row.get("is_active")),
            ],
        )
        if payload is not None:
            self._run_api(
                lambda: (
                    self.api_client.update_cash_register(int(row["id"]), payload),
                    self.refresh_cashier(),
                )
            )

    def toggle_cash_register_active_action(self, row: ApiRow) -> None:
        self._toggle_active(
            row, self.api_client.update_cash_register, self.refresh_cashier
        )

    def close_cash_shift_action(self, row: ApiRow) -> None:
        payload = self._simple_record_form(
            self.translator.text("crud.close"),
            [
                (
                    "closing_amount",
                    self.translator.text("cashier.form.closing_amount"),
                    row.get("closing_amount") or row.get("opening_amount") or "0",
                )
            ],
        )
        if payload is not None:
            self._confirming_api_action(
                row,
                "crud.close",
                lambda: self.api_client.close_cash_shift(int(row["id"]), payload),
                self.refresh_cashier,
            )

    def edit_sale_dialog(self, row: ApiRow) -> None:
        line = self._first_line(row)
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                ("doc_number", self._ui("number"), row.get("doc_number")),
                ("doc_date", self._ui("date"), row.get("doc_date")),
                (
                    "sale_type",
                    self.translator.text("sales.table.type"),
                    row.get("sale_type"),
                ),
                (
                    "cash_register_id",
                    self.translator.text("sales.form.cash_register_id"),
                    row.get("cash_register_id"),
                ),
                (
                    "cash_shift_id",
                    self.translator.text("sales.form.cash_shift_id"),
                    row.get("cash_shift_id"),
                ),
                (
                    "counterparty_id",
                    self.translator.text("sales.form.customer_id"),
                    row.get("counterparty_id"),
                ),
                (
                    "warehouse_id",
                    self.translator.text("sales.form.warehouse_id"),
                    row.get("warehouse_id"),
                ),
                (
                    "currency_id",
                    self.translator.text("sales.form.currency_id"),
                    row.get("currency_id"),
                ),
                (
                    "payment_type",
                    self.translator.text("sales.form.payment_type"),
                    row.get("payment_type"),
                ),
                (
                    "paid_cash_tmt",
                    self.translator.text("sales.form.paid_cash"),
                    row.get("paid_cash_tmt"),
                ),
                (
                    "paid_transfer_tmt",
                    self.translator.text("sales.form.paid_transfer"),
                    row.get("paid_transfer_tmt"),
                ),
                (
                    "debt_amount_tmt",
                    self.translator.text("sales.form.debt_amount"),
                    row.get("debt_amount_tmt"),
                ),
                (
                    "product_id",
                    self.translator.text("sales.form.product_id"),
                    line.get("product_id"),
                ),
                (
                    "service_id",
                    self._humanize_key("service_id"),
                    line.get("service_id"),
                ),
                (
                    "quantity",
                    self.translator.text("sales.form.quantity"),
                    line.get("quantity"),
                ),
                (
                    "price_final",
                    self.translator.text("sales.form.price"),
                    line.get("price_final"),
                ),
                (
                    "discount_percent",
                    self._humanize_key("discount_percent"),
                    line.get("discount_percent"),
                ),
            ],
        )
        if payload is None:
            return
        line_payload = self._line_payload_from_flat(payload, sale=True)
        payload.setdefault("currency_rate", row.get("currency_rate") or "1")
        payload.setdefault("discount_percent", row.get("discount_percent") or "0")
        payload.setdefault("discount_amount_tmt", row.get("discount_amount_tmt") or "0")
        payload["lines"] = [line_payload]
        self._run_api(
            lambda: (
                self.api_client.update_sale(int(row["id"]), payload),
                self.refresh_sales(),
            )
        )

    def cancel_sale_action(self, row: ApiRow) -> None:
        self._confirming_api_action(
            row,
            "crud.cancel",
            lambda: self.api_client.cancel_sale(int(row["id"])),
            self.refresh_sales,
        )

    def edit_sale_return_dialog(self, row: ApiRow) -> None:
        line = self._first_line(row)
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                ("doc_number", self._ui("number"), row.get("doc_number")),
                ("doc_date", self._ui("date"), row.get("doc_date")),
                (
                    "sale_id",
                    self.translator.text("sales.form.sale_id"),
                    row.get("sale_id"),
                ),
                (
                    "cash_register_id",
                    self.translator.text("sales.form.cash_register_id"),
                    row.get("cash_register_id"),
                ),
                (
                    "cash_shift_id",
                    self.translator.text("sales.form.cash_shift_id"),
                    row.get("cash_shift_id"),
                ),
                (
                    "refund_method",
                    self.translator.text("sales.form.refund_method"),
                    row.get("refund_method"),
                ),
                (
                    "refund_cash_tmt",
                    self.translator.text("sales.form.refund_cash"),
                    row.get("refund_cash_tmt"),
                ),
                (
                    "refund_transfer_tmt",
                    self.translator.text("sales.form.refund_transfer"),
                    row.get("refund_transfer_tmt"),
                ),
                (
                    "receivable_correction_tmt",
                    self.translator.text("sales.form.receivable_correction"),
                    row.get("receivable_correction_tmt"),
                ),
                (
                    "source_sale_line_id",
                    self.translator.text("sales.form.sale_line_id"),
                    line.get("source_sale_line_id"),
                ),
                (
                    "quantity",
                    self.translator.text("sales.form.quantity"),
                    line.get("quantity"),
                ),
                (
                    "price_final",
                    self.translator.text("sales.form.price"),
                    line.get("price_final"),
                ),
            ],
        )
        if payload is None:
            return
        try:
            source_sale_line_id = int(payload.pop("source_sale_line_id"))
        except (TypeError, ValueError):
            QMessageBox.critical(
                self,
                self.translator.text("common.error"),
                self.translator.text("sales.form.sale_line_id"),
            )
            return
        line_payload = {
            "source_sale_line_id": source_sale_line_id,
            "quantity": payload.pop("quantity"),
            "price_final": payload.pop("price_final"),
        }
        payload["lines"] = [line_payload]
        self._run_api(
            lambda: (
                self.api_client.update_sale_return(int(row["id"]), payload),
                self.refresh_sales(),
            )
        )

    def cancel_sale_return_action(self, row: ApiRow) -> None:
        self._confirming_api_action(
            row,
            "crud.cancel",
            lambda: self.api_client.cancel_sale_return(int(row["id"])),
            self.refresh_sales,
        )

    def edit_report_filter_dialog(self, row: ApiRow) -> None:
        payload = self._simple_record_form(
            self.translator.text("crud.edit"),
            [
                ("name", self._ui("name"), row.get("name")),
                (
                    "filters",
                    self._ui("filters"),
                    json.dumps(row.get("filters") or {}, ensure_ascii=False),
                ),
                ("is_shared", self._ui("shared"), row.get("is_shared")),
            ],
        )
        if payload is None:
            return
        try:
            payload["filters"] = json.loads(str(payload["filters"] or "{}"))
        except json.JSONDecodeError as exc:
            QMessageBox.critical(self, self.translator.text("common.error"), str(exc))
            return
        self._run_api(
            lambda: (
                self.api_client.update_report_filter(int(row["id"]), payload),
                self.refresh_reports(),
            )
        )

    def delete_report_filter_action(self, row: ApiRow) -> None:
        label = self.translator.text("crud.delete")
        if self._confirm_record_action(row, label, hard_delete=True):
            self._run_api(
                lambda: (
                    self.api_client.delete_report_filter(int(row["id"])),
                    self.refresh_reports(),
                )
            )

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
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            product = self.api_client.find_product_by_barcode(barcode.text().strip())
            self._show_product_result_dialog(product)

        self._run_api(action)

    def _show_product_result_dialog(self, product: ApiRow) -> None:
        """Show barcode lookup results as a friendly details dialog."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("catalog.find_barcode"))
        dialog.setMinimumSize(520, 360)
        layout = QVBoxLayout(dialog)
        header = QLabel(
            product.get("name")
            or product.get("name_ru")
            or product.get("sku")
            or self.translator.text("catalog.find_barcode")
        )
        header.setObjectName("PageTitle")
        layout.addWidget(header)
        summary, summary_layout = self._metric_area()
        self._render_metric_cards(
            summary_layout,
            [
                (self._ui("sku"), product.get("sku") or product.get("code")),
                (
                    self._ui("retail_price"),
                    product.get("retail_price") or product.get("default_price"),
                ),
                (self._ui("active"), product.get("is_active")),
            ],
        )
        layout.addWidget(summary)
        rows = [
            {"field": self._humanize_key(key), "value": value}
            for key, value in product.items()
            if key != "barcodes"
        ]
        table = QTableWidget(0, 2)
        self._configure_table(table)
        self._populate_table(
            table, rows, [("field", self._ui("field")), ("value", self._ui("value"))]
        )
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

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
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
                    "counterparty_type": "supplier"
                    if role_flags == 1
                    else "both"
                    if role_flags == 3
                    else "customer",
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
        self._add_selector_row(
            form, "pricing.form.currency_id", currency_id, self._select_currency_id
        )
        form.addRow(self.translator.text("pricing.table.default"), is_default)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            selected_currency_id = int(
                currency_id.text().strip() or self._default_currency_id()
            )
            self.api_client.create_price_list(
                {
                    "name_ru": name.text().strip(),
                    "currency_id": selected_currency_id,
                    "is_default": is_default.text().strip().lower()
                    in {"1", "true", "yes", "да"},
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
        self._add_selector_row(
            form,
            "pricing.form.price_list_id",
            price_list_id,
            self._select_price_list_id,
        )
        self._add_selector_row(
            form,
            "pricing.form.product_id",
            product_id,
            lambda field: self._select_product_id(field, price_target=product_price),
        )
        for key, widget in (
            ("pricing.form.price", product_price),
            ("pricing.form.valid_from", valid_from),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
        self._add_selector_row(
            form, "purchase.form.supplier_id", supplier_id, self._select_counterparty_id
        )
        self._add_selector_row(
            form, "purchase.form.warehouse_id", warehouse_id, self._select_warehouse_id
        )
        self._add_selector_row(
            form, "purchase.form.currency_id", currency_id, self._select_currency_id
        )
        self._add_selector_row(
            form,
            "purchase.form.product_id",
            product_id,
            lambda field: self._select_product_id(field, price_target=purchase_price),
        )
        for key, widget in (
            ("purchase.form.quantity", quantity),
            ("purchase.form.price", purchase_price),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
                    "currency_id": int(
                        currency_id.text().strip() or self._default_currency_id()
                    ),
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
        self._add_selector_row(
            form, "purchase.form.supplier_id", supplier_id, self._select_counterparty_id
        )
        self._add_selector_row(
            form, "purchase.form.warehouse_id", warehouse_id, self._select_warehouse_id
        )
        self._add_selector_row(
            form, "purchase.form.currency_id", currency_id, self._select_currency_id
        )
        self._add_selector_row(
            form,
            "purchase.form.product_id",
            product_id,
            lambda field: self._select_product_id(field, price_target=purchase_price),
        )
        for key, widget in (
            ("purchase.form.quantity", quantity),
            ("purchase.form.price", purchase_price),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
                    "currency_id": int(
                        currency_id.text().strip() or self._default_currency_id()
                    ),
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
        self._add_selector_row(
            form, "purchase.form.supplier_id", supplier_id, self._select_counterparty_id
        )
        self._add_selector_row(
            form, "purchase.form.warehouse_id", warehouse_id, self._select_warehouse_id
        )
        self._add_selector_row(
            form, "purchase.form.currency_id", currency_id, self._select_currency_id
        )
        self._add_selector_row(
            form,
            "purchase.form.return_invoice_id",
            source_invoice_id,
            self._select_purchase_invoice_id,
        )
        self._add_selector_row(
            form, "purchase.form.order_id", order_id, self._select_purchase_order_id
        )
        self._add_selector_row(
            form,
            "purchase.form.order_line_id",
            order_line_id,
            lambda field: self._select_purchase_order_line_id(field, order_id),
        )
        self._add_selector_row(
            form,
            "purchase.form.product_id",
            product_id,
            lambda field: self._select_product_id(field, price_target=purchase_price),
        )
        for key, widget in (
            ("purchase.form.quantity", quantity),
            ("purchase.form.price", purchase_price),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def optional_int(widget: QLineEdit) -> int | None:
            text = widget.text().strip()
            return int(text) if text else None

        def action() -> None:
            line: ApiRow = {
                "product_id": int(product_id.text().strip()),
                "quantity": quantity.text().strip() or "1",
                "price_cur": purchase_price.text().strip() or "0",
            }
            order_line = optional_int(order_line_id)
            if order_line is not None:
                line["purchase_order_line_id"] = order_line
            payload: ApiRow = {
                "counterparty_id": int(supplier_id.text().strip()),
                "warehouse_id": int(warehouse_id.text().strip()),
                "currency_id": int(
                    currency_id.text().strip() or self._default_currency_id()
                ),
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
        self._add_selector_row(
            form, "purchase.form.supplier_id", supplier_id, self._select_counterparty_id
        )
        self._add_selector_row(
            form,
            "purchase.form.invoice_id",
            invoice_id,
            self._select_purchase_invoice_id,
        )
        form.addRow(self.translator.text("purchase.form.payment_amount"), amount)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
        self._add_selector_row(
            form,
            "sales.form.cash_register_id",
            cash_register_id,
            self._select_cash_register_id,
        )
        self._add_selector_row(
            form, "sales.form.cash_shift_id", cash_shift_id, self._select_cash_shift_id
        )
        self._add_selector_row(
            form, "sales.form.customer_id", customer_id, self._select_counterparty_id
        )
        self._add_selector_row(
            form, "sales.form.warehouse_id", warehouse_id, self._select_warehouse_id
        )
        self._add_selector_row(
            form, "sales.form.currency_id", currency_id, self._select_currency_id
        )
        self._add_selector_row(
            form,
            "sales.form.product_id",
            product_id,
            lambda field: self._select_product_id(field, price_target=sale_price),
        )
        for key, widget in (
            ("sales.form.quantity", quantity),
            ("sales.form.price", sale_price),
            ("sales.form.payment_type", payment_type),
            ("sales.form.paid_cash", paid_cash),
            ("sales.form.paid_transfer", paid_transfer),
            ("sales.form.debt_amount", debt_amount),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
                    "currency_id": int(
                        currency_id.text().strip() or self._default_currency_id()
                    ),
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
        self._add_selector_row(
            form, "sales.form.sale_id", sale_id, self._select_sale_id
        )
        self._add_selector_row(
            form,
            "sales.form.sale_line_id",
            sale_line_id,
            lambda field: self._select_sale_line_id(field, sale_id),
        )
        self._add_selector_row(
            form,
            "sales.form.cash_register_id",
            cash_register_id,
            self._select_cash_register_id,
        )
        self._add_selector_row(
            form, "sales.form.cash_shift_id", cash_shift_id, self._select_cash_shift_id
        )
        for key, widget in (
            ("sales.form.quantity", quantity),
            ("sales.form.refund_method", refund_method),
            ("sales.form.refund_cash", refund_cash),
            ("sales.form.refund_transfer", refund_transfer),
            ("sales.form.receivable_correction", receivable_correction),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def optional_int(widget: QLineEdit) -> int | None:
            text = widget.text().strip()
            return int(text) if text else None

        def action() -> None:
            payload: ApiRow = {
                "sale_id": int(sale_id.text().strip()),
                "refund_method": refund_method.text().strip() or "debt_correction",
                "refund_cash_tmt": refund_cash.text().strip() or "0",
                "refund_transfer_tmt": refund_transfer.text().strip() or "0",
                "receivable_correction_tmt": receivable_correction.text().strip()
                or "0",
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
        self._add_selector_row(
            form, "sales.form.customer_id", customer_id, self._select_counterparty_id
        )
        self._add_selector_row(
            form, "sales.form.sale_id", sale_id, self._select_sale_id
        )
        self._add_selector_row(
            form, "sales.form.cash_shift_id", shift_id, self._select_cash_shift_id
        )
        form.addRow(self.translator.text("sales.form.paid_cash"), amount)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            sale_text = sale_id.text().strip()
            payload: ApiRow = {
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
        self._add_selector_row(
            form, "sales.form.sale_id", sale_id, self._select_sale_id
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
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
                self._cashier_set_product_inputs(
                    self.api_client.find_product_by_barcode(barcode)
                )
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
                raise ValueError(self.translator.text("cashier.error.cart_empty"))
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
                paid_cash = self._cashier_decimal_text(
                    self.cashier_paid_cash_input.text()
                )
                paid_transfer = self._cashier_decimal_text(
                    self.cashier_paid_transfer_input.text()
                )
                debt_amount = self._cashier_decimal_text(
                    self.cashier_debt_amount_input.text()
                )
                if (paid_cash + paid_transfer + debt_amount).quantize(
                    Decimal("0.01")
                ) != total:
                    raise ValueError(
                        self.translator.text("cashier.error.mixed_payment_total")
                    )
            customer_id = self._cashier_optional_int(self.cashier_customer_id_input)
            if debt_amount > Decimal("0.00") and customer_id is None:
                raise ValueError(
                    self.translator.text("cashier.error.customer_required")
                )
            cash_register_id = self._cashier_optional_int(
                self.cashier_register_id_input
            )
            cash_shift_id = self._cashier_optional_int(self.cashier_shift_id_input)
            warehouse_id = self._cashier_optional_int(self.cashier_warehouse_id_input)
            if warehouse_id is None:
                raise ValueError(
                    self.translator.text("cashier.error.warehouse_required")
                )
            currency_id = (
                self._cashier_optional_int(self.cashier_currency_id_input)
                or self._default_currency_id()
            )
            payload: ApiRow = {
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

        lines = [
            line
            for line in self.cashier_receipt_preview.toPlainText().splitlines()
            if line.strip()
        ]
        if not lines:
            lines = self._cashier_receipt_lines(None)
            self.cashier_receipt_preview.setPlainText("\n".join(lines))
        message = self.hardware.print_receipt(lines)
        self.cashier_text.appendPlainText(message)
        self.cashier_report_status.setText(message)

    def cashier_x_report(self) -> None:
        """Fetch and display the current shift X-report."""

        def action() -> None:
            shift_id = self._cashier_optional_int(self.cashier_shift_id_input)
            if shift_id is None:
                raise ValueError(self.translator.text("cashier.error.shift_required"))
            report = self.api_client.get_cash_shift_x_report(shift_id)
            self._show_cashier_report(report)

        self._run_api(action)

    def cashier_z_report(self) -> None:
        """Create and display a shift Z-report."""

        def action() -> None:
            shift_id = self._cashier_optional_int(self.cashier_shift_id_input)
            if shift_id is None:
                raise ValueError(self.translator.text("cashier.error.shift_required"))
            payload: ApiRow = {}
            closing_amount = self.cashier_closing_amount_input.text().strip()
            if closing_amount:
                payload["closing_amount"] = closing_amount
            report = self.api_client.create_cash_shift_z_report(shift_id, payload)
            self._show_cashier_report(report)
            self.refresh_cashier()

        self._run_api(action)

    def _show_cashier_report(self, report: ApiRow) -> None:
        """Render an X/Z report into the cashier text and receipt preview panes."""

        self.cashier_text.setPlainText(json.dumps(report, indent=2, ensure_ascii=False))
        title = f"{self._format_value(report.get('report_type'))} {self._ui('report_suffix')}"
        self._render_cash_report(report, title=title)
        self.cashier_receipt_preview.setPlainText(
            "\n".join(self._cashier_report_lines(report))
        )

    def _cashier_set_product_inputs(self, product: ApiRow) -> None:
        """Populate product entry fields from a catalog payload."""

        self.cashier_product_id_input.setText(str(product.get("id", "")))
        self.cashier_product_name_input.setText(
            str(
                product.get("name")
                or product.get("name_ru")
                or product.get("sku")
                or ""
            )
        )
        self.cashier_price_input.setText(str(product.get("retail_price") or "0"))

    def _cashier_cart_row_from_inputs(self) -> ApiRow:
        """Build one cart row from entry fields."""

        product_id = self._cashier_optional_int(self.cashier_product_id_input)
        if product_id is None:
            raise ValueError(self.translator.text("cashier.error.product_required"))
        quantity = self._cashier_decimal_text(
            self.cashier_quantity_input.text(), Decimal("1.0000")
        )
        price_final = self._cashier_decimal_text(self.cashier_price_input.text())
        discount_percent = self._cashier_decimal_text(
            self.cashier_discount_input.text()
        )
        if quantity <= Decimal("0.00"):
            raise ValueError(self.translator.text("cashier.error.quantity_positive"))
        if price_final < Decimal("0.00"):
            raise ValueError(self.translator.text("cashier.error.price_non_negative"))
        if discount_percent < Decimal("0.00") or discount_percent > Decimal("100.00"):
            raise ValueError(self.translator.text("cashier.error.discount_range"))
        return {
            "product_id": product_id,
            "product_name": self.cashier_product_name_input.text().strip()
            or f"{self._ui('product')} {product_id}",
            "quantity": quantity,
            "price_final": price_final,
            "discount_percent": discount_percent,
        }

    def _cashier_selected_row(self) -> int:
        """Return the selected cart row index."""

        row = self.cashier_cart_table.currentRow()
        if row < 0 or row >= len(self.cashier_cart):
            raise ValueError(self.translator.text("cashier.error.select_cart_row"))
        return row

    def _cashier_optional_int(self, widget: QLineEdit) -> int | None:
        """Parse an optional integer input."""

        text = widget.text().strip()
        return int(text) if text else None

    def _cashier_decimal_text(
        self, text: str, default: Decimal = Decimal("0.00")
    ) -> Decimal:
        """Parse a decimal input with a default for blank values."""

        value = text.strip()
        return Decimal(value) if value else default

    def _cashier_line_amount(self, item: ApiRow) -> Decimal:
        """Return one cart row amount after percentage discount."""

        quantity = Decimal(str(item["quantity"]))
        price_final = Decimal(str(item["price_final"]))
        discount_percent = Decimal(str(item["discount_percent"]))
        amount = (
            quantity
            * price_final
            * (Decimal("100.00") - discount_percent)
            / Decimal("100.00")
        )
        return amount.quantize(Decimal("0.01"))

    def _cashier_cart_total(self) -> Decimal:
        """Return the current cart total."""

        return sum(
            (self._cashier_line_amount(item) for item in self.cashier_cart),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))

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
                self.cashier_cart_table.setItem(row, col, self._table_item(value))
        self.cashier_total_label.setText(
            f"{self.translator.text('cashier.cart.total')}: {self._cashier_cart_total()} TMT"
        )

    def _cashier_receipt_lines(self, sale: ApiRow | None) -> list[str]:
        """Build receipt-preview lines for a posted sale or current cart."""

        lines = ["ERP Accounting", "Receipt"]
        if sale:
            lines.append(f"Sale: {sale.get('doc_number', sale.get('id', ''))}")
            sale_lines = sale.get("lines", [])
            if isinstance(sale_lines, list):
                for item in sale_lines:
                    if isinstance(item, dict):
                        name = (
                            item.get("product_name")
                            or item.get("service_name_ru")
                            or item.get("product_id")
                        )
                        lines.append(
                            f"{name} x {item.get('quantity')} = {item.get('amount_tmt')} TMT"
                        )
            lines.append(f"Total: {sale.get('total_amount_tmt', '0.00')} TMT")
            lines.append(f"Payment: {sale.get('payment_type', '')}")
            return lines
        for item in self.cashier_cart:
            lines.append(
                f"{item.get('product_name')} x {item.get('quantity')} = {self._cashier_line_amount(item)} TMT"
            )
        lines.append(f"Total: {self._cashier_cart_total()} TMT")
        return lines

    def _cashier_report_lines(self, report: ApiRow) -> list[str]:
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
        self._add_selector_row(
            form, "cashier.form.warehouse_id", warehouse_id, self._select_warehouse_id
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            self.api_client.create_cash_register(
                {
                    "name": name.text().strip(),
                    "warehouse_id": int(warehouse_id.text().strip()),
                }
            )
            self.refresh_cashier()

        self._run_api(action)

    def open_cash_shift_dialog(self) -> None:
        """Open a cash shift."""

        dialog = QDialog(self)
        dialog.setWindowTitle(self.translator.text("cashier.open_shift"))
        form = QFormLayout(dialog)
        register_id = QLineEdit()
        opening_amount = QLineEdit("0")
        self._add_selector_row(
            form, "cashier.form.register_id", register_id, self._select_cash_register_id
        )
        form.addRow(self.translator.text("cashier.form.opening_amount"), opening_amount)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
        self._add_selector_row(
            form, "cashier.form.shift_id", shift_id, self._select_cash_shift_id
        )
        form.addRow(self.translator.text("cashier.form.closing_amount"), closing_amount)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            self.api_client.close_cash_shift(
                int(shift_id.text().strip()),
                {"closing_amount": closing_amount.text().strip() or "0"},
            )
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
        self._add_selector_row(
            form, "cashier.form.shift_id", shift_id, self._select_cash_shift_id
        )
        self._add_selector_row(
            form, "cashier.form.register_id", register_id, self._select_cash_register_id
        )
        form.addRow(self.translator.text("cashier.form.operation_type"), operation_type)
        form.addRow(self.translator.text("cashier.form.amount"), amount)
        self._add_selector_row(
            form,
            "cashier.form.target_register_id",
            target_register_id,
            self._select_cash_register_id,
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def action() -> None:
            payload: ApiRow = {
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
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
        self._add_selector_row(
            form, "warehouse.form.warehouse_id", warehouse_id, self._select_warehouse_id
        )
        self._add_selector_row(
            form,
            "warehouse.form.product_id",
            product_id,
            lambda field: self._select_product_id(field, price_target=unit_cost),
        )
        for key, widget in (
            ("warehouse.form.quantity", qty_actual),
            ("warehouse.form.unit_cost", unit_cost),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
        self._add_selector_row(
            form,
            "warehouse.form.source_warehouse_id",
            source_warehouse_id,
            self._select_warehouse_id,
        )
        self._add_selector_row(
            form,
            "warehouse.form.target_warehouse_id",
            target_warehouse_id,
            self._select_warehouse_id,
        )
        self._add_selector_row(
            form, "warehouse.form.product_id", product_id, self._select_product_id
        )
        form.addRow(self.translator.text("warehouse.form.quantity"), quantity)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
        self._add_selector_row(
            form, "warehouse.form.warehouse_id", warehouse_id, self._select_warehouse_id
        )
        self._add_selector_row(
            form, "warehouse.form.product_id", product_id, self._select_product_id
        )
        for key, widget in (
            ("warehouse.form.quantity", quantity),
            ("warehouse.form.reason", reason),
        ):
            form.addRow(self.translator.text(key), widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
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
        """Refresh roles and optional permission metadata."""

        def action() -> None:
            selected_id = self.roles_selected_role_id
            roles = self.api_client.get_roles()
            self.roles_rows = [dict(role) for role in roles]
            permission_rows: list[ApiRow] = []
            permission_method = getattr(self.api_client, "get_permissions", None)
            if callable(permission_method):
                try:
                    result = permission_method()
                    if isinstance(result, list):
                        permission_rows = [
                            dict(permission)
                            for permission in result
                            if isinstance(permission, dict)
                        ]
                except Exception:
                    permission_rows = []
            self.roles_permission_catalog = {
                str(permission.get("code")): permission
                for permission in permission_rows
                if permission.get("code")
            }
            selection_was_removed = selected_id is not None and not any(
                str(role.get("id")) == str(selected_id)
                for role in self.roles_rows
            )
            if selection_was_removed:
                self.roles_selected_role_id = None
                self._close_role_permissions(
                    clear_selection=True, animate=False
                )
            self.roles_total_value.setText(str(len(self.roles_rows)))
            available_codes = set(self.roles_permission_catalog)
            if not available_codes:
                available_codes = {
                    str(code)
                    for role in self.roles_rows
                    for code in role.get("permissions") or []
                }
            self.roles_available_permissions_value.setText(
                str(len(available_codes))
            )
            self._apply_roles_filter()
            role = self._selected_role()
            if role is not None:
                self.roles_granted_permissions_value.setText(
                    str(len(role.get("permissions") or []))
                )
                self.roles_drawer_title.setText(str(role.get("name") or "-"))
                self.roles_drawer_description.setText(
                    str(
                        role.get("description")
                        or self.translator.text("roles.drawer.no_description")
                    )
                )
                permissions = [
                    str(code) for code in role.get("permissions") or []
                ]
                self.roles_drawer_count.setText(str(len(permissions)))
                self._populate_role_permission_module_filter(permissions)
                self._render_role_permission_cards()
            else:
                self.roles_granted_permissions_value.setText("0")

        self._run_api(action)

    def refresh_settings(self) -> None:
        """Refresh settings editor."""

        def action() -> None:
            settings = self.api_client.get_settings()
            self.settings_values = dict(settings)
            self.settings_text.setPlainText(
                json.dumps(settings, indent=2, ensure_ascii=False)
            )
            self._render_settings_forms(self.settings_values)

        self._run_api(action)

    def save_settings(self) -> None:
        """Save settings from editable form fields."""

        def action() -> None:
            values = json.loads(json.dumps(self.settings_values, ensure_ascii=False))
            for path, field in self.settings_fields.items():
                parsed = self._setting_value_from_text(
                    field.text(), self._settings_value_at_path(path)
                )
                if len(path) == 1:
                    values[path[0]] = parsed
                elif len(path) == 2:
                    parent = values.setdefault(path[0], {})
                    if isinstance(parent, dict):
                        parent[path[1]] = parsed
            updated = self.api_client.update_settings(values)
            self.settings_values = dict(updated)
            self.settings_text.setPlainText(
                json.dumps(updated, indent=2, ensure_ascii=False)
            )
            self._render_settings_forms(self.settings_values)
            QMessageBox.information(
                self,
                self.translator.text("common.success"),
                self.translator.text("common.success"),
            )

        self._run_api(action)

    def simulate_scan(self) -> None:
        """Run scanner simulator."""

        self.hardware_text.appendPlainText(
            f"{self.translator.text('hardware.log.scanner')}: {self.hardware.scan()}"
        )

    def simulate_print(self) -> None:
        """Run printer simulator."""

        self.hardware_text.appendPlainText(
            f"{self.translator.text('hardware.log.printer')}: {self.hardware.print_receipt()}"
        )

    def simulate_drawer(self) -> None:
        """Run cash drawer simulator."""

        self.hardware_text.appendPlainText(
            f"{self.translator.text('hardware.log.drawer')}: {self.hardware.open_drawer()}"
        )

    def simulate_scale(self) -> None:
        """Run scale simulator."""

        self.hardware_text.appendPlainText(
            f"{self.translator.text('hardware.log.scale')}: {self.hardware.read_weight()} kg"
        )

    def simulate_fiscal(self) -> None:
        """Run fiscal-device simulator."""

        self.hardware_text.appendPlainText(
            f"{self.translator.text('hardware.log.fiscal')}: {self.hardware.register_operation(Decimal('0.00'))}"
        )

    def _run_api(self, action: Callable[[], object]) -> None:
        """Run an API action and show a simple error dialog."""

        try:
            action()
        except (ApiClientError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, self.translator.text("common.error"), str(exc))

    def _set_catalog_table_headers(self) -> None:
        """Apply translated column headers to the catalog table."""

        self.catalog_table.setHorizontalHeaderLabels(
            [self.translator.text(key) for key in CATALOG_TABLE_HEADER_KEYS]
        )

    def _set_warehouse_table_headers(self) -> None:
        """Apply translated column headers to the warehouse table."""

        self.warehouse_table.setHorizontalHeaderLabels(
            [self.translator.text(key) for key in WAREHOUSE_TABLE_HEADER_KEYS]
        )

    def _set_counterparties_table_headers(self) -> None:
        """Apply translated column headers to the counterparties table."""

        self.counterparties_table.setHorizontalHeaderLabels(
            [self.translator.text(key) for key in COUNTERPARTY_TABLE_HEADER_KEYS]
        )

    def _set_pricing_table_headers(self) -> None:
        """Apply translated column headers to the pricing table."""

        self.pricing_table.setHorizontalHeaderLabels(
            [self.translator.text(key) for key in PRICING_TABLE_HEADER_KEYS]
        )

    def _set_purchase_table_headers(self) -> None:
        """Apply translated column headers to the purchase table."""

        self.purchase_table.setHorizontalHeaderLabels(
            [self.translator.text(key) for key in PURCHASE_TABLE_HEADER_KEYS]
        )

    def _set_sales_table_headers(self) -> None:
        """Apply translated column headers to the sales table."""

        self.sales_table.setHorizontalHeaderLabels(
            [self.translator.text(key) for key in SALES_TABLE_HEADER_KEYS]
        )

    def _set_cashier_table_headers(self) -> None:
        """Apply translated column headers to the cashier table."""

        self.cashier_table.setHorizontalHeaderLabels(
            [self.translator.text(key) for key in CASHIER_TABLE_HEADER_KEYS]
        )

    def _set_cashier_cart_table_headers(self) -> None:
        """Apply translated column headers to the cashier cart table."""

        self.cashier_cart_table.setHorizontalHeaderLabels(
            [self.translator.text(key) for key in CASHIER_CART_HEADER_KEYS]
        )

    def _set_roles_table_headers(self) -> None:
        """Apply translated column headers to the roles table."""

        if not hasattr(self, "roles_table"):
            return
        self.roles_table.setColumnCount(3)
        self.roles_table.setHorizontalHeaderLabels(
            [
                self._ui("role_id"),
                self._ui("role"),
                self._ui("description"),
            ]
        )
        self._configure_roles_table_columns()

    def _set_report_saved_filters_table_headers(self) -> None:
        """Apply translated column headers to the saved report filters table."""

        self.report_saved_filters_table.setHorizontalHeaderLabels(
            [
                self._ui("name"),
                self._ui("report"),
                self._ui("scope"),
                self._ui("updated"),
            ]
        )

    def _set_report_combo_labels(self) -> None:
        """Apply translated labels to report filter comboboxes."""

        if hasattr(self, "report_code"):
            for index in range(self.report_code.count()):
                code = str(self.report_code.itemData(index))
                self.report_code.setItemText(index, self._report_code_text(code))
        if hasattr(self, "report_debt_type"):
            for index in range(self.report_debt_type.count()):
                value = self.report_debt_type.itemData(index)
                self.report_debt_type.setItemText(
                    index, self._debt_type_text(str(value) if value else None)
                )

    def _set_tab_labels(self) -> None:
        """Apply translated labels to tab widgets."""

        tab_sets: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("catalog_tabs", ("tabs.products", "tabs.product_groups", "tabs.services")),
            (
                "warehouse_tabs",
                (
                    "tabs.warehouses",
                    "tabs.balances",
                    "tabs.movements",
                    "tabs.inventories",
                    "tabs.transfers",
                    "tabs.writeoffs",
                ),
            ),
            ("pricing_tabs", ("tabs.price_lists", "tabs.price_items")),
            ("purchase_tabs", ("tabs.orders", "tabs.invoices", "tabs.debt")),
            ("sales_tabs", ("tabs.sales", "tabs.returns", "tabs.debt")),
            ("cashier_tabs", ("tabs.registers", "tabs.shifts", "tabs.reports")),
            ("report_tabs", ("tabs.report_rows", "tabs.saved_filters")),
        )
        for attr, keys in tab_sets:
            tabs = getattr(self, attr, None)
            if not isinstance(tabs, QTabWidget):
                continue
            for index, key in enumerate(keys):
                if index < tabs.count():
                    tabs.setTabText(index, self.translator.text(key))

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
        if hasattr(self, "roles_table"):
            self._set_roles_table_headers()
        if hasattr(self, "report_saved_filters_table"):
            self._set_report_saved_filters_table_headers()
        self._set_tab_labels()
        self._set_report_combo_labels()
        if hasattr(self, "cashier_cart_table"):
            self._set_cashier_cart_table_headers()
            self._refresh_cashier_cart_table()
        if hasattr(self, "catalog_search"):
            self.catalog_search.setPlaceholderText(
                self.translator.text("catalog.search")
            )
        if hasattr(self, "counterparty_search"):
            self.counterparty_search.setPlaceholderText(
                self.translator.text("counterparties.search")
            )
        for line_edit in self.findChildren(QLineEdit):
            placeholder_key = line_edit.property("placeholderKey")
            if placeholder_key:
                line_edit.setPlaceholderText(self.translator.text(str(placeholder_key)))
        user = self.api_client.current_user
        user_text = f"{user.full_name} ({user.role_name})" if user else ""
        self.status_label.setText(
            f"{self.translator.text('main.connected')}: {user_text}"
        )
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
                if text_key == "users.back_to_list":
                    button.setText("←  " + self.translator.text(str(text_key)))
                else:
                    button.setText(self.translator.text(str(text_key)))
        for button in self.findChildren(QToolButton):
            text_key = button.property("textKey")
            if text_key:
                button.setText(self.translator.text(str(text_key)))
        if hasattr(self, "settings_values") and self.settings_values:
            self._render_settings_forms(self.settings_values)
        if hasattr(self, "users_role_filter"):
            self._populate_users_role_filter()
        if hasattr(self, "users_table") and hasattr(self, "users_rows"):
            self._apply_users_filters()
        if hasattr(self, "roles_table") and hasattr(self, "roles_rows"):
            self._render_roles_table()
        if hasattr(self, "roles_drawer_close"):
            self.roles_drawer_close.setToolTip(
                self.translator.text("roles.close_permissions")
            )
        selected_role = self._selected_role() if hasattr(
            self, "roles_selected_role_id"
        ) else None
        if selected_role is not None:
            permissions = [
                str(code) for code in selected_role.get("permissions") or []
            ]
            self._populate_role_permission_module_filter(permissions)
            self._render_role_permission_cards()
        if (
            hasattr(self, "users_stack")
            and self.users_stack.currentWidget()
            == getattr(self, "users_detail_page", None)
            and self.users_current_detail_row
        ):
            self._render_user_detail(self.users_current_detail_row)
        # Re-apply responsive layout adjustments after translations change
        try:
            self._update_users_responsive_layout()
        except Exception:
            pass
        self._update_roles_responsive_layout()

    def _build_users_page(self) -> QWidget:
        """Build the full-page Users workflow."""

        page, layout, _title = self._page("users.title")
        _title.hide()

        self.users_rows: list[ApiRow] = []
        self.users_filtered_rows: list[ApiRow] = []
        self.users_status_filter = "all"
        self.users_current_detail_row: ApiRow | None = None
        self.users_profile_card = None
        self.users_detail_container_layout = None
        self.users_stat_columns = 0
        self.users_page_size = 10
        self.users_current_page = 0

        self.users_stack = QStackedWidget()
        self.users_stack.setObjectName("UsersStack")

        self.users_list_page = self._build_users_list_page()
        self.users_detail_page, self.users_detail_layout = self._make_users_state_page()
        self.users_create_page, self.users_create_layout = self._make_users_state_page()
        self.users_edit_page, self.users_edit_layout = self._make_users_state_page()

        self.users_stack.addWidget(self.users_list_page)
        self.users_stack.addWidget(self.users_detail_page)
        self.users_stack.addWidget(self.users_create_page)
        self.users_stack.addWidget(self.users_edit_page)
        layout.addWidget(self.users_stack, 1)
        self._update_users_responsive_layout()
        return page

    def _make_users_state_page(self) -> tuple[QWidget, QVBoxLayout]:
        """Create one page for the Users internal stack."""

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        return page, layout

    def _build_users_list_page(self) -> QWidget:
        """Create the responsive Users list surface."""

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(14)

        toolbar = QFrame()
        toolbar.setObjectName("UsersToolbar")
        self.users_toolbar_grid = QGridLayout(toolbar)
        self.users_toolbar_grid.setContentsMargins(16, 14, 16, 14)
        self.users_toolbar_grid.setHorizontalSpacing(12)
        self.users_toolbar_grid.setVerticalSpacing(12)

        self.users_header_title_box = QWidget()
        title_layout = QVBoxLayout(self.users_header_title_box)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(3)
        title = QLabel(self.translator.text("users.title"))
        title.setObjectName("UsersPageHeading")
        title.setProperty("titleKey", "users.title")
        subtitle = QLabel(self.translator.text("users.subtitle"))
        subtitle.setObjectName("UsersSubtitle")
        subtitle.setProperty("titleKey", "users.subtitle")
        # Keep the subtitle as a single line and elide on resize instead
        subtitle.setWordWrap(False)
        subtitle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # expose for responsive updates
        self.users_title_label = title
        self.users_subtitle_label = subtitle
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        self.users_header_actions_box = QWidget()
        actions_layout = QHBoxLayout(self.users_header_actions_box)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        actions_layout.addStretch(1)
        refresh = QPushButton()
        refresh.setProperty("textKey", "users.refresh")
        refresh.setText(self.translator.text("users.refresh"))
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.refresh_users)
        create = QPushButton()
        create.setObjectName("PrimaryButton")
        create.setProperty("textKey", "users.create")
        create.setText(self.translator.text("users.create"))
        create.setCursor(Qt.CursorShape.PointingHandCursor)
        create.clicked.connect(self.create_user_dialog)
        actions_layout.addWidget(refresh)
        actions_layout.addWidget(create)

        self.users_filter_box = QWidget()
        filters_layout = QHBoxLayout(self.users_filter_box)
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(8)
        self.users_search = QLineEdit()
        self.users_search.setProperty("placeholderKey", "users.search_placeholder")
        self.users_search.setPlaceholderText(
            self.translator.text("users.search_placeholder")
        )
        self.users_search.setClearButtonEnabled(True)
        self.users_search.setMinimumWidth(180)
        self.users_search.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.users_search.textChanged.connect(self._filter_users_table)
        filters_layout.addWidget(self.users_search, 2)

        self.users_role_filter = QComboBox()
        self.users_role_filter.setMinimumWidth(150)
        self.users_role_filter.currentIndexChanged.connect(
            lambda _index: self._apply_users_filters()
        )
        filters_layout.addWidget(self.users_role_filter, 1)

        self.users_status_group = QButtonGroup(self)
        self.users_status_group.setExclusive(True)
        self.users_status_buttons: dict[str, QPushButton] = {}
        for status, key in (
            ("all", "users.filter.all"),
            ("active", "users.filter.active"),
            ("inactive", "users.filter.inactive"),
        ):
            button = QPushButton(self.translator.text(key))
            button.setObjectName("UsersFilterButton")
            button.setProperty("textKey", key)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if status == "all":
                button.setChecked(True)
            button.clicked.connect(
                lambda _checked, value=status: self._set_users_status_filter(value)
            )
            self.users_status_group.addButton(button)
            self.users_status_buttons[status] = button
            filters_layout.addWidget(button)

        self.users_stats_widget = QWidget()
        self.users_stats_grid = QGridLayout(self.users_stats_widget)
        self.users_stats_grid.setContentsMargins(0, 0, 0, 0)
        self.users_stats_grid.setSpacing(10)
        self.stat_total_card, self.stat_total_val = self._make_user_stat_card(
            "users.stats.total", "UsersStatCardTotal"
        )
        self.stat_active_card, self.stat_active_val = self._make_user_stat_card(
            "users.stats.active", "UsersStatCardActive"
        )
        self.stat_inactive_card, self.stat_inactive_val = self._make_user_stat_card(
            "users.stats.inactive", "UsersStatCardInactive"
        )
        self.users_stat_cards = [
            self.stat_total_card,
            self.stat_active_card,
            self.stat_inactive_card,
        ]

        list_meta = QHBoxLayout()
        list_meta.setContentsMargins(0, 0, 0, 0)
        self.users_visible_count_label = QLabel()
        self.users_visible_count_label.setObjectName("UsersVisibleCount")
        list_meta.addWidget(self.users_visible_count_label)
        list_meta.addStretch(1)

        self.users_table = QTableWidget(0, len(USER_TABLE_HEADER_KEYS))
        self.users_table.setObjectName("UsersTable")
        self._configure_table(self.users_table)
        users_vertical_header = self.users_table.verticalHeader()
        if users_vertical_header is not None:
            users_vertical_header.setDefaultSectionSize(46)
        self._set_users_table_headers()
        self._install_record_actions(
            self.users_table,
            view=self._show_user_details_dialog,
            edit=self.edit_user_dialog,
            lifecycle=self.deactivate_user_action,
            lifecycle_label=self._active_lifecycle_label,
        )

        self.users_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.users_empty_state = self._build_users_empty_state()
        self.users_table_stack = QStackedWidget()
        self.users_table_stack.addWidget(self.users_table)
        self.users_table_stack.addWidget(self.users_empty_state)

        self.users_pagination_bar = self._build_users_pagination_bar()

        page_layout.addWidget(toolbar)
        page_layout.addWidget(self.users_stats_widget)
        page_layout.addLayout(list_meta)
        page_layout.addWidget(self.users_table_stack, 1)
        page_layout.addWidget(self.users_pagination_bar)
        self._populate_users_role_filter()
        return page

    def _make_user_stat_card(
        self, title_key: str, card_name: str = "UsersStatCard"
    ) -> tuple[QFrame, QLabel]:
        """Create one Users KPI card."""

        card = QFrame()
        card.setObjectName(card_name)
        card.setMinimumHeight(76)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(15, 23, 42, 12))
        shadow.setOffset(0, 3)
        card.setGraphicsEffect(shadow)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(3)
        title = QLabel(self.translator.text(title_key))
        title.setObjectName("UsersStatTitle")
        title.setProperty("titleKey", title_key)
        value = QLabel("0")
        value.setObjectName("UsersStatValue")
        layout.addWidget(title)
        layout.addWidget(value)
        layout.addStretch(1)
        return card, value

    def _build_users_empty_state(self) -> QFrame:
        """Create the empty state shown when the filtered list has no rows."""

        frame = QFrame()
        frame.setObjectName("UsersEmptyState")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(6)
        layout.addStretch(1)
        self.users_empty_title = QLabel()
        self.users_empty_title.setObjectName("UsersPageHeading")
        self.users_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.users_empty_body = QLabel()
        self.users_empty_body.setObjectName("UsersSubtitle")
        self.users_empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.users_empty_body.setWordWrap(True)
        layout.addWidget(self.users_empty_title)
        layout.addWidget(self.users_empty_body)
        layout.addStretch(1)
        return frame

    def _show_users_list_page(self) -> None:
        """Return to the Users list state."""

        self.users_stack.setCurrentWidget(self.users_list_page)
        self._apply_users_filters()

    def _filter_users_table(self, _text: str) -> None:
        """Filter the users table based on search input in real time."""

        self._apply_users_filters()

    def _set_users_status_filter(self, status: str) -> None:
        """Apply one of the segmented status filters."""

        self.users_status_filter = status
        self._apply_users_filters()

    def _populate_users_role_filter(self) -> None:
        """Refresh the role filter from the loaded user rows."""

        if not hasattr(self, "users_role_filter"):
            return
        selected = (
            self.users_role_filter.currentData()
            if self.users_role_filter.count()
            else "all"
        )
        roles = sorted(
            {
                str(row.get("role_name") or "")
                for row in self.users_rows
                if row.get("role_name")
            }
        )
        self.users_role_filter.blockSignals(True)
        self.users_role_filter.clear()
        self.users_role_filter.addItem(
            self.translator.text("users.filter.role_all"), "all"
        )
        for role in roles:
            self.users_role_filter.addItem(role, role)
        index = self.users_role_filter.findData(selected)
        self.users_role_filter.setCurrentIndex(index if index >= 0 else 0)
        self.users_role_filter.blockSignals(False)

    def _apply_users_filters(self) -> None:
        """Re-render the table from the current search, role, and status filters."""

        if not hasattr(self, "users_table"):
            return
        self.users_current_page = 0
        query = (
            self.users_search.text().strip().casefold()
            if hasattr(self, "users_search")
            else ""
        )
        role_filter = (
            self.users_role_filter.currentData()
            if hasattr(self, "users_role_filter")
            else "all"
        )
        filtered: list[ApiRow] = []
        for row in self.users_rows:
            active = bool(row.get("is_active"))
            if self.users_status_filter == "active" and not active:
                continue
            if self.users_status_filter == "inactive" and active:
                continue
            if role_filter not in (None, "all") and str(
                row.get("role_name") or ""
            ) != str(role_filter):
                continue
            haystack = " ".join(
                str(row.get(key) or "")
                for key in ("id", "username", "full_name", "role_name", "is_active")
            ).casefold()
            if query and query not in haystack:
                continue
            filtered.append(row)
        self.users_filtered_rows = filtered
        self._render_users_table(filtered)

    def _render_users_table(self, rows: list[ApiRow]) -> None:
        """Render the paginated Users rows for the current page."""

        total = len(rows)
        start = self.users_current_page * self.users_page_size
        end = min(start + self.users_page_size, total)
        page_rows = rows[start:end]

        self.users_table.setSortingEnabled(False)
        self.users_table.setRowCount(0)
        self.users_table.setRowCount(len(page_rows))
        for row_index, user in enumerate(page_rows):
            values = (
                user.get("id"),
                user.get("username"),
                user.get("full_name"),
                user.get("role_name"),
                self.translator.text(
                    "users.status.active"
                    if user.get("is_active")
                    else "users.status.inactive"
                ),
            )
            for column_index, value in enumerate(values):
                item = self._table_item(value)
                item.setData(Qt.ItemDataRole.UserRole, user)
                self.users_table.setItem(row_index, column_index, item)
            self.users_table.setRowHeight(row_index, 46)
        self._configure_users_table_columns()
        self.users_table.setSortingEnabled(True)
        self._update_users_visible_count()
        self._update_users_empty_state(total)
        self._update_users_pagination()

    def _update_users_visible_count(self) -> None:
        """Update visible/total count text."""

        if not hasattr(self, "users_visible_count_label"):
            return
        self.users_visible_count_label.setText(
            self.translator.text("users.visible_count").format(
                visible=len(self.users_filtered_rows),
                total=len(self.users_rows),
            )
        )

    def _update_users_empty_state(self, visible_count: int) -> None:
        """Switch between table and empty state."""

        has_any_users = bool(self.users_rows)
        if visible_count > 0:
            self.users_table_stack.setCurrentWidget(self.users_table)
            return
        self.users_empty_title.setText(
            self.translator.text(
                "users.empty.title" if has_any_users else "users.empty.no_users_title"
            )
        )
        self.users_empty_body.setText(
            self.translator.text(
                "users.empty.body" if has_any_users else "users.empty.no_users_body"
            )
        )
        self.users_table_stack.setCurrentWidget(self.users_empty_state)

    def _build_users_pagination_bar(self) -> QFrame:
        """Build the pagination control bar below the Users table."""

        bar = QFrame()
        bar.setObjectName("UsersPaginationBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)

        size_label = QLabel(self.translator.text("users.pagination.per_page"))
        size_label.setObjectName("UsersPaginationInfo")
        size_label.setProperty("titleKey", "users.pagination.per_page")
        self.users_page_size_combo = QComboBox()
        self.users_page_size_combo.setObjectName("UsersPageSizeCombo")
        self.users_page_size_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for size in (5, 10, 15, 25):
            self.users_page_size_combo.addItem(str(size), size)
        self.users_page_size_combo.setCurrentIndex(1)
        self.users_page_size_combo.currentIndexChanged.connect(
            lambda _: self._change_users_page_size(
                self.users_page_size_combo.currentData()
            )
        )
        layout.addWidget(size_label)
        layout.addWidget(self.users_page_size_combo)

        layout.addStretch(1)

        self.users_pagination_info = QLabel()
        self.users_pagination_info.setObjectName("UsersPaginationInfo")
        layout.addWidget(self.users_pagination_info)

        layout.addStretch(1)

        self.users_page_nav_layout = QHBoxLayout()
        self.users_page_nav_layout.setSpacing(4)

        self.users_btn_first = QPushButton("\u00ab")
        self.users_btn_first.setObjectName("UsersPaginationButton")
        self.users_btn_first.setCursor(Qt.CursorShape.PointingHandCursor)
        self.users_btn_first.clicked.connect(lambda: self._go_to_users_page(0))

        self.users_btn_prev = QPushButton("\u2039")
        self.users_btn_prev.setObjectName("UsersPaginationButton")
        self.users_btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.users_btn_prev.clicked.connect(
            lambda: self._go_to_users_page(self.users_current_page - 1)
        )

        self.users_btn_next = QPushButton("\u203a")
        self.users_btn_next.setObjectName("UsersPaginationButton")
        self.users_btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.users_btn_next.clicked.connect(
            lambda: self._go_to_users_page(self.users_current_page + 1)
        )

        self.users_btn_last = QPushButton("\u00bb")
        self.users_btn_last.setObjectName("UsersPaginationButton")
        self.users_btn_last.setCursor(Qt.CursorShape.PointingHandCursor)
        self.users_btn_last.clicked.connect(
            lambda: self._go_to_users_page(self._users_total_pages() - 1)
        )

        self.users_page_nav_layout.addWidget(self.users_btn_first)
        self.users_page_nav_layout.addWidget(self.users_btn_prev)

        self.users_page_buttons_container = QWidget()
        self.users_page_buttons_layout = QHBoxLayout(self.users_page_buttons_container)
        self.users_page_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.users_page_buttons_layout.setSpacing(4)
        self.users_page_nav_layout.addWidget(self.users_page_buttons_container)

        self.users_page_nav_layout.addWidget(self.users_btn_next)
        self.users_page_nav_layout.addWidget(self.users_btn_last)

        layout.addLayout(self.users_page_nav_layout)

        return bar

    def _users_total_pages(self) -> int:
        """Return total page count based on filtered rows and page size."""

        total = len(self.users_filtered_rows)
        if total == 0:
            return 1
        return (total + self.users_page_size - 1) // self.users_page_size

    def _update_users_pagination(self) -> None:
        """Recalculate and refresh the pagination controls."""

        if not hasattr(self, "users_pagination_info"):
            return
        total = len(self.users_filtered_rows)
        total_pages = self._users_total_pages()
        if self.users_current_page >= total_pages:
            self.users_current_page = max(0, total_pages - 1)

        start = self.users_current_page * self.users_page_size + 1
        end = min(start + self.users_page_size - 1, total)
        if total == 0:
            self.users_pagination_info.setText(
                self.translator.text("users.pagination.showing").format(
                    start=0, end=0, total=0
                )
            )
        else:
            self.users_pagination_info.setText(
                self.translator.text("users.pagination.showing").format(
                    start=start, end=end, total=total
                )
            )

        self.users_btn_first.setEnabled(self.users_current_page > 0)
        self.users_btn_prev.setEnabled(self.users_current_page > 0)
        self.users_btn_next.setEnabled(self.users_current_page < total_pages - 1)
        self.users_btn_last.setEnabled(self.users_current_page < total_pages - 1)

        while self.users_page_buttons_layout.count():
            child = self.users_page_buttons_layout.takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        max_visible = 5
        if total_pages <= max_visible:
            pages_to_show = list(range(total_pages))
        else:
            half = max_visible // 2
            start_page = max(0, self.users_current_page - half)
            end_page = start_page + max_visible
            if end_page > total_pages:
                end_page = total_pages
                start_page = end_page - max_visible
            pages_to_show = list(range(start_page, end_page))

        for page_index in pages_to_show:
            btn = QPushButton(str(page_index + 1))
            if page_index == self.users_current_page:
                btn.setObjectName("UsersPaginationButtonActive")
            else:
                btn.setObjectName("UsersPaginationButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda _checked, p=page_index: self._go_to_users_page(p)
            )
            self.users_page_buttons_layout.addWidget(btn)

    def _go_to_users_page(self, page: int) -> None:
        """Navigate to a specific page in the Users table."""

        total_pages = self._users_total_pages()
        self.users_current_page = max(0, min(page, total_pages - 1))
        self._render_users_table(self.users_filtered_rows)

    def _change_users_page_size(self, size: int) -> None:
        """Change the number of rows displayed per page."""

        if size and size > 0:
            self.users_page_size = size
            self.users_current_page = 0
            self._render_users_table(self.users_filtered_rows)

    def _make_status_badge(self, active: bool, _lang: str) -> QWidget:
        """Create a styled active/inactive status badge."""

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge = QLabel(
            self.translator.text(
                "users.status.active" if active else "users.status.inactive"
            )
        )
        badge.setObjectName("UsersBadgeActive" if active else "UsersBadgeInactive")
        layout.addWidget(badge)
        return container

    def _make_role_badge(self, role_name: object) -> QLabel:
        """Create a compact role badge."""

        role = QLabel(str(role_name or "-"))
        role.setObjectName("UsersRoleBadge")
        role.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return role

    def _user_initials(self, row: ApiRow) -> str:
        """Return initials for a Users profile avatar."""

        full_name = str(row.get("full_name") or "").strip()
        username = str(row.get("username") or "").strip()
        parts = [part for part in full_name.split() if part]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        if parts:
            return parts[0][0].upper()
        if username:
            return username[:2].upper()
        return "U"

    def _show_user_details_dialog(self, row: ApiRow) -> None:
        """Compatibility wrapper: show the full-page Users detail view."""

        self._render_user_detail(row)
        self.users_stack.setCurrentWidget(self.users_detail_page)

    def _copy_to_clipboard(self, text: str, button: QPushButton) -> None:
        """Copy text to system clipboard and update button state."""

        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer

        QApplication.clipboard().setText(text)
        button.setProperty("copied", True)
        
        lang = self.translator.language
        copied_text = "Скопировано" if lang == "ru" else "Göçürildi" if lang == "tk" else "Copied"
        button.setText("✓ " + copied_text)
        
        button.style().unpolish(button)
        button.style().polish(button)

        def reset():
            button.setProperty("copied", False)
            copy_label = "Копировать" if lang == "ru" else "Göçür" if lang == "tk" else "Copy"
            button.setText("📋 " + copy_label)
            button.style().unpolish(button)
            button.style().polish(button)

        QTimer.singleShot(1500, reset)

    def _render_user_detail(self, row: ApiRow) -> None:
        """Render one user in the full-page detail state."""

        from PyQt6.QtWidgets import QBoxLayout

        self.users_current_detail_row = dict(row)
        self._clear_layout(self.users_detail_layout)

        # Header Section
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 8)
        
        back = QPushButton("←  " + self.translator.text("users.back_to_list"))
        back.setObjectName("UsersFormBackButton")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self._show_users_list_page)
        
        title = QLabel(self.translator.text("users.details"))
        title.setObjectName("UsersPageHeading")
        
        header.addWidget(back)
        header.addWidget(title)
        header.addStretch(1)
        self.users_detail_layout.addLayout(header)

        # Scroll Area for responsive content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 8, 0, 8)
        content_layout.setSpacing(16)

        # Responsive detail container
        self.users_detail_container = QWidget()
        self.users_detail_container_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.users_detail_container_layout.setContentsMargins(0, 0, 0, 0)
        self.users_detail_container_layout.setSpacing(20)
        self.users_detail_container.setLayout(self.users_detail_container_layout)

        # Left/Top Card: Profile Overview
        profile = QFrame()
        profile.setObjectName("UsersProfileCardModern")
        self.users_profile_card = profile
        
        profile_layout = QVBoxLayout(profile)
        profile_layout.setContentsMargins(24, 36, 24, 36)
        profile_layout.setSpacing(12)
        profile_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        avatar = QLabel(self._user_initials(row))
        avatar.setObjectName("UsersDetailAvatar")
        avatar.setProperty("active", bool(row.get("is_active")))
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add drop shadow to Avatar
        avatar_shadow = QGraphicsDropShadowEffect()
        avatar_shadow.setBlurRadius(10)
        avatar_shadow.setColor(QColor(0, 0, 0, 30))
        avatar_shadow.setOffset(0, 4)
        avatar.setGraphicsEffect(avatar_shadow)
        
        name = QLabel(str(row.get("full_name") or row.get("username") or "-"))
        name.setObjectName("UsersPageHeading")
        name.setStyleSheet("font-size: 15pt; font-weight: 800; color: #0f172a; margin-top: 10px;")
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        username = QLabel(f"@{row.get('username') or '-'}")
        username.setObjectName("UsersSubtitle")
        username.setStyleSheet("font-size: 10pt; color: #3b82f6; font-weight: 600;")
        username.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        separator = QFrame()
        separator.setStyleSheet("background: #e2e8f0; max-height: 1px; min-height: 1px; border: none;")
        
        badges = QHBoxLayout()
        badges.setSpacing(8)
        badges.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badges.addWidget(self._make_role_badge(row.get("role_name")))
        badges.addWidget(
            self._make_status_badge(
                bool(row.get("is_active")), self.translator.language
            )
        )
        
        profile_layout.addStretch(1)
        profile_layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignCenter)
        profile_layout.addWidget(name, 0, Qt.AlignmentFlag.AlignCenter)
        profile_layout.addWidget(username, 0, Qt.AlignmentFlag.AlignCenter)
        profile_layout.addWidget(separator)
        profile_layout.addLayout(badges)
        profile_layout.addStretch(1)

        # Add drop shadow to Profile Card
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(14)
        shadow.setColor(QColor(0, 0, 0, 15))
        shadow.setOffset(0, 4)
        profile.setGraphicsEffect(shadow)

        # Right/Bottom Card: Account Details
        details = QFrame()
        details.setObjectName("UsersDetailsCardModern")
        
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(24, 24, 24, 24)
        details_layout.setSpacing(0)

        card_title = QLabel(self.translator.text("users.details"))
        card_title.setObjectName("UsersPageHeading")
        card_title.setStyleSheet("font-size: 13pt; font-weight: 800; color: #0f172a; margin-bottom: 16px;")
        details_layout.addWidget(card_title)

        fields = (
            ("users.table.id", str(row.get("id")), True),
            ("users.table.username", str(row.get("username")), True),
            ("users.table.full_name", str(row.get("full_name") or ""), True),
            ("users.table.role", str(row.get("role_name") or ""), True),
            (
                "users.table.active",
                self.translator.text(
                    "users.status.active"
                    if row.get("is_active")
                    else "users.status.inactive"
                ),
                False,
            ),
        )

        for label_key, val_value, is_copyable in fields:
            row_frame = QFrame()
            row_frame.setObjectName("UsersFieldRow")
            row_lay = QHBoxLayout(row_frame)
            row_lay.setContentsMargins(12, 12, 12, 12)
            row_lay.setSpacing(10)

            # Left Text Group
            text_container = QWidget()
            text_lay = QVBoxLayout(text_container)
            text_lay.setContentsMargins(0, 0, 0, 0)
            text_lay.setSpacing(4)

            lbl = QLabel(self.translator.text(label_key).upper())
            lbl.setObjectName("UsersFieldLabel")
            lbl.setStyleSheet("font-size: 8pt; font-weight: 700; color: #64748b; letter-spacing: 0.5px;")

            val = QLabel(self._format_value(val_value))
            val.setObjectName("UsersFieldValue")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            text_lay.addWidget(lbl)
            text_lay.addWidget(val)
            row_lay.addWidget(text_container, 1)

            # Copy Button
            if is_copyable and val_value and val_value != "-":
                copy_btn = QPushButton()
                copy_btn.setObjectName("UsersCopyButton")
                lang = self.translator.language
                copy_label = "Копировать" if lang == "ru" else "Göçür" if lang == "tk" else "Copy"
                copy_btn.setText("📋 " + copy_label)
                copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                copy_btn.clicked.connect(
                    lambda checked=False, text_to_copy=val_value, btn=copy_btn: self._copy_to_clipboard(text_to_copy, btn)
                )
                row_lay.addWidget(copy_btn)

            details_layout.addWidget(row_frame)

        # Add drop shadow to Details Card
        shadow2 = QGraphicsDropShadowEffect()
        shadow2.setBlurRadius(14)
        shadow2.setColor(QColor(0, 0, 0, 15))
        shadow2.setOffset(0, 4)
        details.setGraphicsEffect(shadow2)

        # Add profile and details cards to the dual container
        self.users_detail_container_layout.addWidget(profile)
        self.users_detail_container_layout.addWidget(details, 1)

        content_layout.addWidget(self.users_detail_container)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        self.users_detail_layout.addWidget(scroll, 1)

        # Footer Button Row
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 8, 0, 0)
        
        toggle = QPushButton(self._active_lifecycle_label(row))
        toggle.setObjectName("UsersStatusToggleButton")
        toggle.setProperty("status_active", bool(row.get("is_active")))
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.clicked.connect(
            lambda _checked=False, current=row: self.deactivate_user_action(current)
        )
        
        edit = QPushButton(self.translator.text("crud.edit"))
        edit.setObjectName("PrimaryButton")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(
            lambda _checked=False, current=row: self.edit_user_dialog(current)
        )
        
        button_row.addStretch(1)
        button_row.addWidget(toggle)
        button_row.addWidget(edit)
        self.users_detail_layout.addLayout(button_row)

        # Call responsive reflow to apply correct initial alignment
        self._update_users_responsive_layout()

    def _user_role_options(
        self, selected_role: str | None = None
    ) -> list[tuple[str, str]]:
        """Return role combo options using the API when available."""

        options: list[tuple[str, str]] = []
        try:
            roles = self.api_client.get_roles()
        except Exception:
            roles = []
        for role in roles:
            role_name = str(role.get("name") or "")
            if not role_name:
                continue
            description = str(role.get("description") or "")
            label = f"{role_name} ({description})" if description else role_name
            options.append((label, role_name))
        if not options:
            options = [("Cashier", "Cashier"), ("Administrator", "Administrator")]
        if selected_role and all(value != selected_role for _label, value in options):
            options.insert(0, (selected_role, selected_role))
        return options

    def create_user_dialog(self) -> None:
        """Compatibility wrapper: show the full-page create user form."""

        self._show_user_form("create")

    def edit_user_dialog(self, row: ApiRow) -> None:
        """Compatibility wrapper: show the full-page edit user form."""

        self._show_user_form("edit", row)

    def _show_user_form(self, mode: str, row: ApiRow | None = None) -> None:
        """Render the full-page create or edit user form."""

        is_edit = mode == "edit"
        row = dict(row or {})
        page = self.users_edit_page if is_edit else self.users_create_page
        layout = self.users_edit_layout if is_edit else self.users_create_layout
        self._clear_layout(layout)

        # Header section
        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        back = QPushButton("←  " + self.translator.text("users.back_to_list"))
        back.setObjectName("UsersFormBackButton")
        back.setProperty("textKey", "users.back_to_list")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self._show_users_list_page)
        
        title_box = QWidget()
        title_box_layout = QVBoxLayout(title_box)
        title_box_layout.setContentsMargins(0, 0, 0, 0)
        title_box_layout.setSpacing(4)
        
        title_key = "users.edit_title" if is_edit else "users.create"
        title = QLabel(self.translator.text(title_key))
        title.setObjectName("UsersPageHeading")
        title.setProperty("titleKey", title_key)
        
        subtitle_key = "users.form.subtitle_edit" if is_edit else "users.form.subtitle_create"
        subtitle = QLabel(self.translator.text(subtitle_key))
        subtitle.setObjectName("UsersFormSubtitle")
        subtitle.setProperty("titleKey", subtitle_key)
        
        title_box_layout.addWidget(title)
        title_box_layout.addWidget(subtitle)
        
        header_layout.addWidget(back)
        header_layout.addWidget(title_box)
        header_layout.addStretch(1)
        layout.addWidget(header_container)

        # Scroll Area for Form Content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 16, 0, 16)
        content_layout.setSpacing(16)

        # Main modern form card
        form_card = QFrame()
        form_card.setObjectName("UsersFormCardModernEdit" if is_edit else "UsersFormCardModern")
        
        card_layout = QVBoxLayout(form_card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(24)

        # Error display
        self.user_form_error_label = QLabel()
        self.user_form_error_label.setObjectName("UsersFormError")
        self.user_form_error_label.setWordWrap(True)
        self.user_form_error_label.hide()
        card_layout.addWidget(self.user_form_error_label)

        # 1. Avatar Section at the top of the card
        avatar_layout = QHBoxLayout()
        avatar_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        avatar_circle = QLabel()
        avatar_circle.setObjectName("UsersFormAvatarCircleEdit" if is_edit else "UsersFormAvatarCircle")
        avatar_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Initials helper
        def get_initials(name_str: str) -> str:
            parts = name_str.strip().split()
            if not parts:
                return "?"
            if len(parts) == 1:
                return parts[0][:2].upper()
            return (parts[0][0] + parts[1][0]).upper()

        initial_name = str(row.get("full_name") or row.get("username") or "")
        avatar_circle.setText(get_initials(initial_name))
        avatar_layout.addWidget(avatar_circle)
        card_layout.addLayout(avatar_layout)

        # Fields inputs initialization
        self.user_form_username = QLineEdit(str(row.get("username") or ""))
        self.user_form_username.setObjectName("UsersFormInput")
        self.user_form_username.setPlaceholderText(self.translator.text("users.form.username"))
        self.user_form_username.setProperty("placeholderKey", "users.form.username")
        self.user_form_username.setReadOnly(is_edit)
        
        self.user_form_full_name = QLineEdit(str(row.get("full_name") or ""))
        self.user_form_full_name.setObjectName("UsersFormInput")
        self.user_form_full_name.setPlaceholderText(self.translator.text("users.form.full_name"))
        self.user_form_full_name.setProperty("placeholderKey", "users.form.full_name")
        # Hook up initials updater
        self.user_form_full_name.textChanged.connect(lambda text: avatar_circle.setText(get_initials(text)))

        self.user_form_password = QLineEdit()
        self.user_form_password.setObjectName("UsersFormInput")
        self.user_form_password.setEchoMode(QLineEdit.EchoMode.Password)
        pass_hint_key = "users.form.password_hint" if is_edit else "users.form.password"
        self.user_form_password.setPlaceholderText(self.translator.text(pass_hint_key))
        self.user_form_password.setProperty("placeholderKey", pass_hint_key)

        # Password show/hide tool
        password_box = QWidget()
        password_layout = QHBoxLayout(password_box)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(10)
        
        self.user_form_password_toggle = QToolButton()
        self.user_form_password_toggle.setObjectName("UsersFormPasswordToggle")
        self.user_form_password_toggle.setText(self.translator.text("users.form.show_password"))
        self.user_form_password_toggle.setProperty("textKey", "users.form.show_password")
        self.user_form_password_toggle.setCursor(Qt.CursorShape.PointingHandCursor)

        def toggle_password() -> None:
            visible = self.user_form_password.echoMode() == QLineEdit.EchoMode.Password
            self.user_form_password.setEchoMode(
                QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
            )
            key = "users.form.hide_password" if visible else "users.form.show_password"
            self.user_form_password_toggle.setText(self.translator.text(key))
            self.user_form_password_toggle.setProperty("textKey", key)

        self.user_form_password_toggle.clicked.connect(toggle_password)
        password_layout.addWidget(self.user_form_password, 1)
        password_layout.addWidget(self.user_form_password_toggle)

        # Password strength bar
        strength_container = QWidget()
        strength_layout = QVBoxLayout(strength_container)
        strength_layout.setContentsMargins(0, 4, 0, 0)
        strength_layout.setSpacing(6)
        
        strength_header = QHBoxLayout()
        strength_title = QLabel(self.translator.text("users.form.password"))
        strength_title.setObjectName("UsersFormFieldLabel")
        strength_title.setProperty("titleKey", "users.form.password")
        strength_text = QLabel("")
        strength_text.setObjectName("UsersPasswordStrengthLabel")
        strength_header.addWidget(strength_title)
        strength_header.addStretch(1)
        strength_header.addWidget(strength_text)
        
        strength_bar = QProgressBar()
        strength_bar.setObjectName("UsersPasswordStrengthBarWeak")
        strength_bar.setTextVisible(False)
        strength_bar.setRange(0, 100)
        strength_bar.setValue(0)
        strength_bar.setFixedHeight(6)
        
        strength_layout.addLayout(strength_header)
        strength_layout.addWidget(strength_bar)
        strength_container.hide()

        def update_password_strength(text: str) -> None:
            if not text:
                strength_container.hide()
                return
            strength_container.show()

            # Categories: uppercase, lowercase, digits, symbols
            has_upper = any(c.isupper() for c in text)
            has_lower = any(c.islower() for c in text)
            has_digit = any(c.isdigit() for c in text)
            has_special = any(not c.isalnum() for c in text)

            categories_present = sum((has_upper, has_lower, has_digit, has_special))

            # Classification per requirement:
            # 4 categories -> strong, 3 -> good, 2 -> medium, 1 -> weak
            if categories_present >= 4:
                strength_bar.setObjectName("UsersPasswordStrengthBarStrong")
                strength_bar.setValue(100)
                strength_text.setText(self.translator.text("users.form.password_strength_strong"))
                strength_text.setObjectName("UsersPasswordStrengthLabelStrong")
                strength_text.setProperty("titleKey", "users.form.password_strength_strong")
            elif categories_present == 3:
                strength_bar.setObjectName("UsersPasswordStrengthBarGood")
                strength_bar.setValue(75)
                strength_text.setText(self.translator.text("users.form.password_strength_good"))
                strength_text.setObjectName("UsersPasswordStrengthLabelGood")
                strength_text.setProperty("titleKey", "users.form.password_strength_good")
            elif categories_present == 2:
                strength_bar.setObjectName("UsersPasswordStrengthBarMedium")
                strength_bar.setValue(50)
                strength_text.setText(self.translator.text("users.form.password_strength_medium"))
                strength_text.setObjectName("UsersPasswordStrengthLabelMedium")
                strength_text.setProperty("titleKey", "users.form.password_strength_medium")
            else:
                strength_bar.setObjectName("UsersPasswordStrengthBarWeak")
                strength_bar.setValue(25)
                strength_text.setText(self.translator.text("users.form.password_strength_weak"))
                strength_text.setObjectName("UsersPasswordStrengthLabelWeak")
                strength_text.setProperty("titleKey", "users.form.password_strength_weak")

            # Re-apply style so objectName changes take effect
            strength_bar.style().unpolish(strength_bar)
            strength_bar.style().polish(strength_bar)
            strength_text.style().unpolish(strength_text)
            strength_text.style().polish(strength_text)

        self.user_form_password.textChanged.connect(update_password_strength)

        # Role Combobox
        self.user_form_role_combo = QComboBox()
        self.user_form_role_combo.setObjectName("UsersFormCombo")
        current_role = str(row.get("role_name") or "")
        for label, value in self._user_role_options(current_role or None):
            self.user_form_role_combo.addItem(label, value)
        selected_role = self.user_form_role_combo.findData(current_role)
        if selected_role >= 0:
            self.user_form_role_combo.setCurrentIndex(selected_role)

        # Active Checkbox
        self.user_form_active_check = QCheckBox()
        self.user_form_active_check.setObjectName("UsersFormToggle")
        self.user_form_active_check.setChecked(bool(row.get("is_active", True)))
        self.user_form_active_check.setCursor(Qt.CursorShape.PointingHandCursor)

        status_label = QLabel()
        status_label.setObjectName("UsersFormToggleLabelActive" if self.user_form_active_check.isChecked() else "UsersFormToggleLabel")
        stat_key = "users.status.active" if self.user_form_active_check.isChecked() else "users.status.inactive"
        status_label.setText(self.translator.text(stat_key))
        status_label.setProperty("titleKey", stat_key)

        def toggle_status_label(checked: bool) -> None:
            key = "users.status.active" if checked else "users.status.inactive"
            status_label.setText(self.translator.text(key))
            status_label.setObjectName("UsersFormToggleLabelActive" if checked else "UsersFormToggleLabel")
            status_label.setProperty("titleKey", key)
            status_label.style().unpolish(status_label)
            status_label.style().polish(status_label)
            
        self.user_form_active_check.toggled.connect(toggle_status_label)

        # Form Section helper
        def create_section(icon_char: str, section_title_key: str) -> tuple[QFrame, QVBoxLayout]:
            sec_card = QFrame()
            sec_card.setObjectName("UsersFormSectionCard")
            sec_lay = QVBoxLayout(sec_card)
            sec_lay.setContentsMargins(20, 20, 20, 20)
            sec_lay.setSpacing(16)
            
            # Header Layout
            header_widget = QWidget()
            header_lay = QHBoxLayout(header_widget)
            header_lay.setContentsMargins(0, 0, 0, 0)
            header_lay.setSpacing(8)
            
            icon_lbl = QLabel(icon_char)
            icon_lbl.setObjectName("UsersFormSectionIcon")
            title_lbl = QLabel(self.translator.text(section_title_key))
            title_lbl.setObjectName("UsersFormSectionHeader")
            title_lbl.setProperty("titleKey", section_title_key)
            
            header_lay.addWidget(icon_lbl)
            header_lay.addWidget(title_lbl)
            header_lay.addStretch(1)
            
            sec_lay.addWidget(header_widget)
            
            # Sub-card divider line
            divider = QFrame()
            divider.setStyleSheet("background: #e2e8f0; max-height: 1px; min-height: 1px; border: none;")
            sec_lay.addWidget(divider)
            
            return sec_card, sec_lay

        def add_field_to_section(sec_lay: QVBoxLayout, label_key: str, input_widget: QWidget):
            field_widget = QWidget()
            field_lay = QVBoxLayout(field_widget)
            field_lay.setContentsMargins(0, 0, 0, 0)
            field_lay.setSpacing(6)
            
            label = QLabel(self.translator.text(label_key))
            label.setObjectName("UsersFormFieldLabel")
            label.setProperty("titleKey", label_key)
            
            field_lay.addWidget(label)
            field_lay.addWidget(input_widget)
            sec_lay.addWidget(field_widget)

        # Section 1: Account Info
        sec_account, sec_account_layout = create_section("👤", "users.form.section_account")
        add_field_to_section(sec_account_layout, "users.form.username", self.user_form_username)
        add_field_to_section(sec_account_layout, "users.form.full_name", self.user_form_full_name)
        card_layout.addWidget(sec_account)

        # Section 2: Security
        sec_security, sec_security_layout = create_section("🔑", "users.form.section_security")
        
        pass_field_widget = QWidget()
        pass_field_lay = QVBoxLayout(pass_field_widget)
        pass_field_lay.setContentsMargins(0, 0, 0, 0)
        pass_field_lay.setSpacing(6)
        pass_label = QLabel(self.translator.text("users.form.password"))
        pass_label.setObjectName("UsersFormFieldLabel")
        pass_label.setProperty("titleKey", "users.form.password")
        pass_field_lay.addWidget(pass_label)
        pass_field_lay.addWidget(password_box)
        
        sec_security_layout.addWidget(pass_field_widget)
        sec_security_layout.addWidget(strength_container)
        card_layout.addWidget(sec_security)

        # Section 3: Permissions
        sec_perms, sec_perms_layout = create_section("🛡️", "users.form.section_permissions")
        add_field_to_section(sec_perms_layout, "users.form.role", self.user_form_role_combo)
        
        # Add toggle switch field
        toggle_widget = QWidget()
        toggle_lay = QHBoxLayout(toggle_widget)
        toggle_lay.setContentsMargins(0, 4, 0, 0)
        toggle_lay.setSpacing(12)
        toggle_lay.addWidget(self.user_form_active_check)
        toggle_lay.addWidget(status_label)
        toggle_lay.addStretch(1)
        
        sec_perms_layout.addWidget(toggle_widget)
        card_layout.addWidget(sec_perms)

        # Add card to wrapper to center it
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addStretch(1)
        wrapper_layout.addWidget(form_card, 2)
        wrapper_layout.addStretch(1)
        
        content_layout.addWidget(wrapper)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Footer Button Row
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 8, 0, 0)
        
        cancel = QPushButton(self.translator.text("crud.cancel"))
        cancel.setObjectName("UsersFormCancelButton")
        cancel.setProperty("textKey", "crud.cancel")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self._show_users_list_page)
        
        self.user_form_save_button = QPushButton(self.translator.text("users.save"))
        self.user_form_save_button.setObjectName("UsersFormSaveButton")
        self.user_form_save_button.setProperty("textKey", "users.save")
        self.user_form_save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.user_form_save_button.clicked.connect(
            lambda _checked=False: self._submit_user_form(mode, row)
        )
        
        button_row.addStretch(1)
        button_row.addWidget(cancel)
        button_row.addWidget(self.user_form_save_button)
        layout.addLayout(button_row)

        self.users_stack.setCurrentWidget(page)

    def _submit_user_form(self, mode: str, row: ApiRow) -> None:
        """Validate and submit the current full-page Users form."""

        is_edit = mode == "edit"
        errors: list[str] = []
        username = self.user_form_username.text().strip()
        full_name = self.user_form_full_name.text().strip()
        password = self.user_form_password.text()
        if not is_edit and not username:
            errors.append(self.translator.text("users.validation.username_required"))
        if not full_name:
            errors.append(self.translator.text("users.validation.full_name_required"))
        if not is_edit and not password:
            errors.append(self.translator.text("users.validation.password_required"))
        if password and len(password) < 6:
            errors.append(self.translator.text("users.validation.password_short"))
        if errors:
            self.user_form_error_label.setText("\n".join(errors))
            self.user_form_error_label.show()
            return
        self.user_form_error_label.hide()

        role_name = str(self.user_form_role_combo.currentData() or "Cashier")
        if is_edit:
            payload: ApiRow = {
                "full_name": full_name,
                "role_name": role_name,
                "is_active": self.user_form_active_check.isChecked(),
            }
            if password:
                payload["password"] = password

            def action() -> None:
                updated = self.api_client.update_user(int(row["id"]), payload)
                self._refresh_users_data()
                detail = self._find_user_by_id(row.get("id")) or dict(updated)
                self._show_user_details_dialog(detail)

            self._run_api(action)
            return

        payload = {
            "username": username,
            "full_name": full_name,
            "password": password,
            "role_name": role_name,
            "is_active": self.user_form_active_check.isChecked(),
        }

        def action() -> None:
            created = self.api_client.create_user(payload)
            self._refresh_users_data()
            detail = (
                self._find_user_by_id(created.get("id"))
                if isinstance(created, dict)
                else None
            )
            self._show_user_details_dialog(detail or dict(created))

        self._run_api(action)

    def _find_user_by_id(self, user_id: object) -> ApiRow | None:
        """Find one loaded user row by ID."""

        for row in self.users_rows:
            if str(row.get("id")) == str(user_id):
                return row
        return None

    def refresh_users(self) -> None:
        """Refresh Users data and keep the full-page workflow state."""

        self._run_api(self._refresh_users_data)

    def _refresh_users_data(self) -> None:
        """Load Users rows and refresh list widgets without opening dialogs."""

        users = self.api_client.get_users()
        self.users_rows = [dict(user) for user in users]
        total_count = len(self.users_rows)
        active_count = sum(1 for user in self.users_rows if user.get("is_active"))
        inactive_count = total_count - active_count
        if hasattr(self, "stat_total_val"):
            self.stat_total_val.setText(str(total_count))
        if hasattr(self, "stat_active_val"):
            self.stat_active_val.setText(str(active_count))
        if hasattr(self, "stat_inactive_val"):
            self.stat_inactive_val.setText(str(inactive_count))
        self._populate_users_role_filter()
        self._apply_users_filters()

    def deactivate_user_action(self, row: ApiRow) -> None:
        """Activate or deactivate a user and preserve the relevant Users state."""

        target_active = not bool(row.get("is_active"))
        label = self.translator.text(
            "crud.activate" if target_active else "crud.deactivate"
        )
        if not self._confirm_record_action(row, label):
            return
        user_id = row.get("id")
        current_widget = (
            self.users_stack.currentWidget() if hasattr(self, "users_stack") else None
        )

        def action() -> None:
            if target_active:
                updated = self.api_client.update_user(
                    int(row["id"]), {"is_active": True}
                )
            else:
                updated = self.api_client.deactivate_user(int(row["id"]))
            self._refresh_users_data()
            refreshed = self._find_user_by_id(user_id) or {
                **row,
                **dict(updated),
                "is_active": target_active,
            }
            if current_widget in (
                getattr(self, "users_detail_page", None),
                getattr(self, "users_edit_page", None),
            ):
                self._show_user_details_dialog(refreshed)

        self._run_api(action)

    def _configure_users_table_columns(self) -> None:
        """Apply practical resize policies for the Users table."""

        if not hasattr(self, "users_table") or self.users_table.columnCount() < 5:
            return
        header = self.users_table.horizontalHeader()
        if header is None:
            return
        for i in range(self.users_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

    def _set_users_table_headers(self) -> None:
        """Apply translated column headers to the users table."""

        if not hasattr(self, "users_table"):
            return
        headers = [self.translator.text(key) for key in USER_TABLE_HEADER_KEYS]
        self.users_table.setColumnCount(len(headers))
        self.users_table.setHorizontalHeaderLabels(headers)
        self._configure_users_table_columns()

    def _update_users_responsive_layout(self) -> None:
        """Reflow Users controls and KPI cards for the current window width."""

        if not hasattr(self, "users_toolbar_grid"):
            return
        for widget in (
            self.users_header_title_box,
            self.users_header_actions_box,
            self.users_filter_box,
        ):
            self.users_toolbar_grid.removeWidget(widget)
        self.users_toolbar_grid.addWidget(self.users_header_title_box, 0, 0)
        self.users_toolbar_grid.addWidget(self.users_header_actions_box, 0, 1)
        self.users_toolbar_grid.addWidget(self.users_filter_box, 1, 0, 1, 2)
        columns = 3
        if columns != self.users_stat_columns:
            self.users_stat_columns = columns
            for card in self.users_stat_cards:
                self.users_stats_grid.removeWidget(card)
            for index, card in enumerate(self.users_stat_cards):
                self.users_stats_grid.addWidget(card, index // columns, index % columns)
        # Ensure the subtitle fits on a single line by eliding if necessary.
        if hasattr(self, "users_subtitle_label") and hasattr(
            self, "users_header_title_box"
        ):
            try:
                subtitle = self.users_subtitle_label
                fm = QFontMetrics(subtitle.font())
                available = max(0, self.users_header_title_box.width() - 8)
                if available > 20:
                    full_text = self.translator.text("users.subtitle")
                    elided = fm.elidedText(
                        full_text, Qt.TextElideMode.ElideRight, available
                    )
                    subtitle.setText(elided)
            except Exception:
                # best-effort; don't break layout on unexpected errors
                pass

        # Reflow the user details cards if visible
        if (
            hasattr(self, "users_detail_container_layout")
            and self.users_detail_container_layout is not None
            and hasattr(self, "users_profile_card")
            and self.users_profile_card is not None
        ):
            from PyQt6.QtWidgets import QBoxLayout
            if self.width() < 900:
                if self.users_detail_container_layout.direction() != QBoxLayout.Direction.TopToBottom:
                    self.users_detail_container_layout.setDirection(QBoxLayout.Direction.TopToBottom)
                    self.users_profile_card.setMaximumWidth(16777215)
            else:
                if self.users_detail_container_layout.direction() != QBoxLayout.Direction.LeftToRight:
                    self.users_detail_container_layout.setDirection(QBoxLayout.Direction.LeftToRight)
                    self.users_profile_card.setMaximumWidth(360)
                    self.users_profile_card.setMinimumWidth(300)

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
            "roles.create": ("admin.manage_roles",),
            "settings.save": ("settings.edit",),
            "catalog.create_group": ("goods.create",),
            "catalog.create_product": ("goods.create",),
            "catalog.create_service": ("goods.create",),
            "warehouse.create_warehouse": ("warehouse.create",),
            "warehouse.opening_inventory": (
                "warehouse.inventory_create",
                "warehouse.inventory_post",
            ),
            "warehouse.transfer": (
                "warehouse.transfer_create",
                "warehouse.transfer_send",
                "warehouse.transfer_receive",
            ),
            "warehouse.writeoff": (
                "warehouse.writeoff_create",
                "warehouse.writeoff_post",
            ),
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
            button.setToolTip(
                "" if allowed else self.translator.text("common.permission_required")
            )

    def resizeEvent(self, a0: QResizeEvent | None) -> None:
        """Handle window resizing to toggle sidebar visibility based on width."""

        super().resizeEvent(a0)
        # Auto-hide the navigation sidebar if the window width is below 1100 pixels
        self.nav.setHidden(self.width() < 1100)
        self._update_users_responsive_layout()
        self._update_roles_responsive_layout()

"""First-run setup wizard for database and API configuration."""

from __future__ import annotations

import pyodbc
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QResizeEvent, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig, create_default_config
from server_app.core.constants import DEFAULT_ODBC_DRIVER, SUPER_ADMIN_FULL_NAME, SUPER_ADMIN_USERNAME
from server_app.core.network import PortCheckResult, check_tcp_port
from server_app.db.bootstrap import validate_database_name
from server_app.gui.i18n import (
    LANGUAGE_OPTIONS,
    format_port_check_message,
    get_language,
    set_language,
    tr,
)


class SetupWindow(QWidget):
    """Collect all first-run settings needed to start the server."""

    setup_requested = pyqtSignal(object, object, str)

    COMPACT_WIDTH = 760
    MAX_CONTENT_WIDTH = 880
    COMPACT_CONTENT_WIDTH = 620
    STEP_COUNT = 3

    def __init__(self, error_message: str | None = None) -> None:
        super().__init__()
        self.setObjectName("SetupWindow")
        self.setMinimumSize(520, 560)
        self.default_config = create_default_config()
        self._initial_error_message = error_message
        self._is_compact_layout: bool | None = None
        self._is_busy = False
        self._current_step = 0
        self._last_port_result: PortCheckResult | None = None
        self._setup_status_key = "setup.ready"
        self._setup_status_before_busy = ("setup.ready", "neutral")

        self.field_labels: dict[str, QLabel] = {}
        self.validation_labels: dict[str, QLabel] = {}
        self.step_labels: list[QLabel] = []

        self.server_edit = QLineEdit(self.default_config.database.server)
        self.database_edit = QLineEdit(self.default_config.database.database)
        self.driver_combo = QComboBox()
        self.auth_combo = QComboBox()
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.trust_cert_check = QCheckBox()

        self.host_edit = QLineEdit(self.default_config.api.host)
        self.port_spin = QSpinBox()
        self.port_hint_label = QLabel()
        self.port_status_label = QLabel()
        self._port_check_timer = QTimer(self)
        self._port_check_timer.setSingleShot(True)
        self._port_check_timer.setInterval(300)

        self.super_admin_username_edit = QLineEdit(SUPER_ADMIN_USERNAME)
        self.super_admin_full_name_edit = QLineEdit(SUPER_ADMIN_FULL_NAME)
        self.current_password_edit = QLineEdit()
        self.new_password_edit = QLineEdit()
        self.confirm_password_edit = QLineEdit()

        self.title_label = QLabel()
        self.subtitle_label = QLabel()
        self.language_label = QLabel()
        self.language_combo = QComboBox()
        self.setup_status_label = QLabel()
        self.message_label = QLabel(error_message or "")
        self.back_button = QPushButton()
        self.next_button = QPushButton()
        self.submit_button = QPushButton()
        self.header_title_block = QWidget()
        self.header_language_block = QWidget()

        self._build_ui()
        self._connect_signals()
        self._retranslate_ui()

    def _build_ui(self) -> None:
        """Create the wizard controls and responsive layout."""

        self._apply_stylesheet()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.header_bar = self._build_header()
        main_layout.addWidget(self.header_bar, 0)

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
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        content_layout.addWidget(self._build_stepper())

        self.wizard_stack = QStackedWidget()
        self.wizard_stack.setObjectName("SetupWizardStack")
        self.database_group = self._build_mssql_page()
        self.api_group = self._build_api_page()
        self.super_admin_group = self._build_super_admin_page()
        self.wizard_stack.addWidget(self.database_group)
        self.wizard_stack.addWidget(self.api_group)
        self.wizard_stack.addWidget(self.super_admin_group)
        content_layout.addWidget(self.wizard_stack)
        content_layout.addStretch(1)

        footer = QWidget()
        footer.setObjectName("SetupFooter")
        self.footer_layout = QGridLayout(footer)
        self.footer_layout.setContentsMargins(24, 14, 24, 14)
        self.footer_layout.setHorizontalSpacing(18)
        self.footer_layout.setVerticalSpacing(10)

        self.message_label.setObjectName("FooterMessage")
        self.message_label.setWordWrap(True)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.footer_controls = QWidget()
        controls_layout = QHBoxLayout(self.footer_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(10)
        controls_layout.addWidget(self.back_button)
        controls_layout.addWidget(self.next_button)
        controls_layout.addWidget(self.submit_button)

        for button in (self.back_button, self.next_button, self.submit_button):
            button.setMinimumHeight(42)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.setObjectName("SecondaryButton")
        self.next_button.setObjectName("PrimaryButton")
        self.submit_button.setObjectName("PrimaryButton")

        main_layout.addWidget(scroll_area, 1)
        main_layout.addWidget(footer, 0)

        self._fill_driver_combo()
        self._set_auth_combo_items()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.current_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.super_admin_username_edit.setReadOnly(True)
        self.super_admin_full_name_edit.setReadOnly(True)
        self.trust_cert_check.setChecked(True)
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.default_config.api.port)
        self.port_hint_label.setObjectName("PortHint")
        self.port_hint_label.setWordWrap(True)
        self.port_status_label.setObjectName("PortStatus")
        self.port_status_label.setWordWrap(True)
        self.port_status_label.setVisible(False)

        self._populate_language_combo()
        self._sync_auth_fields()
        if self._initial_error_message:
            self.show_message(self._initial_error_message, "error")
            self._set_setup_status("setup.failed", "error")
        else:
            self._set_setup_status("setup.ready", "neutral")
        self._apply_responsive_layout()
        self._refresh_validation()

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("SetupHeaderBar")
        self.header_layout = QGridLayout(header)
        self.header_layout.setContentsMargins(24, 14, 24, 14)
        self.header_layout.setHorizontalSpacing(18)
        self.header_layout.setVerticalSpacing(10)

        self.title_label.setObjectName("SetupTitle")
        self.subtitle_label.setObjectName("SetupSubtitle")
        self.language_label.setObjectName("LanguageLabel")
        self.language_combo.setObjectName("LanguageCombo")
        self.language_combo.setMinimumWidth(150)

        self.header_title_block.setObjectName("HeaderTitleBlock")
        title_layout = QVBoxLayout(self.header_title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.subtitle_label)

        self.header_language_block.setObjectName("HeaderLanguageBlock")
        language_layout = QGridLayout(self.header_language_block)
        language_layout.setContentsMargins(0, 0, 0, 0)
        language_layout.setHorizontalSpacing(8)
        language_layout.setVerticalSpacing(4)
        language_layout.addWidget(self.language_label, 0, 0, alignment=Qt.AlignmentFlag.AlignRight)
        language_layout.addWidget(self.language_combo, 1, 0)

        self._build_setup_card()
        self._reflow_header(compact=False)
        return header

    def _build_setup_card(self) -> None:
        card = QFrame()
        card.setObjectName("ConnectionCard")
        card.setProperty("serviceState", "neutral")
        self.connection_card = card

        outer_layout = QHBoxLayout(card)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        accent = QFrame()
        accent.setObjectName("ConnectionAccent")
        accent.setFixedWidth(4)
        outer_layout.addWidget(accent)

        content = QWidget()
        content.setObjectName("ConnectionCardContent")
        outer_layout.addWidget(content, 1)

        card_layout = QHBoxLayout(content)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(14)

        self.card_title_label = QLabel()
        self.card_title_label.setObjectName("CardTitle")
        self.setup_status_label.setObjectName("ServiceStatus")
        self.setup_status_label.setWordWrap(True)
        self.setup_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card_layout.addWidget(self.card_title_label)
        card_layout.addStretch(1)
        card_layout.addWidget(self.setup_status_label)

    def _build_stepper(self) -> QWidget:
        stepper = QWidget()
        stepper.setObjectName("SetupStepper")
        layout = QHBoxLayout(stepper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for _index in range(self.STEP_COUNT):
            label = QLabel()
            label.setObjectName("WizardStep")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setProperty("stepState", "upcoming")
            label.setWordWrap(True)
            label.setMinimumHeight(40)
            self.step_labels.append(label)
            layout.addWidget(label, 1)
        return stepper

    def _build_page_shell(self, title_key: str, help_key: str) -> tuple[QFrame, QGridLayout]:
        page = QFrame()
        page.setObjectName("WizardPage")
        page.setProperty("titleKey", title_key)
        page.setProperty("helpKey", help_key)

        layout = QGridLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(8)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        title = QLabel()
        title.setObjectName("PageTitle")
        title.setProperty("i18nKey", title_key)
        title.setWordWrap(True)
        help_label = QLabel()
        help_label.setObjectName("PageHelp")
        help_label.setProperty("i18nKey", help_key)
        help_label.setWordWrap(True)

        layout.addWidget(title, 0, 0, 1, 2)
        layout.addWidget(help_label, 1, 0, 1, 2)
        return page, layout

    def _build_mssql_page(self) -> QFrame:
        page, layout = self._build_page_shell("section.mssql", "setup.mssql_help")
        row = 3
        row = self._add_form_row(layout, row, "database.server", "field.sql_server", self.server_edit)
        row = self._add_form_row(layout, row, "database.database", "field.database", self.database_edit)
        row = self._add_form_row(layout, row, "database.driver", "field.odbc_driver", self.driver_combo)
        row = self._add_form_row(layout, row, "database.auth_mode", "field.authentication", self.auth_combo)
        row = self._add_form_row(layout, row, "database.username", "field.sql_username", self.username_edit)
        row = self._add_form_row(layout, row, "database.password", "field.sql_password", self.password_edit)
        self._add_form_row(layout, row, "database.trust_server_certificate", "", self.trust_cert_check)
        return page

    def _build_api_page(self) -> QFrame:
        page, layout = self._build_page_shell("section.api", "setup.api_help")
        row = 3
        row = self._add_form_row(layout, row, "api.host", "field.bind_host", self.host_edit)
        row = self._add_form_row(layout, row, "api.port", "field.port", self.port_spin)
        layout.addWidget(self.port_hint_label, row, 1)
        row += 1
        layout.addWidget(self.port_status_label, row, 1)
        return page

    def _build_super_admin_page(self) -> QFrame:
        page, layout = self._build_page_shell("section.super_admin", "setup.admin_help")
        row = 3
        row = self._add_form_row(layout, row, "super_admin.username", "field.username", self.super_admin_username_edit)
        row = self._add_form_row(layout, row, "super_admin.full_name", "field.full_name", self.super_admin_full_name_edit)
        row = self._add_form_row(layout, row, "super_admin.current_password", "field.current_password", self.current_password_edit)
        row = self._add_form_row(layout, row, "super_admin.new_password", "field.new_password", self.new_password_edit)
        self._add_form_row(layout, row, "super_admin.confirm_password", "field.confirm_new_password", self.confirm_password_edit)
        return page

    def _add_form_row(
        self,
        layout: QGridLayout,
        row: int,
        field_id: str,
        label_key: str,
        widget: QWidget,
    ) -> int:
        title_label = QLabel()
        title_label.setObjectName("RowTitle")
        title_label.setProperty("i18nKey", label_key)
        if label_key:
            layout.addWidget(title_label, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
            self.field_labels[field_id] = title_label
        layout.addWidget(widget, row, 1)

        validation = QLabel()
        validation.setObjectName("ValidationMessage")
        validation.setWordWrap(True)
        validation.setVisible(False)
        layout.addWidget(validation, row + 1, 1)
        self.validation_labels[field_id] = validation
        return row + 2

    def _populate_language_combo(self) -> None:
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        for option in LANGUAGE_OPTIONS:
            self.language_combo.addItem(option.label, option.code)
        index = self.language_combo.findData(get_language())
        self.language_combo.setCurrentIndex(index if index >= 0 else 0)
        self.language_combo.blockSignals(False)

    def _set_auth_combo_items(self) -> None:
        current = self.auth_combo.currentData() or "windows"
        self.auth_combo.blockSignals(True)
        self.auth_combo.clear()
        self.auth_combo.addItem(tr("auth.windows"), "windows")
        self.auth_combo.addItem(tr("auth.sql"), "sql")
        index = self.auth_combo.findData(current)
        self.auth_combo.setCurrentIndex(index if index >= 0 else 0)
        self.auth_combo.blockSignals(False)

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

        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.auth_combo.currentIndexChanged.connect(self._sync_auth_fields)
        self.auth_combo.currentIndexChanged.connect(self._refresh_validation)
        self.back_button.clicked.connect(self._on_back)
        self.next_button.clicked.connect(self._on_next)
        self.submit_button.clicked.connect(self._on_submit)
        self.port_spin.valueChanged.connect(self._schedule_port_check)
        self.host_edit.textChanged.connect(self._schedule_port_check)
        self._port_check_timer.timeout.connect(self._update_port_status)

        for edit in (
            self.server_edit,
            self.database_edit,
            self.username_edit,
            self.password_edit,
            self.host_edit,
            self.current_password_edit,
            self.new_password_edit,
            self.confirm_password_edit,
        ):
            edit.textChanged.connect(self._refresh_validation)
        self.driver_combo.currentIndexChanged.connect(self._refresh_validation)
        self.trust_cert_check.stateChanged.connect(self._refresh_validation)

    def _on_language_changed(self, *_args: object) -> None:
        language = self.language_combo.currentData()
        if language:
            set_language(str(language))
            self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        """Apply active translations to all static setup text."""

        self.setWindowTitle(tr("setup.window_title"))
        self.title_label.setText(tr("app.title"))
        self.subtitle_label.setText(tr("setup.subtitle"))
        self.language_label.setText(tr("language.label"))
        self.card_title_label.setText(tr("setup.card_title"))
        self.setup_status_label.setText(tr(self._setup_status_key))
        self.back_button.setText(tr("common.back"))
        self.next_button.setText(tr("common.next"))
        self.submit_button.setText(tr("setup.create"))
        self.port_hint_label.setText(tr("setup.port_hint"))
        self.trust_cert_check.setText(tr("field.trust_certificate"))

        self.server_edit.setPlaceholderText("localhost\\SQLEXPRESS")
        self.database_edit.setPlaceholderText("ERPAccounting")
        self.username_edit.setPlaceholderText(tr("field.sql_username"))
        self.host_edit.setPlaceholderText("0.0.0.0")

        self._set_auth_combo_items()
        for label in self.field_labels.values():
            key = str(label.property("i18nKey") or "")
            label.setText(tr(key) if key else "")
        for page in (self.database_group, self.api_group, self.super_admin_group):
            for label in page.findChildren(QLabel):
                key = label.property("i18nKey")
                if key:
                    label.setText(tr(str(key)))
        self._update_stepper()
        if self._last_port_result is not None:
            self._apply_port_check_result(self._last_port_result)
        self._refresh_validation()
        self._apply_footer_button_sizing(self.width() < self.COMPACT_WIDTH)

    def _update_stepper(self) -> None:
        titles = [tr("section.mssql"), tr("section.api"), tr("section.super_admin")]
        for index, label in enumerate(self.step_labels):
            state = "current" if index == self._current_step else "done" if index < self._current_step else "upcoming"
            label.setText(
                f"{tr('setup.step_counter', current=index + 1, total=self.STEP_COUNT)}\n{titles[index]}"
            )
            label.setProperty("stepState", state)
            label.style().unpolish(label)
            label.style().polish(label)
            label.update()

    def _input_widgets(self) -> list[QWidget]:
        """Return all editable setup form controls."""

        return [
            self.server_edit,
            self.database_edit,
            self.driver_combo,
            self.auth_combo,
            self.username_edit,
            self.password_edit,
            self.trust_cert_check,
            self.host_edit,
            self.port_spin,
            self.current_password_edit,
            self.new_password_edit,
            self.confirm_password_edit,
        ]

    def _schedule_port_check(self, *_args: object) -> None:
        """Debounce live port availability checks while the user edits API settings."""

        if self._is_busy:
            return
        self._last_port_result = None
        self.port_status_label.setVisible(False)
        self._refresh_validation()
        self._port_check_timer.start()

    def _update_port_status(self) -> None:
        """Show whether the selected API port can be bound on this machine."""

        host = self.host_edit.text().strip() or "0.0.0.0"
        port = self.port_spin.value()
        self._apply_port_check_result(check_tcp_port(host, port))
        self._refresh_validation()

    def _apply_port_check_result(self, result: PortCheckResult) -> None:
        """Show the current port check result using the right visual state."""

        self._last_port_result = result
        state = "success" if result.available else "error"
        self._set_port_status(format_port_check_message(result), state)

    def _set_port_status(self, message: str, state: str) -> None:
        """Apply styled text to the live port status label."""

        self.port_status_label.setProperty("messageState", state)
        self.port_status_label.setText(message)
        self.port_status_label.setVisible(True)
        self.port_status_label.style().unpolish(self.port_status_label)
        self.port_status_label.style().polish(self.port_status_label)
        self.port_status_label.update()

    def _sync_auth_fields(self, *_args: object) -> None:
        """Enable SQL username/password only for SQL Login mode."""

        is_sql_login = self.auth_combo.currentData() == "sql"
        self.username_edit.setEnabled(is_sql_login and not self._is_busy)
        self.password_edit.setEnabled(is_sql_login and not self._is_busy)
        self._refresh_validation()

    def _set_validation_message(self, field_id: str, message: str) -> None:
        label = self.validation_labels.get(field_id)
        if label is None:
            return
        label.setText(message)
        label.setVisible(bool(message))

    def _step_errors(self, step_index: int) -> dict[str, str]:
        errors: dict[str, str] = {}

        if step_index == 0:
            if not self.server_edit.text().strip():
                errors["database.server"] = tr("setup.required", field=tr("field.sql_server"))
            database = self.database_edit.text().strip()
            if not database:
                errors["database.database"] = tr("setup.required", field=tr("field.database"))
            else:
                try:
                    validate_database_name(database)
                except ValueError as exc:
                    errors["database.database"] = tr("validation.database_name", message=str(exc))
            if not self.driver_combo.currentText().strip():
                errors["database.driver"] = tr("validation.odbc_driver_required")
            if self.auth_combo.currentData() == "sql":
                if not self.username_edit.text().strip():
                    errors["database.username"] = tr("validation.sql_username_required")
                if not self.password_edit.text():
                    errors["database.password"] = tr("validation.sql_password_required")

        elif step_index == 1:
            if not self.host_edit.text().strip():
                errors["api.host"] = tr("setup.required", field=tr("field.bind_host"))
            if not 1 <= self.port_spin.value() <= 65535:
                errors["api.port"] = tr("validation.api_port_range")
            elif self._last_port_result is not None and not self._last_port_result.available:
                errors["api.port"] = format_port_check_message(self._last_port_result)

        elif step_index == 2:
            new_password = self.new_password_edit.text()
            confirm_password = self.confirm_password_edit.text()
            if len(new_password) < 6:
                errors["super_admin.new_password"] = tr("validation.admin_password_length")
            if new_password and confirm_password and new_password != confirm_password:
                errors["super_admin.confirm_password"] = tr("validation.admin_password_match")
            elif new_password and not confirm_password:
                errors["super_admin.confirm_password"] = tr(
                    "setup.required",
                    field=tr("field.confirm_new_password"),
                )

        return errors

    def _refresh_validation(self, *_args: object) -> None:
        for label in self.validation_labels.values():
            label.setVisible(False)
            label.setText("")
        for field_id, message in self._step_errors(self._current_step).items():
            self._set_validation_message(field_id, message)
        self._refresh_navigation()

    def _is_step_valid(self, step_index: int) -> bool:
        return not self._step_errors(step_index)

    def _all_steps_valid(self) -> bool:
        return all(self._is_step_valid(index) for index in range(self.STEP_COUNT))

    def _refresh_navigation(self) -> None:
        if not hasattr(self, "wizard_stack"):
            return
        self.back_button.setVisible(self._current_step > 0)
        self.next_button.setVisible(self._current_step < self.STEP_COUNT - 1)
        self.submit_button.setVisible(self._current_step == self.STEP_COUNT - 1)
        self.back_button.setEnabled(not self._is_busy and self._current_step > 0)
        self.next_button.setEnabled(not self._is_busy and self._is_step_valid(self._current_step))
        self.submit_button.setEnabled(not self._is_busy and self._all_steps_valid())
        self._update_stepper()

    def _on_back(self, *_args: object) -> None:
        if self._current_step <= 0 or self._is_busy:
            return
        self._current_step -= 1
        self.wizard_stack.setCurrentIndex(self._current_step)
        self._refresh_validation()

    def _on_next(self, *_args: object) -> None:
        if self._is_busy:
            return
        if self._current_step == 1:
            self._update_port_status()
        if not self._is_step_valid(self._current_step):
            self._refresh_validation()
            return
        self._current_step = min(self._current_step + 1, self.STEP_COUNT - 1)
        self.wizard_stack.setCurrentIndex(self._current_step)
        self._refresh_validation()

    def set_busy(self, is_busy: bool, *, restore_status: bool = True) -> None:
        """Disable inputs while setup is running."""

        if is_busy and not self._is_busy:
            self._setup_status_before_busy = (
                self._setup_status_key,
                str(self.connection_card.property("serviceState") or "neutral"),
            )
            self._set_setup_status("setup.working", "neutral")
        elif not is_busy and self._is_busy and restore_status:
            previous_key, previous_state = self._setup_status_before_busy
            self._set_setup_status(previous_key, previous_state)

        self._is_busy = is_busy
        self.submit_button.setText(tr("setup.working") if is_busy else tr("setup.create"))
        self.language_combo.setDisabled(is_busy)

        for widget in self._input_widgets():
            widget.setDisabled(is_busy)
        self._sync_auth_fields()
        self._refresh_navigation()
        self._apply_footer_button_sizing(self.width() < self.COMPACT_WIDTH)

    def _set_setup_status(self, text_key: str, state: str) -> None:
        """Update the styled setup status badge and card state."""

        self._setup_status_key = text_key
        self.setup_status_label.setProperty("serviceState", state)
        self.setup_status_label.setText(tr(text_key))
        self.setup_status_label.style().unpolish(self.setup_status_label)
        self.setup_status_label.style().polish(self.setup_status_label)
        self.setup_status_label.update()

        self.connection_card.setProperty("serviceState", state)
        self.connection_card.style().unpolish(self.connection_card)
        self.connection_card.style().polish(self.connection_card)
        self.connection_card.update()

    def show_message(self, message: str, state: str = "info") -> None:
        """Show a styled footer message."""

        self.message_label.setProperty("messageState", state)
        self.message_label.setText(message)
        self.message_label.setVisible(bool(message))
        self.message_label.style().unpolish(self.message_label)
        self.message_label.style().polish(self.message_label)
        self.message_label.update()

    def show_error(self, message: str) -> None:
        """Show a recoverable setup error."""

        self.show_message(message, "error")
        self.set_busy(False, restore_status=False)
        self._set_setup_status("setup.failed", "error")

    def show_port_error(self, message: str) -> None:
        """Show a setup error caused by API bind settings."""

        self._set_port_status(message, "error")
        self.show_error(message)
        self._current_step = 1
        self.wizard_stack.setCurrentIndex(self._current_step)
        self._refresh_validation()

    def _on_submit(self) -> None:
        """Validate form values and emit a setup request."""

        try:
            config, current_password, new_password = self._build_config_from_form()
        except ValueError as exc:
            QMessageBox.warning(self, tr("setup.invalid_title"), str(exc))
            self._refresh_validation()
            return

        port_result = check_tcp_port(config.api.host, config.api.port)
        self._apply_port_check_result(port_result)
        if not port_result.available:
            QMessageBox.warning(
                self,
                tr("setup.port_unavailable_title"),
                format_port_check_message(port_result, include_diagnostic=True),
            )
            self._current_step = 1
            self.wizard_stack.setCurrentIndex(self._current_step)
            self._refresh_validation()
            return

        self.show_message(tr("setup.creating"), "info")
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
            raise ValueError(tr("setup.required", field=tr("field.sql_server")))
        if not database:
            raise ValueError(tr("setup.required", field=tr("field.database")))
        try:
            validate_database_name(database)
        except ValueError as exc:
            raise ValueError(tr("validation.database_name", message=str(exc))) from exc
        if not host:
            raise ValueError(tr("setup.required", field=tr("field.bind_host")))
        if auth_mode == "sql" and not self.username_edit.text().strip():
            raise ValueError(tr("validation.sql_username_required"))
        if auth_mode == "sql" and not self.password_edit.text():
            raise ValueError(tr("validation.sql_password_required"))
        if len(new_password) < 6:
            raise ValueError(tr("validation.admin_password_length"))
        if new_password != password_confirm:
            raise ValueError(tr("validation.admin_password_match"))

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

    def _apply_responsive_layout(self) -> None:
        """Reflow fixed shell controls and keep content readable across sizes."""

        compact = self.width() < self.COMPACT_WIDTH
        self._update_content_width(compact)
        self._reflow_header(compact)
        self._apply_footer_button_sizing(compact)
        if compact == self._is_compact_layout:
            return

        self._is_compact_layout = compact
        self.footer_layout.removeWidget(self.message_label)
        self.footer_layout.removeWidget(self.footer_controls)

        if compact:
            self.footer_layout.addWidget(self.message_label, 0, 0)
            self.footer_layout.addWidget(self.footer_controls, 1, 0)
            self.footer_layout.setColumnStretch(0, 1)
            self.footer_layout.setColumnStretch(1, 0)
        else:
            self.footer_layout.addWidget(self.message_label, 0, 0)
            self.footer_layout.addWidget(
                self.footer_controls,
                0,
                1,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
            self.footer_layout.setColumnStretch(0, 1)
            self.footer_layout.setColumnStretch(1, 0)

    def _reflow_header(self, compact: bool) -> None:
        """Keep the fixed header full-width and readable at each window size."""

        for widget in (self.header_title_block, self.header_language_block, self.connection_card):
            self.header_layout.removeWidget(widget)

        if compact:
            self.header_layout.addWidget(self.header_title_block, 0, 0, 1, 2)
            self.header_layout.addWidget(
                self.header_language_block,
                1,
                0,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            self.header_layout.addWidget(
                self.connection_card,
                1,
                1,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
            self.header_layout.setColumnStretch(0, 1)
            self.header_layout.setColumnStretch(1, 0)
            self.connection_card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.connection_card.setMinimumWidth(210)
            self.connection_card.setMaximumWidth(280)
            return

        self.header_layout.addWidget(
            self.header_title_block,
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self.header_layout.addWidget(
            self.header_language_block,
            0,
            1,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        self.header_layout.addWidget(
            self.connection_card,
            0,
            2,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        self.header_layout.setColumnStretch(0, 1)
        self.header_layout.setColumnStretch(1, 0)
        self.header_layout.setColumnStretch(2, 0)
        self.connection_card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.connection_card.setMinimumWidth(240)
        self.connection_card.setMaximumWidth(320)

    def _apply_footer_button_sizing(self, compact: bool) -> None:
        """Keep wizard buttons easy to hit without wasting wide-window space."""

        policy = QSizePolicy.Policy.Expanding if compact else QSizePolicy.Policy.Fixed
        self.footer_controls.setSizePolicy(policy, QSizePolicy.Policy.Fixed)
        for button in (self.back_button, self.next_button, self.submit_button):
            button.setSizePolicy(policy, QSizePolicy.Policy.Fixed)
            button.setMinimumWidth(0 if compact else max(110, button.sizeHint().width()))
            button.setMaximumWidth(16777215 if compact else max(110, button.sizeHint().width()))

    def _update_content_width(self, compact: bool) -> None:
        """Keep the form centered without letting it stretch too wide."""

        max_width = self.COMPACT_CONTENT_WIDTH if compact else self.MAX_CONTENT_WIDTH
        available_width = max(340, self.width() - 48)
        self.content_widget.setFixedWidth(min(max_width, available_width))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override name
        """Keep the setup wizard aligned as the desktop window resizes."""

        super().resizeEvent(event)
        self._apply_responsive_layout()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt override name
        """Re-apply layout once the window has its final size."""

        super().showEvent(event)
        self._apply_responsive_layout()
        self._update_port_status()

    def _apply_stylesheet(self) -> None:
        """Apply scoped styling for the first-run setup wizard."""

        self.setStyleSheet(
            """
            QWidget#SetupWindow {
                background: #f3f6fb;
                color: #182033;
                font-family: "Segoe UI", "Arial", sans-serif;
                font-size: 10.5pt;
            }
            QScrollArea#SetupScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#SetupScrollHost {
                background: #f3f6fb;
            }
            QWidget#SetupHeaderBar {
                background: #ffffff;
                border-bottom: 1px solid #dce4ef;
            }
            QLabel#SetupTitle {
                color: #111827;
                font-size: 26px;
                font-weight: 700;
            }
            QLabel#SetupSubtitle {
                color: #64748b;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#LanguageLabel {
                color: #64748b;
                font-size: 11px;
                font-weight: 700;
            }
            QFrame#WizardPage {
                background: #ffffff;
                border: 1px solid #dce4ef;
                border-radius: 8px;
            }
            QLabel#PageTitle {
                color: #111827;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#PageHelp {
                color: #64748b;
                font-size: 12px;
                font-weight: 500;
                margin-bottom: 10px;
            }
            QLabel#WizardStep {
                background: #ffffff;
                border: 1px solid #dce4ef;
                border-radius: 8px;
                color: #64748b;
                font-size: 11px;
                font-weight: 700;
                padding: 7px 8px;
            }
            QLabel#WizardStep[stepState="current"] {
                background: #eff6ff;
                border-color: #93c5fd;
                color: #1d4ed8;
            }
            QLabel#WizardStep[stepState="done"] {
                background: #ecfdf3;
                border-color: #bbf7d0;
                color: #167a3b;
            }
            QLabel#RowTitle {
                color: #475569;
                font-size: 12px;
                font-weight: 700;
                min-width: 160px;
                padding-top: 7px;
            }
            QLabel#ValidationMessage {
                color: #b42318;
                font-size: 11px;
                font-weight: 600;
                padding-bottom: 4px;
            }
            QLabel#PortHint {
                color: #94a3b8;
                font-size: 11px;
                font-weight: 500;
                padding-top: 2px;
            }
            QLabel#PortStatus {
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                padding: 7px 10px;
            }
            QLabel#PortStatus[messageState="success"] {
                background: #ecfdf3;
                border: 1px solid #bbf7d0;
                color: #167a3b;
            }
            QLabel#PortStatus[messageState="error"] {
                background: #fef2f2;
                border: 1px solid #fecaca;
                color: #b42318;
            }
            QLabel#ServiceStatus {
                border-radius: 14px;
                font-weight: 700;
                font-size: 14px;
                padding: 6px 16px;
                border: 1px solid transparent;
            }
            QLabel#ServiceStatus[serviceState="neutral"] {
                background: transparent;
                color: #475569;
                border-color: #cbd5e1;
            }
            QLabel#ServiceStatus[serviceState="error"] {
                background: transparent;
                color: #b42318;
                border-color: #fee2e2;
            }
            QFrame#ConnectionCard {
                background: #ffffff;
                border: 1px solid #dce4ef;
                border-radius: 8px;
            }
            QFrame#ConnectionCard[serviceState="neutral"] {
                background: #f8fafc;
                border-color: #cbd5e1;
            }
            QFrame#ConnectionCard[serviceState="error"] {
                background: #fef2f2;
                border-color: #fee2e2;
            }
            QWidget#ConnectionCardContent {
                background: transparent;
            }
            QFrame#ConnectionAccent {
                background-color: #2563eb;
                border: none;
                border-top-left-radius: 8px;
                border-bottom-left-radius: 8px;
            }
            QFrame#ConnectionCard[serviceState="error"] QFrame#ConnectionAccent {
                background-color: #dc2626;
            }
            QLabel#CardTitle {
                color: #334155;
                font-size: 15px;
                font-weight: 700;
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
                min-height: 36px;
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
                font-weight: 600;
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
            QLabel#FooterMessage {
                border-radius: 6px;
                font-weight: 700;
                padding: 9px 11px;
            }
            QLabel#FooterMessage[messageState="info"] {
                background: #eff6ff;
                border: 1px solid #bfdbfe;
                color: #1d4ed8;
            }
            QLabel#FooterMessage[messageState="success"] {
                background: #ecfdf3;
                border: 1px solid #bbf7d0;
                color: #167a3b;
            }
            QLabel#FooterMessage[messageState="error"] {
                background: #fef2f2;
                border: 1px solid #fecaca;
                color: #b42318;
            }
            QPushButton#PrimaryButton,
            QPushButton#SecondaryButton {
                border-radius: 7px;
                font-weight: 700;
                padding: 8px 18px;
            }
            QPushButton#PrimaryButton {
                background: #2563eb;
                border: 1px solid #1d4ed8;
                color: #ffffff;
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
            QPushButton#SecondaryButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                color: #1d4ed8;
            }
            QPushButton#SecondaryButton:hover {
                background: #eff6ff;
                border-color: #93c5fd;
            }
            QPushButton#SecondaryButton:disabled {
                background: #f1f5f9;
                color: #94a3b8;
            }
            """
        )

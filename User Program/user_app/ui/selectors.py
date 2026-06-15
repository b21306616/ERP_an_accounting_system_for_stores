"""Reusable searchable reference selectors for endpoint-client forms."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ReferenceSelectorDialog(QDialog):
    """Small searchable table dialog that returns one selected API row."""

    def __init__(
        self,
        title: str,
        rows: list[dict[str, Any]],
        columns: list[tuple[str, str]],
        *,
        search_placeholder: str = "Search",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rows = rows
        self._filtered_rows = rows
        self._columns = columns
        self._selected_row: dict[str, Any] | None = None
        self.setWindowTitle(title)
        self.setMinimumSize(640, 420)

        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(search_placeholder)
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)

        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels([header for _key, header in columns])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemDoubleClicked.connect(lambda _item: self._accept_current())
        layout.addWidget(self.table, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept_current)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._render_rows(rows)

    def selected_row(self) -> dict[str, Any] | None:
        """Return the selected API row after dialog acceptance."""

        return self._selected_row

    def _apply_filter(self, value: str) -> None:
        """Filter table rows by a case-insensitive text search."""

        needle = value.strip().casefold()
        if not needle:
            self._filtered_rows = self._rows
        else:
            self._filtered_rows = [row for row in self._rows if self._row_matches(row, needle)]
        self._render_rows(self._filtered_rows)

    def _row_matches(self, row: dict[str, Any], needle: str) -> bool:
        """Return true when the search string appears in any displayed column."""

        for key, _header in self._columns:
            value = row.get(key)
            if value is not None and needle in str(value).casefold():
                return True
        return False

    def _render_rows(self, rows: list[dict[str, Any]]) -> None:
        """Render rows into the table."""

        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, (key, _header) in enumerate(self._columns):
                item = QTableWidgetItem(str(row.get(key, "") or ""))
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(row_index, column_index, item)
        if rows:
            self.table.selectRow(0)
        self.table.resizeColumnsToContents()

    def _accept_current(self) -> None:
        """Accept the currently selected table row."""

        selected = self.table.selectedItems()
        if not selected:
            return
        row_index = selected[0].row()
        if 0 <= row_index < len(self._filtered_rows):
            self._selected_row = self._filtered_rows[row_index]
            self.accept()

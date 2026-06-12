"""Simulator-first hardware abstraction for cashier devices."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


class BarcodeScanner(Protocol):
    """Barcode scanner interface."""

    def scan(self, barcode: str) -> str:
        """Return the scanned barcode."""


class ReceiptPrinter(Protocol):
    """Receipt printer interface."""

    def print_receipt(self, lines: list[str]) -> str:
        """Print receipt lines and return a device message."""


class CashDrawer(Protocol):
    """Cash drawer interface."""

    def open_drawer(self) -> str:
        """Open the cash drawer and return a device message."""


class ScaleDevice(Protocol):
    """Scale interface."""

    def read_weight(self) -> Decimal:
        """Return the current weight in kilograms."""


class FiscalDevice(Protocol):
    """Fiscal-device interface."""

    def register_operation(self, amount: Decimal) -> str:
        """Register an operation and return a device message."""


@dataclass(slots=True)
class HardwareSimulator:
    """In-memory simulator for all cashier hardware interfaces."""

    last_barcode: str = "4600000000000"
    current_weight: Decimal = Decimal("1.000")
    printed_receipts: list[list[str]] = field(default_factory=list)
    drawer_open_count: int = 0
    fiscal_operations: list[Decimal] = field(default_factory=list)

    def scan(self, barcode: str | None = None) -> str:
        """Simulate scanner input."""

        if barcode:
            self.last_barcode = barcode
        return self.last_barcode

    def print_receipt(self, lines: list[str] | None = None) -> str:
        """Simulate receipt printing."""

        receipt_lines = lines or ["ERP Accounting", "Demo receipt", "Total: 0.00 TMT"]
        self.printed_receipts.append(receipt_lines)
        return f"Printed {len(receipt_lines)} receipt lines."

    def open_drawer(self) -> str:
        """Simulate opening the cash drawer."""

        self.drawer_open_count += 1
        return "Cash drawer opened."

    def read_weight(self) -> Decimal:
        """Simulate reading scale weight."""

        return self.current_weight

    def register_operation(self, amount: Decimal = Decimal("0.00")) -> str:
        """Simulate a fiscal-device operation."""

        self.fiscal_operations.append(amount)
        return f"Fiscal operation registered for {amount}."

"""Protocol interfaces for cashier hardware adapters."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class BarcodeScanner(Protocol):
    """Barcode scanner adapter contract."""

    def scan(self, barcode: str | None = None) -> str:
        """Return the scanned barcode."""


@runtime_checkable
class ReceiptPrinter(Protocol):
    """Receipt printer adapter contract."""

    def print_receipt(self, lines: list[str] | None = None) -> str:
        """Print receipt lines and return a device message."""


@runtime_checkable
class CashDrawer(Protocol):
    """Cash drawer adapter contract."""

    def open_drawer(self) -> str:
        """Open the cash drawer and return a device message."""


@runtime_checkable
class ScaleDevice(Protocol):
    """Scale adapter contract."""

    def read_weight(self) -> Decimal:
        """Return the current weight in kilograms."""


@runtime_checkable
class FiscalDevice(Protocol):
    """Fiscal-device adapter contract."""

    def register_operation(self, amount: Decimal = Decimal("0.00")) -> str:
        """Register a fiscal operation and return a device message."""


class HardwareAdapterError(RuntimeError):
    """Raised when a real hardware adapter cannot complete an operation."""

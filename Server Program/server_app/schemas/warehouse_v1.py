"""Schemas for API v1 warehouse endpoints."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class WarehouseCreate(BaseModel):
    """Create payload for a warehouse."""

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    """Update payload for a warehouse."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class StockDocumentLineCreate(BaseModel):
    """Common line payload for stock documents."""

    product_id: int
    uom_id: int | None = None
    quantity: Decimal = Field(gt=0)
    unit_cost_tmt: Decimal | None = Field(default=None, ge=0)


class StockTransferCreate(BaseModel):
    """Create payload for a transfer between two warehouses."""

    source_warehouse_id: int
    target_warehouse_id: int
    note: str | None = None
    lines: list[StockDocumentLineCreate] = Field(min_length=1)


class StockWriteoffCreate(BaseModel):
    """Create payload for a stock write-off document."""

    warehouse_id: int
    reason_code: str = Field(default="other", min_length=1, max_length=40)
    note: str | None = None
    lines: list[StockDocumentLineCreate] = Field(min_length=1)


class InventoryCountLine(BaseModel):
    """Counted inventory line."""

    product_id: int
    uom_id: int | None = None
    qty_actual: Decimal = Field(ge=0)
    unit_cost_tmt: Decimal | None = Field(default=None, ge=0)


class InventoryCreate(BaseModel):
    """Create payload for an inventory count."""

    warehouse_id: int
    note: str | None = None
    lines: list[InventoryCountLine] = Field(default_factory=list)


class InventoryLinesReplace(BaseModel):
    """Replace payload for counted inventory lines."""

    lines: list[InventoryCountLine] = Field(min_length=1)

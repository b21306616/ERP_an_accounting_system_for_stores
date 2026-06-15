"""Schemas for API v1 sales, cashier, and report endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class CashRegisterCreate(BaseModel):
    """Create payload for a cash register."""

    name: str = Field(min_length=1, max_length=100)
    warehouse_id: int
    is_active: bool = True


class CashShiftOpen(BaseModel):
    """Open-shift payload."""

    cash_register_id: int
    opening_amount: Decimal = Field(default=Decimal("0"), ge=0)


class CashShiftClose(BaseModel):
    """Close-shift payload."""

    closing_amount: Decimal = Field(ge=0)


class CashShiftZReportCreate(BaseModel):
    """Create a Z-report and optionally close the shift."""

    closing_amount: Decimal | None = Field(default=None, ge=0)
    close_shift: bool = True


class CashOperationCreate(BaseModel):
    """Create payload for a manual cash operation."""

    doc_number: str | None = Field(default=None, max_length=50)
    doc_date: datetime | None = None
    cash_shift_id: int
    cash_register_from_id: int
    cash_register_to_id: int | None = None
    operation_type: str = Field(pattern="^(collection|transfer)$")
    amount_tmt: Decimal = Field(gt=0)
    note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_transfer_target(self) -> "CashOperationCreate":
        """Transfers require a target register."""

        if self.operation_type == "transfer" and self.cash_register_to_id is None:
            raise ValueError("cash_register_to_id is required for transfer operations.")
        return self


class SaleLineCreate(BaseModel):
    """Create payload for one sale line."""

    line_type: str = Field(default="product", max_length=20)
    product_id: int | None = None
    service_id: int | None = None
    product_uom_id: int | None = None
    uom_id: int | None = None
    quantity: Decimal = Field(gt=0)
    price_list_price: Decimal | None = Field(default=None, ge=0)
    price_final: Decimal = Field(ge=0)
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    price_override: bool = False

    @model_validator(mode="after")
    def validate_target(self) -> "SaleLineCreate":
        """Require exactly one line target."""

        if (self.product_id is None) == (self.service_id is None):
            raise ValueError("Exactly one of product_id or service_id is required.")
        return self


class SaleCreate(BaseModel):
    """Create payload for a sale document."""

    doc_number: str | None = Field(default=None, max_length=50)
    doc_date: datetime | None = None
    sale_type: str = Field(pattern="^(retail|wholesale)$")
    cash_register_id: int | None = None
    cash_shift_id: int | None = None
    counterparty_id: int | None = None
    contract_id: int | None = None
    warehouse_id: int
    price_list_id: int | None = None
    currency_id: int
    currency_rate: Decimal = Field(default=Decimal("1"), gt=0)
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    discount_amount_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    payment_type: str = Field(pattern="^(cash|transfer|mixed|debt|bonus)$")
    paid_cash_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    paid_transfer_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    paid_bonus_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    debt_amount_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    loyalty_card_id: int | None = None
    lines: list[SaleLineCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_customer_requirements(self) -> "SaleCreate":
        """Wholesale and debt sales require a counterparty."""

        if self.sale_type == "wholesale" and self.counterparty_id is None:
            raise ValueError("counterparty_id is required for wholesale sales.")
        if self.payment_type == "debt" and self.counterparty_id is None:
            raise ValueError("counterparty_id is required for debt sales.")
        return self

class SaleReturnLineCreate(BaseModel):
    """Create payload for one sale-return line."""

    source_sale_line_id: int
    quantity: Decimal = Field(gt=0)
    price_final: Decimal | None = Field(default=None, ge=0)


class SaleReturnCreate(BaseModel):
    """Create payload for a customer sale return."""

    doc_number: str | None = Field(default=None, max_length=50)
    doc_date: datetime | None = None
    sale_id: int
    cash_register_id: int | None = None
    cash_shift_id: int | None = None
    refund_method: str = Field(pattern="^(cash|transfer|bonus|debt_correction|mixed)$")
    refund_cash_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    refund_transfer_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    refund_bonus_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    receivable_correction_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    note: str | None = Field(default=None, max_length=200)
    lines: list[SaleReturnLineCreate] = Field(min_length=1)


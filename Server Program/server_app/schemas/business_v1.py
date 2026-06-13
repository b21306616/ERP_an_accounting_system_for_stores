"""Schemas for API v1 pricing, purchase, and counterparty endpoints."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class CounterpartyCategoryCreate(BaseModel):
    """Create payload for a counterparty category."""

    name_ru: str = Field(min_length=1, max_length=100)
    name_tk: str | None = Field(default=None, max_length=100)


class CounterpartyCreate(BaseModel):
    """Create payload for a counterparty."""

    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=180)
    role_flags: int = Field(default=2, ge=1, le=3)
    category_id: int | None = None
    counterparty_type: str = Field(default="customer", max_length=40)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=120)
    tax_id: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=200)
    price_list_id: int | None = None
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    credit_limit_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    note: str | None = None
    is_active: bool = True


class CounterpartyUpdate(BaseModel):
    """Patch payload for a counterparty."""

    name: str | None = Field(default=None, min_length=1, max_length=180)
    role_flags: int | None = Field(default=None, ge=1, le=3)
    category_id: int | None = None
    counterparty_type: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=120)
    tax_id: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=200)
    price_list_id: int | None = None
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    credit_limit_tmt: Decimal | None = Field(default=None, ge=0)
    note: str | None = None
    is_active: bool | None = None


class PriceListCreate(BaseModel):
    """Create payload for a price list."""

    name_ru: str = Field(min_length=1, max_length=100)
    name_tk: str | None = Field(default=None, max_length=100)
    currency_id: int
    is_default: bool = False
    is_active: bool = True
    note: str | None = None


class PriceListItemCreate(BaseModel):
    """Create payload for a versioned price-list item."""

    product_id: int | None = None
    service_id: int | None = None
    product_uom_id: int | None = None
    uom_id: int | None = None
    price_tmt: Decimal = Field(gt=0)
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "PriceListItemCreate":
        """Require exactly one priced target."""

        if (self.product_id is None) == (self.service_id is None):
            raise ValueError("Exactly one of product_id or service_id is required.")
        return self


class PurchaseOrderLineCreate(BaseModel):
    """Create payload for a purchase order line."""

    product_id: int | None = None
    service_id: int | None = None
    expense_category_id: int | None = None
    product_uom_id: int | None = None
    uom_id: int | None = None
    quantity: Decimal = Field(gt=0)
    price_cur: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_target(self) -> "PurchaseOrderLineCreate":
        """Require exactly one line target."""

        if (self.product_id is None) == (self.service_id is None):
            raise ValueError("Exactly one of product_id or service_id is required.")
        if self.service_id is not None and self.expense_category_id is None:
            raise ValueError("expense_category_id is required for service purchase order lines.")
        return self


class PurchaseOrderCreate(BaseModel):
    """Create payload for a supplier purchase order."""

    doc_number: str | None = Field(default=None, max_length=50)
    doc_date: date | None = None
    counterparty_id: int
    warehouse_id: int
    currency_id: int
    currency_rate: Decimal = Field(default=Decimal("1"), gt=0)
    note: str | None = None
    lines: list[PurchaseOrderLineCreate] = Field(min_length=1)


class PurchaseOrderUpdate(BaseModel):
    """Replace editable fields and lines for an open purchase order."""

    doc_date: date | None = None
    counterparty_id: int | None = None
    warehouse_id: int | None = None
    currency_id: int | None = None
    currency_rate: Decimal | None = Field(default=None, gt=0)
    note: str | None = None
    lines: list[PurchaseOrderLineCreate] | None = Field(default=None, min_length=1)


class PurchaseInvoiceLineCreate(BaseModel):
    """Create payload for a purchase invoice line."""

    purchase_order_line_id: int | None = None
    product_id: int | None = None
    service_id: int | None = None
    expense_category_id: int | None = None
    product_uom_id: int | None = None
    uom_id: int | None = None
    quantity: Decimal = Field(gt=0)
    price_cur: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_target(self) -> "PurchaseInvoiceLineCreate":
        """Require exactly one line target."""

        if (self.product_id is None) == (self.service_id is None):
            raise ValueError("Exactly one of product_id or service_id is required.")
        if self.service_id is not None and self.expense_category_id is None:
            raise ValueError("expense_category_id is required for service purchase lines.")
        return self


class PurchaseInvoiceCreate(BaseModel):
    """Create payload for a purchase invoice."""

    doc_number: str | None = Field(default=None, max_length=50)
    doc_date: date | None = None
    counterparty_id: int
    warehouse_id: int
    currency_id: int
    currency_rate: Decimal = Field(default=Decimal("1"), gt=0)
    purchase_order_id: int | None = None
    expiry_note: str | None = Field(default=None, max_length=200)
    is_return: bool = False
    return_invoice_id: int | None = None
    note: str | None = None
    lines: list[PurchaseInvoiceLineCreate] = Field(min_length=1)


class PaymentAllocationCreate(BaseModel):
    """Payment allocation payload."""

    doc_type: str = Field(default="purchase_invoice", max_length=30)
    doc_id: int
    allocated_amount: Decimal = Field(gt=0)


class PaymentCreate(BaseModel):
    """Create payload for a payment document."""

    doc_number: str | None = Field(default=None, max_length=50)
    doc_date: datetime | None = None
    counterparty_id: int
    direction: str = Field(pattern="^(incoming|outgoing)$")
    payment_method: str = Field(default="cash", max_length=20)
    amount_tmt: Decimal = Field(gt=0)
    currency_id: int | None = None
    amount_cur: Decimal | None = Field(default=None, ge=0)
    currency_rate: Decimal | None = Field(default=None, gt=0)
    cash_shift_id: int | None = None
    note: str | None = None
    allocations: list[PaymentAllocationCreate] = Field(default_factory=list)

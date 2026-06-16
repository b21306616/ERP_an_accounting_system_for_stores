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


class ContractCreate(BaseModel):
    """Create payload for a counterparty contract."""

    counterparty_id: int
    currency_id: int | None = None
    number: str = Field(min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=180)
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_dates(self) -> "ContractCreate":
        """End date cannot be before start date."""

        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date.")
        return self


class ContractUpdate(BaseModel):
    """Patch payload for a counterparty contract."""

    currency_id: int | None = None
    number: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=180)
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None


class PriceListCreate(BaseModel):
    """Create payload for a price list."""

    name_ru: str = Field(min_length=1, max_length=100)
    name_tk: str | None = Field(default=None, max_length=100)
    currency_id: int
    is_default: bool = False
    is_active: bool = True
    note: str | None = None


class PriceListUpdate(BaseModel):
    """Patch payload for a price list."""

    name_ru: str | None = Field(default=None, min_length=1, max_length=100)
    name_tk: str | None = Field(default=None, max_length=100)
    currency_id: int | None = None
    is_default: bool | None = None
    is_active: bool | None = None
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


class PriceListItemUpdate(BaseModel):
    """Patch payload for a versioned price-list item."""

    product_id: int | None = None
    service_id: int | None = None
    product_uom_id: int | None = None
    uom_id: int | None = None
    price_tmt: Decimal | None = Field(default=None, gt=0)
    valid_from: date | None = None
    valid_to: date | None = None


class PriceListImportRow(BaseModel):
    """Import row for price-list prices."""

    product_id: int | None = None
    product_sku: str | None = Field(default=None, max_length=80)
    service_id: int | None = None
    service_code: str | None = Field(default=None, max_length=80)
    product_uom_id: int | None = None
    uom_id: int | None = None
    price_tmt: Decimal = Field(gt=0)
    valid_from: date
    valid_to: date | None = None


class PriceListImportPayload(BaseModel):
    """Import payload for price-list rows or a base64 XLSX workbook."""

    rows: list[PriceListImportRow] = Field(default_factory=list)
    xlsx_base64: str | None = None
    duplicate_mode: str = Field(default="add_version", pattern="^(add_version|skip|update)$")


class PromotionCreate(BaseModel):
    """Create payload for a sale promotion."""

    name: str = Field(min_length=1, max_length=160)
    promotion_type: str = Field(pattern="^(discount|gift)$")
    target_type: str = Field(default="product", pattern="^(product|group|all)$")
    product_id: int | None = None
    product_group_id: int | None = None
    discount_type: str | None = Field(default=None, pattern="^(percent|fixed_amount|fixed_price)$")
    discount_value: Decimal = Field(default=Decimal("0"), ge=0)
    min_quantity: Decimal = Field(default=Decimal("1"), gt=0)
    gift_product_id: int | None = None
    gift_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    valid_from: datetime
    valid_to: datetime | None = None
    is_active: bool = True
    note: str | None = None

    @model_validator(mode="after")
    def validate_rule(self) -> "PromotionCreate":
        """Require fields that match the promotion type and target."""

        if self.target_type == "product" and self.product_id is None:
            raise ValueError("product_id is required for product promotions.")
        if self.target_type == "group" and self.product_group_id is None:
            raise ValueError("product_group_id is required for group promotions.")
        if self.promotion_type == "discount" and self.discount_type is None:
            raise ValueError("discount_type is required for discount promotions.")
        if self.promotion_type == "gift" and (self.gift_product_id is None or self.gift_quantity <= 0):
            raise ValueError("gift_product_id and positive gift_quantity are required for gift promotions.")
        return self


class PromotionUpdate(BaseModel):
    """Patch payload for a sale promotion."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    promotion_type: str | None = Field(default=None, pattern="^(discount|gift)$")
    target_type: str | None = Field(default=None, pattern="^(product|group|all)$")
    product_id: int | None = None
    product_group_id: int | None = None
    discount_type: str | None = Field(default=None, pattern="^(percent|fixed_amount|fixed_price)$")
    discount_value: Decimal | None = Field(default=None, ge=0)
    min_quantity: Decimal | None = Field(default=None, gt=0)
    gift_product_id: int | None = None
    gift_quantity: Decimal | None = Field(default=None, ge=0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    is_active: bool | None = None
    note: str | None = None


class LoyaltySettingsUpdate(BaseModel):
    """Update global loyalty settings."""

    earn_rate_percent: Decimal = Field(ge=0, le=100)
    redemption_limit_percent: Decimal = Field(ge=0, le=100)
    is_active: bool = True
    note: str | None = None


class LoyaltyCardCreate(BaseModel):
    """Create payload for a loyalty card."""

    card_number: str = Field(min_length=1, max_length=80)
    counterparty_id: int | None = None
    owner_name: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=80)
    balance_tmt: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool = True
    note: str | None = None


class LoyaltyCardUpdate(BaseModel):
    """Patch payload for a loyalty card."""

    counterparty_id: int | None = None
    owner_name: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None
    note: str | None = None


class LoyaltyAdjustmentCreate(BaseModel):
    """Manual loyalty balance adjustment."""

    amount_tmt: Decimal
    note: str | None = Field(default=None, max_length=200)


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
    contract_id: int | None = None
    warehouse_id: int
    currency_id: int
    currency_rate: Decimal = Field(default=Decimal("1"), gt=0)
    note: str | None = None
    lines: list[PurchaseOrderLineCreate] = Field(min_length=1)


class PurchaseOrderUpdate(BaseModel):
    """Replace editable fields and lines for an open purchase order."""

    doc_date: date | None = None
    counterparty_id: int | None = None
    contract_id: int | None = None
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
    contract_id: int | None = None
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
    contract_id: int | None = None
    direction: str = Field(pattern="^(incoming|outgoing)$")
    payment_method: str = Field(default="cash", max_length=20)
    amount_tmt: Decimal = Field(gt=0)
    currency_id: int | None = None
    amount_cur: Decimal | None = Field(default=None, ge=0)
    currency_rate: Decimal | None = Field(default=None, gt=0)
    cash_shift_id: int | None = None
    note: str | None = None
    allocations: list[PaymentAllocationCreate] = Field(default_factory=list)

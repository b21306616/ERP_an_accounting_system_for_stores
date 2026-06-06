"""Foundation CRUD schemas for reference data."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from server_app.schemas.common import OrmModel


class CurrencyBase(BaseModel):
    """Common currency fields."""

    code: str = Field(min_length=3, max_length=3)
    name: str = Field(min_length=1, max_length=100)
    symbol: str | None = Field(default=None, max_length=12)
    is_system: bool = False
    is_active: bool = True


class CurrencyCreate(CurrencyBase):
    """Payload for creating a currency."""


class CurrencyUpdate(BaseModel):
    """Payload for updating a currency."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    symbol: str | None = Field(default=None, max_length=12)
    is_system: bool | None = None
    is_active: bool | None = None


class CurrencyRead(CurrencyBase, OrmModel):
    """Currency response."""

    id: int


class ExchangeRateBase(BaseModel):
    """Common exchange-rate fields."""

    currency_id: int
    rate_date: date
    rate_to_system: Decimal = Field(gt=0)


class ExchangeRateCreate(ExchangeRateBase):
    """Payload for creating an exchange rate."""


class ExchangeRateUpdate(BaseModel):
    """Payload for updating an exchange rate."""

    currency_id: int | None = None
    rate_date: date | None = None
    rate_to_system: Decimal | None = Field(default=None, gt=0)


class ExchangeRateRead(ExchangeRateBase, OrmModel):
    """Exchange-rate response."""

    id: int


class WarehouseBase(BaseModel):
    """Common warehouse fields."""

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class WarehouseCreate(WarehouseBase):
    """Payload for creating a warehouse."""


class WarehouseUpdate(BaseModel):
    """Payload for updating a warehouse."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class WarehouseRead(WarehouseBase, OrmModel):
    """Warehouse response."""

    id: int


class ProductBase(BaseModel):
    """Common product fields."""

    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    unit: str = Field(default="pcs", max_length=30)
    retail_price: Decimal = Field(default=Decimal("0"), ge=0)
    last_known_cost: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool = True


class ProductCreate(ProductBase):
    """Payload for creating a product."""


class ProductUpdate(BaseModel):
    """Payload for updating a product."""

    name: str | None = Field(default=None, min_length=1, max_length=180)
    unit: str | None = Field(default=None, max_length=30)
    retail_price: Decimal | None = Field(default=None, ge=0)
    last_known_cost: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductRead(ProductBase, OrmModel):
    """Product response."""

    id: int


class ProductSetItemBase(BaseModel):
    """Common product-set item fields."""

    product_id: int
    quantity: Decimal = Field(gt=0)


class ProductSetItemCreate(ProductSetItemBase):
    """Payload for adding a product to a set."""


class ProductSetItemRead(ProductSetItemBase, OrmModel):
    """Product-set item response."""

    id: int


class ProductSetBase(BaseModel):
    """Common product-set fields."""

    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    fixed_price: Decimal = Field(ge=0)
    is_active: bool = True


class ProductSetCreate(ProductSetBase):
    """Payload for creating a product set."""

    items: list[ProductSetItemCreate] = Field(default_factory=list)


class ProductSetUpdate(BaseModel):
    """Payload for updating a product set."""

    name: str | None = Field(default=None, min_length=1, max_length=180)
    fixed_price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    items: list[ProductSetItemCreate] | None = None


class ProductSetRead(ProductSetBase, OrmModel):
    """Product-set response with components."""

    id: int
    items: list[ProductSetItemRead] = Field(default_factory=list)


class CounterpartyBase(BaseModel):
    """Common counterparty fields."""

    name: str = Field(min_length=1, max_length=180)
    counterparty_type: str = Field(default="other", max_length=40)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=120)
    tax_id: str | None = Field(default=None, max_length=80)
    is_active: bool = True


class CounterpartyCreate(CounterpartyBase):
    """Payload for creating a counterparty."""


class CounterpartyUpdate(BaseModel):
    """Payload for updating a counterparty."""

    name: str | None = Field(default=None, min_length=1, max_length=180)
    counterparty_type: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=120)
    tax_id: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None


class CounterpartyRead(CounterpartyBase, OrmModel):
    """Counterparty response."""

    id: int


class ContractBase(BaseModel):
    """Common contract fields."""

    counterparty_id: int
    currency_id: int | None = None
    number: str = Field(min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=180)
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool = True


class ContractCreate(ContractBase):
    """Payload for creating a contract."""


class ContractUpdate(BaseModel):
    """Payload for updating a contract."""

    currency_id: int | None = None
    title: str | None = Field(default=None, max_length=180)
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None


class ContractRead(ContractBase, OrmModel):
    """Contract response."""

    id: int


class MoneyAccountBase(BaseModel):
    """Common cash or bank account fields."""

    currency_id: int
    name: str = Field(min_length=1, max_length=140)
    account_type: str = Field(max_length=40)
    details: str | None = None
    is_active: bool = True


class MoneyAccountCreate(MoneyAccountBase):
    """Payload for creating a money account."""


class MoneyAccountUpdate(BaseModel):
    """Payload for updating a money account."""

    currency_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=140)
    account_type: str | None = Field(default=None, max_length=40)
    details: str | None = None
    is_active: bool | None = None


class MoneyAccountRead(MoneyAccountBase, OrmModel):
    """Money-account response."""

    id: int

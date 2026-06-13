"""Schemas for API v1 product catalog endpoints."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class ProductGroupCreate(BaseModel):
    """Create payload for a product group."""

    code: str = Field(min_length=1, max_length=50)
    name_ru: str = Field(min_length=1, max_length=180)
    name_tk: str | None = Field(default=None, max_length=180)
    parent_id: int | None = None
    sort_order: int = 0
    is_active: bool = True


class ProductGroupUpdate(BaseModel):
    """Update payload for a product group."""

    name_ru: str | None = Field(default=None, min_length=1, max_length=180)
    name_tk: str | None = Field(default=None, max_length=180)
    parent_id: int | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class UnitOfMeasureCreate(BaseModel):
    """Create payload for a unit of measure."""

    code: str = Field(min_length=1, max_length=30)
    name_ru: str = Field(min_length=1, max_length=120)
    name_tk: str | None = Field(default=None, max_length=120)
    is_active: bool = True


class UnitOfMeasureUpdate(BaseModel):
    """Update payload for a unit of measure."""

    name_ru: str | None = Field(default=None, min_length=1, max_length=120)
    name_tk: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None


class ProductCreate(BaseModel):
    """Create payload for a product."""

    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    name_tk: str | None = Field(default=None, max_length=180)
    group_id: int | None = None
    base_uom_id: int | None = None
    product_type: str = Field(default="standard", max_length=40)
    unit: str = Field(default="pcs", max_length=30)
    retail_price: Decimal = Field(default=Decimal("0"), ge=0)
    last_known_cost: Decimal = Field(default=Decimal("0"), ge=0)
    min_stock: Decimal = Field(default=Decimal("0"), ge=0)
    description: str | None = None
    is_active: bool = True


class ProductUpdate(BaseModel):
    """Update payload for a product."""

    name: str | None = Field(default=None, min_length=1, max_length=180)
    name_tk: str | None = Field(default=None, max_length=180)
    group_id: int | None = None
    base_uom_id: int | None = None
    product_type: str | None = Field(default=None, max_length=40)
    unit: str | None = Field(default=None, max_length=30)
    retail_price: Decimal | None = Field(default=None, ge=0)
    last_known_cost: Decimal | None = Field(default=None, ge=0)
    min_stock: Decimal | None = Field(default=None, ge=0)
    description: str | None = None
    is_active: bool | None = None


class ProductBarcodeCreate(BaseModel):
    """Create payload for a product barcode."""

    barcode: str = Field(min_length=1, max_length=80)
    product_uom_id: int | None = None
    is_weight_barcode: bool = False


class ExpenseCategoryCreate(BaseModel):
    """Create payload for an expense category."""

    code: str = Field(min_length=1, max_length=50)
    name_ru: str = Field(min_length=1, max_length=160)
    name_tk: str | None = Field(default=None, max_length=160)
    is_active: bool = True


class ExpenseCategoryUpdate(BaseModel):
    """Update payload for an expense category."""

    name_ru: str | None = Field(default=None, min_length=1, max_length=160)
    name_tk: str | None = Field(default=None, max_length=160)
    is_active: bool | None = None


class ServiceCreate(BaseModel):
    """Create payload for a service."""

    code: str = Field(min_length=1, max_length=80)
    name_ru: str = Field(min_length=1, max_length=180)
    name_tk: str | None = Field(default=None, max_length=180)
    service_type: str = Field(default="sale", max_length=40)
    expense_category_id: int | None = None
    default_price: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool = True


class ServiceUpdate(BaseModel):
    """Update payload for a service."""

    name_ru: str | None = Field(default=None, min_length=1, max_length=180)
    name_tk: str | None = Field(default=None, max_length=180)
    service_type: str | None = Field(default=None, max_length=40)
    expense_category_id: int | None = None
    default_price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ServiceBarcodeCreate(BaseModel):
    """Create payload for a service barcode."""

    barcode: str = Field(min_length=1, max_length=80)

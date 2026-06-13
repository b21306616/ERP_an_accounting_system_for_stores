"""SQLAlchemy ORM models for the server Foundation MVP."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server_app.db.base import Base, ReprMixin, TimestampMixin


class Role(Base, ReprMixin, TimestampMixin):
    """Built-in access role such as Super Admin, Accountant, Manager, Cashier, Auditor."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="role")
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )


class Permission(Base, ReprMixin, TimestampMixin):
    """Action permission such as ``sale.create`` or ``reports.export``."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission",
        cascade="all, delete-orphan",
    )


class RolePermission(Base, ReprMixin):
    """Permission assigned to one role."""

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), nullable=False)

    role: Mapped[Role] = relationship(back_populates="role_permissions")
    permission: Mapped[Permission] = relationship(back_populates="role_permissions")


class Workplace(Base, ReprMixin, TimestampMixin):
    """Client workplace assigned to users and cashier devices."""

    __tablename__ = "workplaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    workplace_type: Mapped[str] = mapped_column(String(40), default="office", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="workplace")


class User(Base, ReprMixin, TimestampMixin):
    """Application user allowed to authenticate from a future client endpoint."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    workplace_id: Mapped[int | None] = mapped_column(ForeignKey("workplaces.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    role: Mapped[Role] = relationship(back_populates="users")
    workplace: Mapped[Workplace | None] = relationship(back_populates="users")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user")


class UserSession(Base, ReprMixin, TimestampMixin):
    """Opaque API v1 session token issued to an endpoint client."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    client_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class AuditLog(Base, ReprMixin):
    """Minimal audit trail for security and administrative events."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    module: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User | None] = relationship(back_populates="audit_logs")


class Setting(Base, ReprMixin, TimestampMixin):
    """System setting stored as JSON text for organization and feature config."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Currency(Base, ReprMixin, TimestampMixin):
    """Currency used by prices, contracts, accounts, and exchange rates."""

    __tablename__ = "currencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(12), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    exchange_rates: Mapped[list["ExchangeRate"]] = relationship(back_populates="currency")
    contracts: Mapped[list["Contract"]] = relationship(back_populates="currency")
    money_accounts: Mapped[list["MoneyAccount"]] = relationship(back_populates="currency")


class ExchangeRate(Base, ReprMixin, TimestampMixin):
    """Historical exchange rate to the system currency for a specific date."""

    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("currency_id", "rate_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate_to_system: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    currency: Mapped[Currency] = relationship(back_populates="exchange_rates")


class Warehouse(Base, ReprMixin, TimestampMixin):
    """Storage location used for inventory balances."""

    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    stock_balances: Mapped[list["StockBalance"]] = relationship(back_populates="warehouse")


class ProductGroup(Base, ReprMixin, TimestampMixin):
    """Hierarchical product group used by catalogs and reports."""

    __tablename__ = "product_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("product_groups.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name_ru: Mapped[str] = mapped_column(String(180), nullable=False)
    name_tk: Mapped[str | None] = mapped_column(String(180), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parent: Mapped["ProductGroup | None"] = relationship(remote_side="ProductGroup.id")
    products: Mapped[list["Product"]] = relationship(back_populates="group")


class UnitOfMeasure(Base, ReprMixin, TimestampMixin):
    """Unit of measure such as piece, kilogram, or package."""

    __tablename__ = "unit_of_measures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name_ru: Mapped[str] = mapped_column(String(120), nullable=False)
    name_tk: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    products: Mapped[list["Product"]] = relationship(back_populates="base_uom")


class Product(Base, ReprMixin, TimestampMixin):
    """Stock item that can later participate in purchases, sales, and sets."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    name_tk: Mapped[str | None] = mapped_column(String(180), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("product_groups.id"), nullable=True)
    base_uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    product_type: Mapped[str] = mapped_column(String(40), default="standard", nullable=False)
    unit: Mapped[str] = mapped_column(String(30), default="pcs", nullable=False)
    retail_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    last_known_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    min_stock: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=0, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    group: Mapped[ProductGroup | None] = relationship(back_populates="products")
    base_uom: Mapped[UnitOfMeasure | None] = relationship(back_populates="products")
    set_items: Mapped[list["ProductSetItem"]] = relationship(back_populates="product")
    uoms: Mapped[list["ProductUom"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
    barcodes: Mapped[list["ProductBarcode"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )


class ProductUom(Base, ReprMixin):
    """Additional unit of measure for a product with conversion coefficient."""

    __tablename__ = "product_uoms"
    __table_args__ = (UniqueConstraint("product_id", "uom_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    uom_id: Mapped[int] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=False)
    coefficient: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=1, nullable=False)
    is_base: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product: Mapped[Product] = relationship(back_populates="uoms")
    uom: Mapped[UnitOfMeasure] = relationship()


class ProductBarcode(Base, ReprMixin):
    """Barcode linked to a product and optionally to a product UOM."""

    __tablename__ = "product_barcodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_uom_id: Mapped[int | None] = mapped_column(ForeignKey("product_uoms.id"), nullable=True)
    barcode: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    is_weight_barcode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product: Mapped[Product] = relationship(back_populates="barcodes")
    product_uom: Mapped[ProductUom | None] = relationship()


class ProductSet(Base, ReprMixin, TimestampMixin):
    """Bundle sold as one line while components are deducted from stock."""

    __tablename__ = "product_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    fixed_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    items: Mapped[list["ProductSetItem"]] = relationship(
        back_populates="product_set",
        cascade="all, delete-orphan",
    )


class ProductSetItem(Base, ReprMixin):
    """Component line inside a product set."""

    __tablename__ = "product_set_items"
    __table_args__ = (UniqueConstraint("product_set_id", "product_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_set_id: Mapped[int] = mapped_column(ForeignKey("product_sets.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)

    product_set: Mapped[ProductSet] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="set_items")


class Counterparty(Base, ReprMixin, TimestampMixin):
    """Customer, supplier, or other business partner."""

    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    counterparty_type: Mapped[str] = mapped_column(String(40), default="other", nullable=False)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    contracts: Mapped[list["Contract"]] = relationship(back_populates="counterparty")


class Contract(Base, ReprMixin, TimestampMixin):
    """Universal contract used for customer, supplier, and other settlements."""

    __tablename__ = "contracts"
    __table_args__ = (UniqueConstraint("counterparty_id", "number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"), nullable=False)
    currency_id: Mapped[int | None] = mapped_column(ForeignKey("currencies.id"), nullable=True)
    number: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str | None] = mapped_column(String(180), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    counterparty: Mapped[Counterparty] = relationship(back_populates="contracts")
    currency: Mapped[Currency | None] = relationship(back_populates="contracts")


class MoneyAccount(Base, ReprMixin, TimestampMixin):
    """Cash desk or bank account used for Cash Flow reporting."""

    __tablename__ = "money_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    account_type: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    currency: Mapped[Currency] = relationship(back_populates="money_accounts")


class ExpenseCategory(Base, ReprMixin, TimestampMixin):
    """Expense category used by service purchases and operating expenses."""

    __tablename__ = "expense_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name_ru: Mapped[str] = mapped_column(String(160), nullable=False)
    name_tk: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    services: Mapped[list["Service"]] = relationship(back_populates="expense_category")


class Service(Base, ReprMixin, TimestampMixin):
    """Service or non-stock item that can appear in sale/purchase documents."""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name_ru: Mapped[str] = mapped_column(String(180), nullable=False)
    name_tk: Mapped[str | None] = mapped_column(String(180), nullable=True)
    service_type: Mapped[str] = mapped_column(String(40), default="sale", nullable=False)
    expense_category_id: Mapped[int | None] = mapped_column(ForeignKey("expense_categories.id"), nullable=True)
    default_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    expense_category: Mapped[ExpenseCategory | None] = relationship(back_populates="services")
    barcodes: Mapped[list["ServiceBarcode"]] = relationship(
        back_populates="service",
        cascade="all, delete-orphan",
    )


class ServiceBarcode(Base, ReprMixin):
    """Barcode linked to a service."""

    __tablename__ = "service_barcodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    barcode: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)

    service: Mapped[Service] = relationship(back_populates="barcodes")


class StockBalance(Base, ReprMixin, TimestampMixin):
    """Current stock balance for one product at one warehouse."""

    __tablename__ = "stock_balances"
    __table_args__ = (UniqueConstraint("warehouse_id", "product_id", "uom_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=0, nullable=False)
    avg_cost_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)

    warehouse: Mapped[Warehouse] = relationship(back_populates="stock_balances")
    product: Mapped[Product] = relationship()
    uom: Mapped[UnitOfMeasure | None] = relationship()


class StockMovement(Base, ReprMixin):
    """Immutable stock movement journal row."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    movement_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_cost_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    movement_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    warehouse: Mapped[Warehouse] = relationship()
    product: Mapped[Product] = relationship()
    uom: Mapped[UnitOfMeasure | None] = relationship()
    created_by_user: Mapped[User | None] = relationship()


class StockTransfer(Base, ReprMixin, TimestampMixin):
    """Two-step transfer between warehouses."""

    __tablename__ = "stock_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    target_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sent_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    received_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    rejected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_warehouse: Mapped[Warehouse] = relationship(foreign_keys=[source_warehouse_id])
    target_warehouse: Mapped[Warehouse] = relationship(foreign_keys=[target_warehouse_id])
    lines: Mapped[list["StockTransferLine"]] = relationship(
        back_populates="transfer",
        cascade="all, delete-orphan",
    )


class StockTransferLine(Base, ReprMixin):
    """Line inside a warehouse transfer."""

    __tablename__ = "stock_transfer_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("stock_transfers.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_cost_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)

    transfer: Mapped[StockTransfer] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
    uom: Mapped[UnitOfMeasure | None] = relationship()


class StockWriteoff(Base, ReprMixin, TimestampMixin):
    """Warehouse write-off document."""

    __tablename__ = "stock_writeoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), default="other", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    warehouse: Mapped[Warehouse] = relationship()
    lines: Mapped[list["StockWriteoffLine"]] = relationship(
        back_populates="writeoff",
        cascade="all, delete-orphan",
    )


class StockWriteoffLine(Base, ReprMixin):
    """Line inside a warehouse write-off."""

    __tablename__ = "stock_writeoff_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    writeoff_id: Mapped[int] = mapped_column(ForeignKey("stock_writeoffs.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_cost_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)

    writeoff: Mapped[StockWriteoff] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
    uom: Mapped[UnitOfMeasure | None] = relationship()


class Inventory(Base, ReprMixin, TimestampMixin):
    """Inventory count document for one warehouse."""

    __tablename__ = "inventories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    warehouse: Mapped[Warehouse] = relationship()
    lines: Mapped[list["InventoryLine"]] = relationship(
        back_populates="inventory",
        cascade="all, delete-orphan",
    )


class InventoryLine(Base, ReprMixin):
    """Line inside an inventory count."""

    __tablename__ = "inventory_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventories.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    qty_expected: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=0, nullable=False)
    qty_actual: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    unit_cost_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)

    inventory: Mapped[Inventory] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
    uom: Mapped[UnitOfMeasure | None] = relationship()


class InventoryRevision(Base, ReprMixin, TimestampMixin):
    """Future lock point preventing older inventory and finance edits."""

    __tablename__ = "inventory_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    revision_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    warehouse: Mapped[Warehouse] = relationship()
    posted_by_user: Mapped[User | None] = relationship()

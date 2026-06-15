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
    report_filters: Mapped[list["ReportFilter"]] = relationship(back_populates="created_by_user")


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


class ReportFilter(Base, ReprMixin, TimestampMixin):
    """Saved report filter preset visible to the owner or shared with all users."""

    __tablename__ = "report_filters"
    __table_args__ = (UniqueConstraint("report_code", "name", "created_by_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    created_by_user: Mapped[User | None] = relationship(back_populates="report_filters")


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
    cash_registers: Mapped[list["CashRegister"]] = relationship(back_populates="warehouse")


class CashRegister(Base, ReprMixin, TimestampMixin):
    """Cash register/workplace bound to one warehouse."""

    __tablename__ = "cash_registers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    warehouse: Mapped[Warehouse] = relationship(back_populates="cash_registers")
    shifts: Mapped[list["CashShift"]] = relationship(back_populates="cash_register")
    sales: Mapped[list["Sale"]] = relationship(back_populates="cash_register")


class CashShift(Base, ReprMixin):
    """Cashier shift opened on one cash register."""

    __tablename__ = "cash_shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cash_register_id: Mapped[int] = mapped_column(ForeignKey("cash_registers.id"), nullable=False, index=True)
    opened_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opening_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    closing_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open", nullable=False, index=True)

    cash_register: Mapped[CashRegister] = relationship(back_populates="shifts")
    opened_by_user: Mapped[User | None] = relationship(foreign_keys=[opened_by_user_id])
    closed_by_user: Mapped[User | None] = relationship(foreign_keys=[closed_by_user_id])
    sales: Mapped[list["Sale"]] = relationship(back_populates="cash_shift")
    cash_operations: Mapped[list["CashOperation"]] = relationship(back_populates="cash_shift")


class CashOperation(Base, ReprMixin, TimestampMixin):
    """Manual cash collection or transfer inside a shift."""

    __tablename__ = "cash_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    doc_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cash_shift_id: Mapped[int] = mapped_column(ForeignKey("cash_shifts.id"), nullable=False)
    cash_register_from_id: Mapped[int] = mapped_column(ForeignKey("cash_registers.id"), nullable=False)
    cash_register_to_id: Mapped[int | None] = mapped_column(ForeignKey("cash_registers.id"), nullable=True)
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    cash_shift: Mapped[CashShift] = relationship(back_populates="cash_operations")
    cash_register_from: Mapped[CashRegister] = relationship(foreign_keys=[cash_register_from_id])
    cash_register_to: Mapped[CashRegister | None] = relationship(foreign_keys=[cash_register_to_id])
    created_by_user: Mapped[User | None] = relationship()


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
    code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("counterparty_categories.id"), nullable=True)
    counterparty_type: Mapped[str] = mapped_column(String(40), default="other", nullable=False)
    role_flags: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    price_list_id: Mapped[int | None] = mapped_column(ForeignKey("price_lists.id"), nullable=True)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    credit_limit_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped["CounterpartyCategory | None"] = relationship(back_populates="counterparties")
    price_list: Mapped["PriceList | None"] = relationship(back_populates="counterparties")
    contracts: Mapped[list["Contract"]] = relationship(back_populates="counterparty")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="counterparty")
    purchase_invoices: Mapped[list["PurchaseInvoice"]] = relationship(back_populates="counterparty")
    sales: Mapped[list["Sale"]] = relationship(back_populates="counterparty")
    sale_returns: Mapped[list["SaleReturn"]] = relationship(back_populates="counterparty")
    loyalty_cards: Mapped[list["LoyaltyCard"]] = relationship(back_populates="counterparty")
    debt_entries: Mapped[list["DebtLedger"]] = relationship(back_populates="counterparty")
    payments: Mapped[list["Payment"]] = relationship(back_populates="counterparty")


class CounterpartyCategory(Base, ReprMixin, TimestampMixin):
    """Optional grouping for counterparties."""

    __tablename__ = "counterparty_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(100), nullable=False)
    name_tk: Mapped[str | None] = mapped_column(String(100), nullable=True)

    counterparties: Mapped[list[Counterparty]] = relationship(back_populates="category")


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
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="contract")
    purchase_invoices: Mapped[list["PurchaseInvoice"]] = relationship(back_populates="contract")
    sales: Mapped[list["Sale"]] = relationship(back_populates="contract")
    payments: Mapped[list["Payment"]] = relationship(back_populates="contract")
    debt_entries: Mapped[list["DebtLedger"]] = relationship(back_populates="contract")


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


class PriceList(Base, ReprMixin, TimestampMixin):
    """Versioned price list header."""

    __tablename__ = "price_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(100), nullable=False)
    name_tk: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    currency: Mapped[Currency] = relationship()
    items: Mapped[list["PriceListItem"]] = relationship(
        back_populates="price_list",
        cascade="all, delete-orphan",
    )
    counterparties: Mapped[list[Counterparty]] = relationship(back_populates="price_list")
    sales: Mapped[list["Sale"]] = relationship(back_populates="price_list")


class PriceListItem(Base, ReprMixin, TimestampMixin):
    """Versioned price for one product or service."""

    __tablename__ = "price_list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_list_id: Mapped[int] = mapped_column(ForeignKey("price_lists.id"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    product_uom_id: Mapped[int | None] = mapped_column(ForeignKey("product_uoms.id"), nullable=True)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    price_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    price_list: Mapped[PriceList] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()
    service: Mapped[Service | None] = relationship()
    product_uom: Mapped[ProductUom | None] = relationship()
    uom: Mapped[UnitOfMeasure | None] = relationship()


class Promotion(Base, ReprMixin, TimestampMixin):
    """Promotion rule that can discount sale lines or add a gift line."""

    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    promotion_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), default="product", nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    product_group_id: Mapped[int | None] = mapped_column(ForeignKey("product_groups.id"), nullable=True)
    discount_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    min_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=1, nullable=False)
    gift_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    gift_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped[Product | None] = relationship(foreign_keys=[product_id])
    product_group: Mapped[ProductGroup | None] = relationship()
    gift_product: Mapped[Product | None] = relationship(foreign_keys=[gift_product_id])


class LoyaltySetting(Base, ReprMixin, TimestampMixin):
    """Global loyalty-program settings."""

    __tablename__ = "loyalty_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    earn_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    redemption_limit_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class LoyaltyCard(Base, ReprMixin, TimestampMixin):
    """Customer loyalty card with a TMT-denominated bonus balance."""

    __tablename__ = "loyalty_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_number: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    counterparty_id: Mapped[int | None] = mapped_column(ForeignKey("counterparties.id"), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    balance_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    counterparty: Mapped[Counterparty | None] = relationship(back_populates="loyalty_cards")
    transactions: Mapped[list["LoyaltyTransaction"]] = relationship(
        back_populates="loyalty_card",
        cascade="all, delete-orphan",
    )
    sales: Mapped[list["Sale"]] = relationship(back_populates="loyalty_card")


class LoyaltyTransaction(Base, ReprMixin):
    """Append-only bonus movement journal."""

    __tablename__ = "loyalty_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loyalty_card_id: Mapped[int] = mapped_column(ForeignKey("loyalty_cards.id"), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    doc_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    doc_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    loyalty_card: Mapped[LoyaltyCard] = relationship(back_populates="transactions")
    created_by_user: Mapped[User | None] = relationship()


class PurchaseOrder(Base, ReprMixin, TimestampMixin):
    """Supplier purchase order tracked through invoice receiving."""

    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    doc_date: Mapped[date] = mapped_column(Date, nullable=False)
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"), nullable=False)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=1, nullable=False)
    total_amount_cur: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sent_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    counterparty: Mapped[Counterparty] = relationship(back_populates="purchase_orders")
    contract: Mapped[Contract | None] = relationship(back_populates="purchase_orders")
    warehouse: Mapped[Warehouse] = relationship()
    currency: Mapped[Currency] = relationship()
    created_by_user: Mapped[User | None] = relationship(foreign_keys=[created_by_user_id])
    sent_by_user: Mapped[User | None] = relationship(foreign_keys=[sent_by_user_id])
    cancelled_by_user: Mapped[User | None] = relationship(foreign_keys=[cancelled_by_user_id])
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )
    invoices: Mapped[list["PurchaseInvoice"]] = relationship(back_populates="purchase_order")


class PurchaseOrderLine(Base, ReprMixin):
    """Product or service line requested from a supplier."""

    __tablename__ = "purchase_order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    expense_category_id: Mapped[int | None] = mapped_column(ForeignKey("expense_categories.id"), nullable=True)
    product_uom_id: Mapped[int | None] = mapped_column(ForeignKey("product_uoms.id"), nullable=True)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    price_cur: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    price_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount_cur: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
    product: Mapped[Product | None] = relationship()
    service: Mapped[Service | None] = relationship()
    expense_category: Mapped[ExpenseCategory | None] = relationship()
    product_uom: Mapped[ProductUom | None] = relationship()
    uom: Mapped[UnitOfMeasure | None] = relationship()
    invoice_lines: Mapped[list["PurchaseInvoiceLine"]] = relationship(back_populates="purchase_order_line")


class PurchaseInvoice(Base, ReprMixin, TimestampMixin):
    """Purchase invoice that can post stock and payable debt."""

    __tablename__ = "purchase_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    doc_date: Mapped[date] = mapped_column(Date, nullable=False)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), nullable=True)
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"), nullable=False)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=1, nullable=False)
    total_amount_cur: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid", nullable=False)
    expiry_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_return: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    return_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_invoices.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    counterparty: Mapped[Counterparty] = relationship(back_populates="purchase_invoices")
    contract: Mapped[Contract | None] = relationship(back_populates="purchase_invoices")
    purchase_order: Mapped[PurchaseOrder | None] = relationship(back_populates="invoices")
    warehouse: Mapped[Warehouse] = relationship()
    currency: Mapped[Currency] = relationship()
    return_invoice: Mapped["PurchaseInvoice | None"] = relationship(remote_side="PurchaseInvoice.id")
    lines: Mapped[list["PurchaseInvoiceLine"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class PurchaseInvoiceLine(Base, ReprMixin):
    """Product or service line inside a purchase invoice."""

    __tablename__ = "purchase_invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_invoice_id: Mapped[int] = mapped_column(ForeignKey("purchase_invoices.id"), nullable=False)
    purchase_order_line_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_lines.id"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    expense_category_id: Mapped[int | None] = mapped_column(ForeignKey("expense_categories.id"), nullable=True)
    product_uom_id: Mapped[int | None] = mapped_column(ForeignKey("product_uoms.id"), nullable=True)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    price_cur: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    price_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount_cur: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    avg_cost_before: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    avg_cost_after: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    invoice: Mapped[PurchaseInvoice] = relationship(back_populates="lines")
    purchase_order_line: Mapped[PurchaseOrderLine | None] = relationship(back_populates="invoice_lines")
    product: Mapped[Product | None] = relationship()
    service: Mapped[Service | None] = relationship()
    expense_category: Mapped[ExpenseCategory | None] = relationship()
    product_uom: Mapped[ProductUom | None] = relationship()
    uom: Mapped[UnitOfMeasure | None] = relationship()


class Sale(Base, ReprMixin, TimestampMixin):
    """Retail or wholesale sale document."""

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    doc_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sale_type: Mapped[str] = mapped_column(String(10), nullable=False)
    cash_register_id: Mapped[int | None] = mapped_column(ForeignKey("cash_registers.id"), nullable=True)
    cash_shift_id: Mapped[int | None] = mapped_column(ForeignKey("cash_shifts.id"), nullable=True)
    counterparty_id: Mapped[int | None] = mapped_column(ForeignKey("counterparties.id"), nullable=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    price_list_id: Mapped[int | None] = mapped_column(ForeignKey("price_lists.id"), nullable=True)
    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=1, nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    discount_amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    paid_cash_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    paid_transfer_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    paid_bonus_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    debt_amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    loyalty_card_id: Mapped[int | None] = mapped_column(ForeignKey("loyalty_cards.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    admin_override_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cash_register: Mapped[CashRegister | None] = relationship(back_populates="sales")
    cash_shift: Mapped[CashShift | None] = relationship(back_populates="sales")
    counterparty: Mapped[Counterparty | None] = relationship(back_populates="sales")
    contract: Mapped[Contract | None] = relationship(back_populates="sales")
    warehouse: Mapped[Warehouse] = relationship()
    price_list: Mapped[PriceList | None] = relationship(back_populates="sales")
    currency: Mapped[Currency] = relationship()
    loyalty_card: Mapped[LoyaltyCard | None] = relationship(back_populates="sales")
    admin_override_by_user: Mapped[User | None] = relationship(foreign_keys=[admin_override_by_user_id])
    created_by_user: Mapped[User | None] = relationship(foreign_keys=[created_by_user_id])
    posted_by_user: Mapped[User | None] = relationship(foreign_keys=[posted_by_user_id])
    cancelled_by_user: Mapped[User | None] = relationship(foreign_keys=[cancelled_by_user_id])
    lines: Mapped[list["SaleLine"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
    )
    returns: Mapped[list["SaleReturn"]] = relationship(back_populates="sale")


class SaleLine(Base, ReprMixin):
    """Product or service line inside a sale."""

    __tablename__ = "sale_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), nullable=False)
    line_type: Mapped[str] = mapped_column(String(20), default="product", nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    product_uom_id: Mapped[int | None] = mapped_column(ForeignKey("product_uoms.id"), nullable=True)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    price_list_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    price_final: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    avg_cost_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    promo_id: Mapped[int | None] = mapped_column(ForeignKey("promotions.id"), nullable=True)
    parent_line_id: Mapped[int | None] = mapped_column(ForeignKey("sale_lines.id"), nullable=True)
    price_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sale: Mapped[Sale] = relationship(back_populates="lines")
    product: Mapped[Product | None] = relationship()
    service: Mapped[Service | None] = relationship()
    product_uom: Mapped[ProductUom | None] = relationship()
    uom: Mapped[UnitOfMeasure | None] = relationship()
    promotion: Mapped[Promotion | None] = relationship()
    parent_line: Mapped["SaleLine | None"] = relationship(remote_side="SaleLine.id")
    return_lines: Mapped[list["SaleReturnLine"]] = relationship(back_populates="source_sale_line")


class SaleReturn(Base, ReprMixin, TimestampMixin):
    """Customer return document that restores stock and can correct receivables."""

    __tablename__ = "sale_returns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    doc_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), nullable=False)
    cash_register_id: Mapped[int | None] = mapped_column(ForeignKey("cash_registers.id"), nullable=True)
    cash_shift_id: Mapped[int | None] = mapped_column(ForeignKey("cash_shifts.id"), nullable=True)
    counterparty_id: Mapped[int | None] = mapped_column(ForeignKey("counterparties.id"), nullable=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=1, nullable=False)
    total_amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    refund_method: Mapped[str] = mapped_column(String(20), nullable=False)
    refund_cash_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    refund_transfer_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    refund_bonus_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    receivable_correction_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sale: Mapped[Sale] = relationship(back_populates="returns")
    cash_register: Mapped[CashRegister | None] = relationship()
    cash_shift: Mapped[CashShift | None] = relationship()
    counterparty: Mapped[Counterparty | None] = relationship(back_populates="sale_returns")
    warehouse: Mapped[Warehouse] = relationship()
    currency: Mapped[Currency] = relationship()
    created_by_user: Mapped[User | None] = relationship(foreign_keys=[created_by_user_id])
    posted_by_user: Mapped[User | None] = relationship(foreign_keys=[posted_by_user_id])
    cancelled_by_user: Mapped[User | None] = relationship(foreign_keys=[cancelled_by_user_id])
    lines: Mapped[list["SaleReturnLine"]] = relationship(
        back_populates="sale_return",
        cascade="all, delete-orphan",
    )


class SaleReturnLine(Base, ReprMixin):
    """Line returned against one original sale line."""

    __tablename__ = "sale_return_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_return_id: Mapped[int] = mapped_column(ForeignKey("sale_returns.id"), nullable=False)
    source_sale_line_id: Mapped[int] = mapped_column(ForeignKey("sale_lines.id"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    product_uom_id: Mapped[int | None] = mapped_column(ForeignKey("product_uoms.id"), nullable=True)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measures.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    price_final: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    avg_cost_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, nullable=False)

    sale_return: Mapped[SaleReturn] = relationship(back_populates="lines")
    source_sale_line: Mapped[SaleLine] = relationship(back_populates="return_lines")
    product: Mapped[Product | None] = relationship()
    service: Mapped[Service | None] = relationship()
    product_uom: Mapped[ProductUom | None] = relationship()
    uom: Mapped[UnitOfMeasure | None] = relationship()


class DebtLedger(Base, ReprMixin):
    """Append-only receivable/payable ledger."""

    __tablename__ = "debt_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"), nullable=False)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)
    debt_type: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False)
    doc_number: Mapped[str] = mapped_column(String(50), nullable=False)
    doc_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_id: Mapped[int | None] = mapped_column(ForeignKey("currencies.id"), nullable=True)
    amount_cur: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    counterparty: Mapped[Counterparty] = relationship(back_populates="debt_entries")
    contract: Mapped[Contract | None] = relationship(back_populates="debt_entries")
    currency: Mapped[Currency | None] = relationship()
    created_by_user: Mapped[User | None] = relationship()


class Payment(Base, ReprMixin, TimestampMixin):
    """Payment document that reduces receivable or payable debt."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    doc_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"), nullable=False)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), default="cash", nullable=False)
    amount_tmt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_id: Mapped[int | None] = mapped_column(ForeignKey("currencies.id"), nullable=True)
    amount_cur: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    cash_shift_id: Mapped[int | None] = mapped_column(ForeignKey("cash_shifts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="posted", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    counterparty: Mapped[Counterparty] = relationship(back_populates="payments")
    contract: Mapped[Contract | None] = relationship(back_populates="payments")
    currency: Mapped[Currency | None] = relationship()
    cash_shift: Mapped[CashShift | None] = relationship()
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class PaymentAllocation(Base, ReprMixin):
    """Optional allocation of a payment to a source document."""

    __tablename__ = "payment_allocations"
    __table_args__ = (UniqueConstraint("payment_id", "doc_type", "doc_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    payment: Mapped[Payment] = relationship(back_populates="allocations")

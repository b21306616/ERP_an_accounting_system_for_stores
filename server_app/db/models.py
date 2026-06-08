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


class User(Base, ReprMixin, TimestampMixin):
    """Application user allowed to authenticate from a future client endpoint."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    role: Mapped[Role] = relationship(back_populates="users")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")


class AuditLog(Base, ReprMixin):
    """Minimal audit trail for security and administrative events."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User | None] = relationship(back_populates="audit_logs")


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


class Product(Base, ReprMixin, TimestampMixin):
    """Stock item that can later participate in purchases, sales, and sets."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), default="pcs", nullable=False)
    retail_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    last_known_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    set_items: Mapped[list["ProductSetItem"]] = relationship(back_populates="product")


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

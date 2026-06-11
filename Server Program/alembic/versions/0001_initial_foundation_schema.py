"""Initial foundation schema.

Revision ID: 0001_initial_foundation_schema
Revises:
Create Date: 2026-06-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_foundation_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the foundation tables needed by the server MVP."""

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
    )
    op.create_index(op.f("ix_roles_name"), "roles", ["name"], unique=False)

    op.create_table(
        "currencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("symbol", sa.String(length=12), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_currencies")),
        sa.UniqueConstraint("code", name=op.f("uq_currencies_code")),
    )
    op.create_index(op.f("ix_currencies_code"), "currencies", ["code"], unique=False)

    op.create_table(
        "counterparties",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("counterparty_type", sa.String(length=40), server_default="other", nullable=False),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("tax_id", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_counterparties")),
    )
    op.create_index(op.f("ix_counterparties_name"), "counterparties", ["name"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("unit", sa.String(length=30), server_default="pcs", nullable=False),
        sa.Column("retail_price", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("last_known_cost", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("sku", name=op.f("uq_products_sku")),
    )
    op.create_index(op.f("ix_products_sku"), "products", ["sku"], unique=False)

    op.create_table(
        "product_sets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("fixed_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_sets")),
        sa.UniqueConstraint("code", name=op.f("uq_product_sets_code")),
    )
    op.create_index(op.f("ix_product_sets_code"), "product_sets", ["code"], unique=False)

    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_warehouses")),
        sa.UniqueConstraint("code", name=op.f("uq_warehouses_code")),
    )
    op.create_index(op.f("ix_warehouses_code"), "warehouses", ["code"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_users_role_id_roles")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=False)

    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), nullable=False),
        sa.Column("currency_id", sa.Integer(), nullable=True),
        sa.Column("number", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"], name=op.f("fk_contracts_counterparty_id_counterparties")),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"], name=op.f("fk_contracts_currency_id_currencies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contracts")),
        sa.UniqueConstraint("counterparty_id", "number", name=op.f("uq_contracts_counterparty_id")),
    )

    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("currency_id", sa.Integer(), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("rate_to_system", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"], name=op.f("fk_exchange_rates_currency_id_currencies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exchange_rates")),
        sa.UniqueConstraint("currency_id", "rate_date", name=op.f("uq_exchange_rates_currency_id")),
    )

    op.create_table(
        "money_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("currency_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("account_type", sa.String(length=40), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"], name=op.f("fk_money_accounts_currency_id_currencies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_money_accounts")),
    )

    op.create_table(
        "product_set_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_set_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_product_set_items_product_id_products")),
        sa.ForeignKeyConstraint(["product_set_id"], ["product_sets.id"], name=op.f("fk_product_set_items_product_set_id_product_sets")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_set_items")),
        sa.UniqueConstraint("product_set_id", "product_id", name=op.f("uq_product_set_items_product_set_id")),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_name", sa.String(length=120), nullable=True),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_audit_logs_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )

    op.create_table(
        "inventory_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("revision_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], name=op.f("fk_inventory_revisions_posted_by_user_id_users")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name=op.f("fk_inventory_revisions_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_revisions")),
    )


def downgrade() -> None:
    """Drop the foundation tables in dependency order."""

    op.drop_table("inventory_revisions")
    op.drop_table("audit_logs")
    op.drop_table("product_set_items")
    op.drop_table("money_accounts")
    op.drop_table("exchange_rates")
    op.drop_table("contracts")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_warehouses_code"), table_name="warehouses")
    op.drop_table("warehouses")
    op.drop_index(op.f("ix_product_sets_code"), table_name="product_sets")
    op.drop_table("product_sets")
    op.drop_index(op.f("ix_products_sku"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_counterparties_name"), table_name="counterparties")
    op.drop_table("counterparties")
    op.drop_index(op.f("ix_currencies_code"), table_name="currencies")
    op.drop_table("currencies")
    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_table("roles")

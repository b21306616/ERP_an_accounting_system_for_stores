"""Add sales and cashier foundation tables.

Revision ID: 0006_sales_cashier_reports
Revises: 0005_pricing_purchase
Create Date: 2026-06-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_sales_cashier_reports"
down_revision = "0005_pricing_purchase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create sales, cashier, and cash-operation tables."""

    op.create_table(
        "cash_registers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name=op.f("fk_cash_registers_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cash_registers")),
    )

    op.create_table(
        "cash_shifts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cash_register_id", sa.Integer(), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opening_amount", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("closing_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="open", nullable=False),
        sa.ForeignKeyConstraint(["cash_register_id"], ["cash_registers.id"], name=op.f("fk_cash_shifts_cash_register_id_cash_registers")),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"], name=op.f("fk_cash_shifts_closed_by_user_id_users")),
        sa.ForeignKeyConstraint(["opened_by_user_id"], ["users.id"], name=op.f("fk_cash_shifts_opened_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cash_shifts")),
    )
    op.create_index(op.f("ix_cash_shifts_cash_register_id"), "cash_shifts", ["cash_register_id"], unique=False)
    op.create_index(op.f("ix_cash_shifts_status"), "cash_shifts", ["status"], unique=False)

    op.add_column("payments", sa.Column("cash_shift_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_payments_cash_shift_id_cash_shifts"),
        "payments",
        "cash_shifts",
        ["cash_shift_id"],
        ["id"],
    )

    op.create_table(
        "cash_operations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_number", sa.String(length=50), nullable=False),
        sa.Column("doc_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cash_shift_id", sa.Integer(), nullable=False),
        sa.Column("cash_register_from_id", sa.Integer(), nullable=False),
        sa.Column("cash_register_to_id", sa.Integer(), nullable=True),
        sa.Column("operation_type", sa.String(length=20), nullable=False),
        sa.Column("amount_tmt", sa.Numeric(18, 2), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["cash_register_from_id"], ["cash_registers.id"], name=op.f("fk_cash_operations_cash_register_from_id_cash_registers")),
        sa.ForeignKeyConstraint(["cash_register_to_id"], ["cash_registers.id"], name=op.f("fk_cash_operations_cash_register_to_id_cash_registers")),
        sa.ForeignKeyConstraint(["cash_shift_id"], ["cash_shifts.id"], name=op.f("fk_cash_operations_cash_shift_id_cash_shifts")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_cash_operations_created_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cash_operations")),
        sa.UniqueConstraint("doc_number", name=op.f("uq_cash_operations_doc_number")),
    )
    op.create_index(op.f("ix_cash_operations_doc_number"), "cash_operations", ["doc_number"], unique=False)

    op.create_table(
        "sales",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_number", sa.String(length=50), nullable=False),
        sa.Column("doc_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sale_type", sa.String(length=10), nullable=False),
        sa.Column("cash_register_id", sa.Integer(), nullable=True),
        sa.Column("cash_shift_id", sa.Integer(), nullable=True),
        sa.Column("counterparty_id", sa.Integer(), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("price_list_id", sa.Integer(), nullable=True),
        sa.Column("currency_id", sa.Integer(), nullable=False),
        sa.Column("currency_rate", sa.Numeric(18, 6), server_default="1", nullable=False),
        sa.Column("discount_percent", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("discount_amount_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("total_amount_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("payment_type", sa.String(length=20), nullable=False),
        sa.Column("paid_cash_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("paid_transfer_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("paid_bonus_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("debt_amount_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("loyalty_card_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("admin_override_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["admin_override_by_user_id"], ["users.id"], name=op.f("fk_sales_admin_override_by_user_id_users")),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], name=op.f("fk_sales_cancelled_by_user_id_users")),
        sa.ForeignKeyConstraint(["cash_register_id"], ["cash_registers.id"], name=op.f("fk_sales_cash_register_id_cash_registers")),
        sa.ForeignKeyConstraint(["cash_shift_id"], ["cash_shifts.id"], name=op.f("fk_sales_cash_shift_id_cash_shifts")),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"], name=op.f("fk_sales_counterparty_id_counterparties")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_sales_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"], name=op.f("fk_sales_currency_id_currencies")),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], name=op.f("fk_sales_posted_by_user_id_users")),
        sa.ForeignKeyConstraint(["price_list_id"], ["price_lists.id"], name=op.f("fk_sales_price_list_id_price_lists")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name=op.f("fk_sales_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales")),
        sa.UniqueConstraint("doc_number", name=op.f("uq_sales_doc_number")),
    )
    op.create_index(op.f("ix_sales_doc_number"), "sales", ["doc_number"], unique=False)

    op.create_table(
        "sale_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("line_type", sa.String(length=20), server_default="product", nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("product_uom_id", sa.Integer(), nullable=True),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("price_list_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("price_final", sa.Numeric(18, 4), nullable=False),
        sa.Column("discount_percent", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("discount_amount", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("amount_tmt", sa.Numeric(18, 2), nullable=False),
        sa.Column("avg_cost_tmt", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("promo_id", sa.Integer(), nullable=True),
        sa.Column("parent_line_id", sa.Integer(), nullable=True),
        sa.Column("price_override", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(["parent_line_id"], ["sale_lines.id"], name=op.f("fk_sale_lines_parent_line_id_sale_lines")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_sale_lines_product_id_products")),
        sa.ForeignKeyConstraint(["product_uom_id"], ["product_uoms.id"], name=op.f("fk_sale_lines_product_uom_id_product_uoms")),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name=op.f("fk_sale_lines_sale_id_sales")),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name=op.f("fk_sale_lines_service_id_services")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_sale_lines_uom_id_unit_of_measures")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_lines")),
    )


def downgrade() -> None:
    """Drop sales and cashier foundation tables."""

    op.drop_table("sale_lines")
    op.drop_index(op.f("ix_sales_doc_number"), table_name="sales")
    op.drop_table("sales")
    op.drop_index(op.f("ix_cash_operations_doc_number"), table_name="cash_operations")
    op.drop_table("cash_operations")
    op.drop_constraint(op.f("fk_payments_cash_shift_id_cash_shifts"), "payments", type_="foreignkey")
    op.drop_column("payments", "cash_shift_id")
    op.drop_index(op.f("ix_cash_shifts_status"), table_name="cash_shifts")
    op.drop_index(op.f("ix_cash_shifts_cash_register_id"), table_name="cash_shifts")
    op.drop_table("cash_shifts")
    op.drop_table("cash_registers")

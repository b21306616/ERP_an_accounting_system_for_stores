"""Add purchase orders and sale returns.

Revision ID: 0007_document_lifecycle
Revises: 0006_sales_cashier_reports
Create Date: 2026-06-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_document_lifecycle"
down_revision = "0006_sales_cashier_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create document lifecycle tables and links."""

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_number", sa.String(length=50), nullable=False),
        sa.Column("doc_date", sa.Date(), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("currency_id", sa.Integer(), nullable=False),
        sa.Column("currency_rate", sa.Numeric(18, 6), server_default="1", nullable=False),
        sa.Column("total_amount_cur", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("total_amount_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("sent_by_user_id", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], name=op.f("fk_purchase_orders_cancelled_by_user_id_users")),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"], name=op.f("fk_purchase_orders_counterparty_id_counterparties")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_purchase_orders_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"], name=op.f("fk_purchase_orders_currency_id_currencies")),
        sa.ForeignKeyConstraint(["sent_by_user_id"], ["users.id"], name=op.f("fk_purchase_orders_sent_by_user_id_users")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name=op.f("fk_purchase_orders_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_orders")),
        sa.UniqueConstraint("doc_number", name=op.f("uq_purchase_orders_doc_number")),
    )
    op.create_index(op.f("ix_purchase_orders_doc_number"), "purchase_orders", ["doc_number"], unique=False)

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("expense_category_id", sa.Integer(), nullable=True),
        sa.Column("product_uom_id", sa.Integer(), nullable=True),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("quantity_ordered", sa.Numeric(18, 4), nullable=False),
        sa.Column("quantity_received", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("price_cur", sa.Numeric(18, 4), nullable=False),
        sa.Column("price_tmt", sa.Numeric(18, 4), nullable=False),
        sa.Column("amount_cur", sa.Numeric(18, 2), nullable=False),
        sa.Column("amount_tmt", sa.Numeric(18, 2), nullable=False),
        sa.ForeignKeyConstraint(["expense_category_id"], ["expense_categories.id"], name=op.f("fk_purchase_order_lines_expense_category_id_expense_categories")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_purchase_order_lines_product_id_products")),
        sa.ForeignKeyConstraint(["product_uom_id"], ["product_uoms.id"], name=op.f("fk_purchase_order_lines_product_uom_id_product_uoms")),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], name=op.f("fk_purchase_order_lines_purchase_order_id_purchase_orders")),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name=op.f("fk_purchase_order_lines_service_id_services")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_purchase_order_lines_uom_id_unit_of_measures")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_order_lines")),
    )

    op.create_foreign_key(
        op.f("fk_purchase_invoices_purchase_order_id_purchase_orders"),
        "purchase_invoices",
        "purchase_orders",
        ["purchase_order_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_purchase_invoice_lines_purchase_order_line_id_purchase_order_lines"),
        "purchase_invoice_lines",
        "purchase_order_lines",
        ["purchase_order_line_id"],
        ["id"],
    )

    op.create_table(
        "sale_returns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_number", sa.String(length=50), nullable=False),
        sa.Column("doc_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("cash_register_id", sa.Integer(), nullable=True),
        sa.Column("cash_shift_id", sa.Integer(), nullable=True),
        sa.Column("counterparty_id", sa.Integer(), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("currency_id", sa.Integer(), nullable=False),
        sa.Column("currency_rate", sa.Numeric(18, 6), server_default="1", nullable=False),
        sa.Column("total_amount_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("refund_method", sa.String(length=20), nullable=False),
        sa.Column("refund_cash_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("refund_transfer_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("receivable_correction_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], name=op.f("fk_sale_returns_cancelled_by_user_id_users")),
        sa.ForeignKeyConstraint(["cash_register_id"], ["cash_registers.id"], name=op.f("fk_sale_returns_cash_register_id_cash_registers")),
        sa.ForeignKeyConstraint(["cash_shift_id"], ["cash_shifts.id"], name=op.f("fk_sale_returns_cash_shift_id_cash_shifts")),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"], name=op.f("fk_sale_returns_counterparty_id_counterparties")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_sale_returns_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"], name=op.f("fk_sale_returns_currency_id_currencies")),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], name=op.f("fk_sale_returns_posted_by_user_id_users")),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name=op.f("fk_sale_returns_sale_id_sales")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name=op.f("fk_sale_returns_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_returns")),
        sa.UniqueConstraint("doc_number", name=op.f("uq_sale_returns_doc_number")),
    )
    op.create_index(op.f("ix_sale_returns_doc_number"), "sale_returns", ["doc_number"], unique=False)

    op.create_table(
        "sale_return_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sale_return_id", sa.Integer(), nullable=False),
        sa.Column("source_sale_line_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("product_uom_id", sa.Integer(), nullable=True),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("price_final", sa.Numeric(18, 4), nullable=False),
        sa.Column("amount_tmt", sa.Numeric(18, 2), nullable=False),
        sa.Column("avg_cost_tmt", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_sale_return_lines_product_id_products")),
        sa.ForeignKeyConstraint(["product_uom_id"], ["product_uoms.id"], name=op.f("fk_sale_return_lines_product_uom_id_product_uoms")),
        sa.ForeignKeyConstraint(["sale_return_id"], ["sale_returns.id"], name=op.f("fk_sale_return_lines_sale_return_id_sale_returns")),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name=op.f("fk_sale_return_lines_service_id_services")),
        sa.ForeignKeyConstraint(["source_sale_line_id"], ["sale_lines.id"], name=op.f("fk_sale_return_lines_source_sale_line_id_sale_lines")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_sale_return_lines_uom_id_unit_of_measures")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_return_lines")),
    )


def downgrade() -> None:
    """Drop document lifecycle tables and links."""

    op.drop_table("sale_return_lines")
    op.drop_index(op.f("ix_sale_returns_doc_number"), table_name="sale_returns")
    op.drop_table("sale_returns")
    op.drop_constraint(op.f("fk_purchase_invoice_lines_purchase_order_line_id_purchase_order_lines"), "purchase_invoice_lines", type_="foreignkey")
    op.drop_constraint(op.f("fk_purchase_invoices_purchase_order_id_purchase_orders"), "purchase_invoices", type_="foreignkey")
    op.drop_table("purchase_order_lines")
    op.drop_index(op.f("ix_purchase_orders_doc_number"), table_name="purchase_orders")
    op.drop_table("purchase_orders")

"""Add pricing, purchase, and counterparty settlement layer.

Revision ID: 0005_pricing_purchase
Revises: 0004_warehouse_layer
Create Date: 2026-06-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_pricing_purchase"
down_revision = "0004_warehouse_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create price, purchase, debt, and payment tables."""

    op.create_table(
        "counterparty_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name_ru", sa.String(length=100), nullable=False),
        sa.Column("name_tk", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_counterparty_categories")),
    )

    op.create_table(
        "price_lists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name_ru", sa.String(length=100), nullable=False),
        sa.Column("name_tk", sa.String(length=100), nullable=True),
        sa.Column("currency_id", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"], name=op.f("fk_price_lists_currency_id_currencies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_lists")),
    )

    op.add_column("counterparties", sa.Column("code", sa.String(length=50), nullable=True))
    op.add_column("counterparties", sa.Column("category_id", sa.Integer(), nullable=True))
    op.add_column("counterparties", sa.Column("role_flags", sa.Integer(), server_default="2", nullable=False))
    op.add_column("counterparties", sa.Column("address", sa.String(length=200), nullable=True))
    op.add_column("counterparties", sa.Column("price_list_id", sa.Integer(), nullable=True))
    op.add_column("counterparties", sa.Column("discount_percent", sa.Numeric(5, 2), server_default="0", nullable=False))
    op.add_column("counterparties", sa.Column("credit_limit_tmt", sa.Numeric(18, 2), server_default="0", nullable=False))
    op.add_column("counterparties", sa.Column("note", sa.Text(), nullable=True))
    op.create_index(op.f("ix_counterparties_code"), "counterparties", ["code"], unique=True)
    op.create_foreign_key(
        op.f("fk_counterparties_category_id_counterparty_categories"),
        "counterparties",
        "counterparty_categories",
        ["category_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_counterparties_price_list_id_price_lists"),
        "counterparties",
        "price_lists",
        ["price_list_id"],
        ["id"],
    )

    op.create_table(
        "price_list_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("price_list_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("product_uom_id", sa.Integer(), nullable=True),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("price_tmt", sa.Numeric(18, 4), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["price_list_id"], ["price_lists.id"], name=op.f("fk_price_list_items_price_list_id_price_lists")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_price_list_items_product_id_products")),
        sa.ForeignKeyConstraint(["product_uom_id"], ["product_uoms.id"], name=op.f("fk_price_list_items_product_uom_id_product_uoms")),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name=op.f("fk_price_list_items_service_id_services")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_price_list_items_uom_id_unit_of_measures")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_list_items")),
    )
    op.create_index("ix_price_list_items_product", "price_list_items", ["price_list_id", "product_id", "valid_from"], unique=False)
    op.create_index("ix_price_list_items_service", "price_list_items", ["price_list_id", "service_id", "valid_from"], unique=False)

    op.create_table(
        "purchase_invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_number", sa.String(length=50), nullable=False),
        sa.Column("doc_date", sa.Date(), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=True),
        sa.Column("counterparty_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("currency_id", sa.Integer(), nullable=False),
        sa.Column("currency_rate", sa.Numeric(18, 6), server_default="1", nullable=False),
        sa.Column("total_amount_cur", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("total_amount_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("payment_status", sa.String(length=20), server_default="unpaid", nullable=False),
        sa.Column("expiry_note", sa.String(length=200), nullable=True),
        sa.Column("is_return", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("return_invoice_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"], name=op.f("fk_purchase_invoices_counterparty_id_counterparties")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_purchase_invoices_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"], name=op.f("fk_purchase_invoices_currency_id_currencies")),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], name=op.f("fk_purchase_invoices_posted_by_user_id_users")),
        sa.ForeignKeyConstraint(["return_invoice_id"], ["purchase_invoices.id"], name=op.f("fk_purchase_invoices_return_invoice_id_purchase_invoices")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name=op.f("fk_purchase_invoices_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_invoices")),
        sa.UniqueConstraint("doc_number", name=op.f("uq_purchase_invoices_doc_number")),
    )
    op.create_index(op.f("ix_purchase_invoices_doc_number"), "purchase_invoices", ["doc_number"], unique=False)

    op.create_table(
        "purchase_invoice_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_invoice_id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_line_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("expense_category_id", sa.Integer(), nullable=True),
        sa.Column("product_uom_id", sa.Integer(), nullable=True),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("price_cur", sa.Numeric(18, 4), nullable=False),
        sa.Column("price_tmt", sa.Numeric(18, 4), nullable=False),
        sa.Column("amount_cur", sa.Numeric(18, 2), nullable=False),
        sa.Column("amount_tmt", sa.Numeric(18, 2), nullable=False),
        sa.Column("avg_cost_before", sa.Numeric(18, 4), nullable=True),
        sa.Column("avg_cost_after", sa.Numeric(18, 4), nullable=True),
        sa.ForeignKeyConstraint(["expense_category_id"], ["expense_categories.id"], name=op.f("fk_purchase_invoice_lines_expense_category_id_expense_categories")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_purchase_invoice_lines_product_id_products")),
        sa.ForeignKeyConstraint(["product_uom_id"], ["product_uoms.id"], name=op.f("fk_purchase_invoice_lines_product_uom_id_product_uoms")),
        sa.ForeignKeyConstraint(["purchase_invoice_id"], ["purchase_invoices.id"], name=op.f("fk_purchase_invoice_lines_purchase_invoice_id_purchase_invoices")),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name=op.f("fk_purchase_invoice_lines_service_id_services")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_purchase_invoice_lines_uom_id_unit_of_measures")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_invoice_lines")),
    )

    op.create_table(
        "debt_ledger",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), nullable=False),
        sa.Column("debt_type", sa.String(length=15), nullable=False),
        sa.Column("doc_type", sa.String(length=30), nullable=False),
        sa.Column("doc_id", sa.Integer(), nullable=False),
        sa.Column("doc_number", sa.String(length=50), nullable=False),
        sa.Column("doc_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount_tmt", sa.Numeric(18, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency_id", sa.Integer(), nullable=True),
        sa.Column("amount_cur", sa.Numeric(18, 2), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"], name=op.f("fk_debt_ledger_counterparty_id_counterparties")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_debt_ledger_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"], name=op.f("fk_debt_ledger_currency_id_currencies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_debt_ledger")),
    )
    op.create_index(op.f("ix_debt_ledger_debt_type"), "debt_ledger", ["debt_type"], unique=False)
    op.create_index("ix_debt_counterparty_type_date", "debt_ledger", ["counterparty_id", "debt_type", "doc_date"], unique=False)
    op.create_index("ix_debt_doc", "debt_ledger", ["doc_type", "doc_id"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_number", sa.String(length=50), nullable=False),
        sa.Column("doc_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("payment_method", sa.String(length=20), server_default="cash", nullable=False),
        sa.Column("amount_tmt", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency_id", sa.Integer(), nullable=True),
        sa.Column("amount_cur", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="posted", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], name=op.f("fk_payments_cancelled_by_user_id_users")),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"], name=op.f("fk_payments_counterparty_id_counterparties")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_payments_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"], name=op.f("fk_payments_currency_id_currencies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("doc_number", name=op.f("uq_payments_doc_number")),
    )
    op.create_index(op.f("ix_payments_doc_number"), "payments", ["doc_number"], unique=False)

    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("doc_type", sa.String(length=30), nullable=False),
        sa.Column("doc_id", sa.Integer(), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(18, 2), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], name=op.f("fk_payment_allocations_payment_id_payments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_allocations")),
        sa.UniqueConstraint("payment_id", "doc_type", "doc_id", name=op.f("uq_payment_allocations_payment_id")),
    )


def downgrade() -> None:
    """Drop pricing, purchase, and counterparty settlement tables."""

    op.drop_table("payment_allocations")
    op.drop_index(op.f("ix_payments_doc_number"), table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_debt_doc", table_name="debt_ledger")
    op.drop_index("ix_debt_counterparty_type_date", table_name="debt_ledger")
    op.drop_index(op.f("ix_debt_ledger_debt_type"), table_name="debt_ledger")
    op.drop_table("debt_ledger")
    op.drop_table("purchase_invoice_lines")
    op.drop_index(op.f("ix_purchase_invoices_doc_number"), table_name="purchase_invoices")
    op.drop_table("purchase_invoices")
    op.drop_index("ix_price_list_items_service", table_name="price_list_items")
    op.drop_index("ix_price_list_items_product", table_name="price_list_items")
    op.drop_table("price_list_items")
    op.drop_constraint(op.f("fk_counterparties_price_list_id_price_lists"), "counterparties", type_="foreignkey")
    op.drop_constraint(op.f("fk_counterparties_category_id_counterparty_categories"), "counterparties", type_="foreignkey")
    op.drop_index(op.f("ix_counterparties_code"), table_name="counterparties")
    op.drop_column("counterparties", "note")
    op.drop_column("counterparties", "credit_limit_tmt")
    op.drop_column("counterparties", "discount_percent")
    op.drop_column("counterparties", "price_list_id")
    op.drop_column("counterparties", "address")
    op.drop_column("counterparties", "role_flags")
    op.drop_column("counterparties", "category_id")
    op.drop_column("counterparties", "code")
    op.drop_table("price_lists")
    op.drop_table("counterparty_categories")

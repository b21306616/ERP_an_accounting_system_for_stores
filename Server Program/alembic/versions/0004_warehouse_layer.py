"""Add warehouse layer.

Revision ID: 0004_warehouse_layer
Revises: 0003_catalog_layer
Create Date: 2026-06-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_warehouse_layer"
down_revision = "0003_catalog_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create stock balances, movements, and warehouse documents."""

    op.create_table(
        "stock_balances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("avg_cost_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_stock_balances_product_id_products")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_stock_balances_uom_id_unit_of_measures")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name=op.f("fk_stock_balances_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_balances")),
        sa.UniqueConstraint("warehouse_id", "product_id", "uom_id", name=op.f("uq_stock_balances_warehouse_id")),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("movement_type", sa.String(length=40), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost_tmt", sa.Numeric(18, 2), nullable=False),
        sa.Column("amount_tmt", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("movement_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_stock_movements_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_stock_movements_product_id_products")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_stock_movements_uom_id_unit_of_measures")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name=op.f("fk_stock_movements_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
    )
    op.create_index(op.f("ix_stock_movements_movement_type"), "stock_movements", ["movement_type"], unique=False)

    op.create_table(
        "stock_transfers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_warehouse_id", sa.Integer(), nullable=False),
        sa.Column("target_warehouse_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="draft", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("sent_by_user_id", sa.Integer(), nullable=True),
        sa.Column("received_by_user_id", sa.Integer(), nullable=True),
        sa.Column("rejected_by_user_id", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_stock_transfers_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["received_by_user_id"], ["users.id"], name=op.f("fk_stock_transfers_received_by_user_id_users")),
        sa.ForeignKeyConstraint(["rejected_by_user_id"], ["users.id"], name=op.f("fk_stock_transfers_rejected_by_user_id_users")),
        sa.ForeignKeyConstraint(["sent_by_user_id"], ["users.id"], name=op.f("fk_stock_transfers_sent_by_user_id_users")),
        sa.ForeignKeyConstraint(["source_warehouse_id"], ["warehouses.id"], name=op.f("fk_stock_transfers_source_warehouse_id_warehouses")),
        sa.ForeignKeyConstraint(["target_warehouse_id"], ["warehouses.id"], name=op.f("fk_stock_transfers_target_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_transfers")),
    )

    op.create_table(
        "stock_transfer_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transfer_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_stock_transfer_lines_product_id_products")),
        sa.ForeignKeyConstraint(["transfer_id"], ["stock_transfers.id"], name=op.f("fk_stock_transfer_lines_transfer_id_stock_transfers")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_stock_transfer_lines_uom_id_unit_of_measures")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_transfer_lines")),
    )

    op.create_table(
        "stock_writeoffs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="draft", nullable=False),
        sa.Column("reason_code", sa.String(length=40), server_default="other", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_stock_writeoffs_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], name=op.f("fk_stock_writeoffs_posted_by_user_id_users")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name=op.f("fk_stock_writeoffs_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_writeoffs")),
    )

    op.create_table(
        "stock_writeoff_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("writeoff_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_stock_writeoff_lines_product_id_products")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_stock_writeoff_lines_uom_id_unit_of_measures")),
        sa.ForeignKeyConstraint(["writeoff_id"], ["stock_writeoffs.id"], name=op.f("fk_stock_writeoff_lines_writeoff_id_stock_writeoffs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_writeoff_lines")),
    )

    op.create_table(
        "inventories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="draft", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_inventories_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], name=op.f("fk_inventories_posted_by_user_id_users")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name=op.f("fk_inventories_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventories")),
    )

    op.create_table(
        "inventory_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inventory_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("qty_expected", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("qty_actual", sa.Numeric(18, 3), nullable=True),
        sa.Column("unit_cost_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["inventory_id"], ["inventories.id"], name=op.f("fk_inventory_lines_inventory_id_inventories")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_inventory_lines_product_id_products")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_inventory_lines_uom_id_unit_of_measures")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_lines")),
    )


def downgrade() -> None:
    """Drop warehouse layer tables."""

    op.drop_table("inventory_lines")
    op.drop_table("inventories")
    op.drop_table("stock_writeoff_lines")
    op.drop_table("stock_writeoffs")
    op.drop_table("stock_transfer_lines")
    op.drop_table("stock_transfers")
    op.drop_index(op.f("ix_stock_movements_movement_type"), table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_table("stock_balances")

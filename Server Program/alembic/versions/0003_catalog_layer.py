"""Add product catalog layer.

Revision ID: 0003_catalog_layer
Revises: 0002_api_v1_foundation_contract
Create Date: 2026-06-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_catalog_layer"
down_revision = "0002_api_v1_foundation_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create catalog tables and extend existing products."""

    op.create_table(
        "product_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name_ru", sa.String(length=180), nullable=False),
        sa.Column("name_tk", sa.String(length=180), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["product_groups.id"], name=op.f("fk_product_groups_parent_id_product_groups")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_groups")),
        sa.UniqueConstraint("code", name=op.f("uq_product_groups_code")),
    )
    op.create_index(op.f("ix_product_groups_code"), "product_groups", ["code"], unique=False)

    op.create_table(
        "unit_of_measures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name_ru", sa.String(length=120), nullable=False),
        sa.Column("name_tk", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unit_of_measures")),
        sa.UniqueConstraint("code", name=op.f("uq_unit_of_measures_code")),
    )
    op.create_index(op.f("ix_unit_of_measures_code"), "unit_of_measures", ["code"], unique=False)

    op.add_column("products", sa.Column("name_tk", sa.String(length=180), nullable=True))
    op.add_column("products", sa.Column("group_id", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("base_uom_id", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("product_type", sa.String(length=40), server_default="standard", nullable=False))
    op.add_column("products", sa.Column("min_stock", sa.Numeric(18, 3), server_default="0", nullable=False))
    op.add_column("products", sa.Column("description", sa.Text(), nullable=True))
    op.create_foreign_key(op.f("fk_products_group_id_product_groups"), "products", "product_groups", ["group_id"], ["id"])
    op.create_foreign_key(op.f("fk_products_base_uom_id_unit_of_measures"), "products", "unit_of_measures", ["base_uom_id"], ["id"])

    op.create_table(
        "product_uoms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("uom_id", sa.Integer(), nullable=False),
        sa.Column("coefficient", sa.Numeric(18, 6), server_default="1", nullable=False),
        sa.Column("is_base", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_product_uoms_product_id_products")),
        sa.ForeignKeyConstraint(["uom_id"], ["unit_of_measures.id"], name=op.f("fk_product_uoms_uom_id_unit_of_measures")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_uoms")),
        sa.UniqueConstraint("product_id", "uom_id", name=op.f("uq_product_uoms_product_id")),
    )

    op.create_table(
        "product_barcodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_uom_id", sa.Integer(), nullable=True),
        sa.Column("barcode", sa.String(length=80), nullable=False),
        sa.Column("is_weight_barcode", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_product_barcodes_product_id_products")),
        sa.ForeignKeyConstraint(["product_uom_id"], ["product_uoms.id"], name=op.f("fk_product_barcodes_product_uom_id_product_uoms")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_barcodes")),
        sa.UniqueConstraint("barcode", name=op.f("uq_product_barcodes_barcode")),
    )
    op.create_index(op.f("ix_product_barcodes_barcode"), "product_barcodes", ["barcode"], unique=False)

    op.create_table(
        "expense_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name_ru", sa.String(length=160), nullable=False),
        sa.Column("name_tk", sa.String(length=160), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expense_categories")),
        sa.UniqueConstraint("code", name=op.f("uq_expense_categories_code")),
    )
    op.create_index(op.f("ix_expense_categories_code"), "expense_categories", ["code"], unique=False)

    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name_ru", sa.String(length=180), nullable=False),
        sa.Column("name_tk", sa.String(length=180), nullable=True),
        sa.Column("service_type", sa.String(length=40), server_default="sale", nullable=False),
        sa.Column("expense_category_id", sa.Integer(), nullable=True),
        sa.Column("default_price", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["expense_category_id"], ["expense_categories.id"], name=op.f("fk_services_expense_category_id_expense_categories")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_services")),
        sa.UniqueConstraint("code", name=op.f("uq_services_code")),
    )
    op.create_index(op.f("ix_services_code"), "services", ["code"], unique=False)

    op.create_table(
        "service_barcodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("barcode", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name=op.f("fk_service_barcodes_service_id_services")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_barcodes")),
        sa.UniqueConstraint("barcode", name=op.f("uq_service_barcodes_barcode")),
    )
    op.create_index(op.f("ix_service_barcodes_barcode"), "service_barcodes", ["barcode"], unique=False)


def downgrade() -> None:
    """Drop catalog layer objects."""

    op.drop_index(op.f("ix_service_barcodes_barcode"), table_name="service_barcodes")
    op.drop_table("service_barcodes")
    op.drop_index(op.f("ix_services_code"), table_name="services")
    op.drop_table("services")
    op.drop_index(op.f("ix_expense_categories_code"), table_name="expense_categories")
    op.drop_table("expense_categories")
    op.drop_index(op.f("ix_product_barcodes_barcode"), table_name="product_barcodes")
    op.drop_table("product_barcodes")
    op.drop_table("product_uoms")
    op.drop_constraint(op.f("fk_products_base_uom_id_unit_of_measures"), "products", type_="foreignkey")
    op.drop_constraint(op.f("fk_products_group_id_product_groups"), "products", type_="foreignkey")
    op.drop_column("products", "description")
    op.drop_column("products", "min_stock")
    op.drop_column("products", "product_type")
    op.drop_column("products", "base_uom_id")
    op.drop_column("products", "group_id")
    op.drop_column("products", "name_tk")
    op.drop_index(op.f("ix_unit_of_measures_code"), table_name="unit_of_measures")
    op.drop_table("unit_of_measures")
    op.drop_index(op.f("ix_product_groups_code"), table_name="product_groups")
    op.drop_table("product_groups")

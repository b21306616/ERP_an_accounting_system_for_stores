"""Add promotions and loyalty program.

Revision ID: 0008_promotions_loyalty
Revises: 0007_document_lifecycle
Create Date: 2026-06-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_promotions_loyalty"
down_revision = "0007_document_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create promotion and loyalty tables."""

    op.create_table(
        "promotions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("promotion_type", sa.String(length=20), nullable=False),
        sa.Column("target_type", sa.String(length=20), server_default="product", nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_group_id", sa.Integer(), nullable=True),
        sa.Column("discount_type", sa.String(length=20), nullable=True),
        sa.Column("discount_value", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("min_quantity", sa.Numeric(18, 4), server_default="1", nullable=False),
        sa.Column("gift_product_id", sa.Integer(), nullable=True),
        sa.Column("gift_quantity", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["gift_product_id"], ["products.id"], name=op.f("fk_promotions_gift_product_id_products")),
        sa.ForeignKeyConstraint(["product_group_id"], ["product_groups.id"], name=op.f("fk_promotions_product_group_id_product_groups")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_promotions_product_id_products")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promotions")),
    )

    op.create_table(
        "loyalty_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("earn_rate_percent", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("redemption_limit_percent", sa.Numeric(5, 2), server_default="100", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_loyalty_settings")),
    )

    op.create_table(
        "loyalty_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_number", sa.String(length=80), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), nullable=True),
        sa.Column("owner_name", sa.String(length=180), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("balance_tmt", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"], name=op.f("fk_loyalty_cards_counterparty_id_counterparties")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_loyalty_cards")),
        sa.UniqueConstraint("card_number", name=op.f("uq_loyalty_cards_card_number")),
    )
    op.create_index(op.f("ix_loyalty_cards_card_number"), "loyalty_cards", ["card_number"], unique=False)

    op.create_table(
        "loyalty_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("loyalty_card_id", sa.Integer(), nullable=False),
        sa.Column("transaction_type", sa.String(length=30), nullable=False),
        sa.Column("doc_type", sa.String(length=30), nullable=True),
        sa.Column("doc_id", sa.Integer(), nullable=True),
        sa.Column("amount_tmt", sa.Numeric(18, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 2), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_loyalty_transactions_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["loyalty_card_id"], ["loyalty_cards.id"], name=op.f("fk_loyalty_transactions_loyalty_card_id_loyalty_cards")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_loyalty_transactions")),
    )
    op.create_index(op.f("ix_loyalty_transactions_loyalty_card_id"), "loyalty_transactions", ["loyalty_card_id"], unique=False)
    op.create_index(op.f("ix_loyalty_transactions_transaction_type"), "loyalty_transactions", ["transaction_type"], unique=False)

    op.add_column("sale_returns", sa.Column("refund_bonus_tmt", sa.Numeric(18, 2), server_default="0", nullable=False))
    op.create_foreign_key(op.f("fk_sales_loyalty_card_id_loyalty_cards"), "sales", "loyalty_cards", ["loyalty_card_id"], ["id"])
    op.create_foreign_key(op.f("fk_sale_lines_promo_id_promotions"), "sale_lines", "promotions", ["promo_id"], ["id"])


def downgrade() -> None:
    """Drop promotion and loyalty objects."""

    op.drop_constraint(op.f("fk_sale_lines_promo_id_promotions"), "sale_lines", type_="foreignkey")
    op.drop_constraint(op.f("fk_sales_loyalty_card_id_loyalty_cards"), "sales", type_="foreignkey")
    op.drop_column("sale_returns", "refund_bonus_tmt")
    op.drop_index(op.f("ix_loyalty_transactions_transaction_type"), table_name="loyalty_transactions")
    op.drop_index(op.f("ix_loyalty_transactions_loyalty_card_id"), table_name="loyalty_transactions")
    op.drop_table("loyalty_transactions")
    op.drop_index(op.f("ix_loyalty_cards_card_number"), table_name="loyalty_cards")
    op.drop_table("loyalty_cards")
    op.drop_table("loyalty_settings")
    op.drop_table("promotions")

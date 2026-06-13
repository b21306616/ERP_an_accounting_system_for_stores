"""counterparty finance completion

Revision ID: 0009_counterparty_finance
Revises: 0008_promotions_loyalty
Create Date: 2026-06-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_counterparty_finance"
down_revision = "0008_promotions_loyalty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add contract links to settlement documents and debt rows."""

    op.add_column("purchase_orders", sa.Column("contract_id", sa.Integer(), nullable=True))
    op.add_column("purchase_invoices", sa.Column("contract_id", sa.Integer(), nullable=True))
    op.add_column("sales", sa.Column("contract_id", sa.Integer(), nullable=True))
    op.add_column("payments", sa.Column("contract_id", sa.Integer(), nullable=True))
    op.add_column("debt_ledger", sa.Column("contract_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_purchase_orders_contract_id", "purchase_orders", "contracts", ["contract_id"], ["id"])
    op.create_foreign_key("fk_purchase_invoices_contract_id", "purchase_invoices", "contracts", ["contract_id"], ["id"])
    op.create_foreign_key("fk_sales_contract_id", "sales", "contracts", ["contract_id"], ["id"])
    op.create_foreign_key("fk_payments_contract_id", "payments", "contracts", ["contract_id"], ["id"])
    op.create_foreign_key("fk_debt_ledger_contract_id", "debt_ledger", "contracts", ["contract_id"], ["id"])


def downgrade() -> None:
    """Remove contract links from settlement documents and debt rows."""

    op.drop_constraint("fk_debt_ledger_contract_id", "debt_ledger", type_="foreignkey")
    op.drop_constraint("fk_payments_contract_id", "payments", type_="foreignkey")
    op.drop_constraint("fk_sales_contract_id", "sales", type_="foreignkey")
    op.drop_constraint("fk_purchase_invoices_contract_id", "purchase_invoices", type_="foreignkey")
    op.drop_constraint("fk_purchase_orders_contract_id", "purchase_orders", type_="foreignkey")
    op.drop_column("debt_ledger", "contract_id")
    op.drop_column("payments", "contract_id")
    op.drop_column("sales", "contract_id")
    op.drop_column("purchase_invoices", "contract_id")
    op.drop_column("purchase_orders", "contract_id")

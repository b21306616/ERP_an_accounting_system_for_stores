"""report filters and report export presets

Revision ID: 0010_report_filters
Revises: 0009_counterparty_finance
Create Date: 2026-06-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_report_filters"
down_revision = "0009_counterparty_finance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create saved report filter presets."""

    op.create_table(
        "report_filters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("filters_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("is_shared", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_report_filters_created_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_filters")),
        sa.UniqueConstraint("report_code", "name", "created_by_user_id", name=op.f("uq_report_filters_report_code")),
    )
    op.create_index(op.f("ix_report_filters_report_code"), "report_filters", ["report_code"], unique=False)
    op.create_index(op.f("ix_report_filters_created_by_user_id"), "report_filters", ["created_by_user_id"], unique=False)


def downgrade() -> None:
    """Drop saved report filter presets."""

    op.drop_index(op.f("ix_report_filters_created_by_user_id"), table_name="report_filters")
    op.drop_index(op.f("ix_report_filters_report_code"), table_name="report_filters")
    op.drop_table("report_filters")

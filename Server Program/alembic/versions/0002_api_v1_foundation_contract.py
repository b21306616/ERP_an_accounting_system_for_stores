"""Add API v1 foundation contract tables.

Revision ID: 0002_api_v1_foundation_contract
Revises: 0001_initial_foundation_schema
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_api_v1_foundation_contract"
down_revision = "0001_initial_foundation_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create session, permission, workplace, and settings support."""

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("code", name=op.f("uq_permissions_code")),
    )
    op.create_index(op.f("ix_permissions_code"), "permissions", ["code"], unique=False)
    op.create_index(op.f("ix_permissions_module"), "permissions", ["module"], unique=False)

    op.create_table(
        "workplaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("workplace_type", sa.String(length=40), server_default="office", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workplaces")),
        sa.UniqueConstraint("code", name=op.f("uq_workplaces_code")),
    )
    op.create_index(op.f("ix_workplaces_code"), "workplaces", ["code"], unique=False)

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
        sa.UniqueConstraint("key", name=op.f("uq_settings_key")),
    )
    op.create_index(op.f("ix_settings_key"), "settings", ["key"], unique=False)

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], name=op.f("fk_role_permissions_permission_id_permissions")),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_role_permissions_role_id_roles")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_permissions")),
        sa.UniqueConstraint("role_id", "permission_id", name=op.f("uq_role_permissions_role_id")),
    )

    op.add_column("users", sa.Column("workplace_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_users_workplace_id_workplaces"),
        "users",
        "workplaces",
        ["workplace_id"],
        ["id"],
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_name", sa.String(length=120), nullable=True),
        sa.Column("client_version", sa.String(length=40), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_sessions_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
    )
    op.create_index(op.f("ix_user_sessions_token_hash"), "user_sessions", ["token_hash"], unique=False)

    op.add_column("audit_logs", sa.Column("module", sa.String(length=80), nullable=True))
    op.add_column("audit_logs", sa.Column("old_values", sa.Text(), nullable=True))
    op.add_column("audit_logs", sa.Column("new_values", sa.Text(), nullable=True))
    op.add_column("audit_logs", sa.Column("ip_address", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Drop API v1 foundation additions."""

    op.drop_column("audit_logs", "ip_address")
    op.drop_column("audit_logs", "new_values")
    op.drop_column("audit_logs", "old_values")
    op.drop_column("audit_logs", "module")

    op.drop_index(op.f("ix_user_sessions_token_hash"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_constraint(op.f("fk_users_workplace_id_workplaces"), "users", type_="foreignkey")
    op.drop_column("users", "workplace_id")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_settings_key"), table_name="settings")
    op.drop_table("settings")
    op.drop_index(op.f("ix_workplaces_code"), table_name="workplaces")
    op.drop_table("workplaces")
    op.drop_index(op.f("ix_permissions_module"), table_name="permissions")
    op.drop_index(op.f("ix_permissions_code"), table_name="permissions")
    op.drop_table("permissions")

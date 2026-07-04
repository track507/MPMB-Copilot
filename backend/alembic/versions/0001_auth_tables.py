"""
Auth tables: users, auth_sessions, login_attempts

Revision ID: 0001
Revises:
Create Date: 2026-07-04
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('admin','user')", name="users_role_check"),
    )
    # ! Case-insensitive uniqueness: lookups use LOWER(username)
    op.create_index("idx_users_username_lower", "users", [sa.text("LOWER(username)")], unique=True)

    op.create_table(
        "auth_sessions",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", PGUUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    op.create_index("idx_auth_sessions_user", "auth_sessions", ["user_id"])

    op.create_table(
        "login_attempts",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("client_ip", sa.String(64), nullable=False),
        sa.Column(
            "attempted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    op.create_index("idx_login_attempts_window", "login_attempts", ["username", "client_ip", "attempted_at"])


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_table("auth_sessions")
    op.drop_table("users")

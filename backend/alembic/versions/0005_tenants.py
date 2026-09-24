"""
Add tenants and scope every user-owned table to one

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op
from app.core.storage_keys import DEFAULT_TENANT_ID

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCOPED_TABLES = ("users", "sessions", "files")


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(f"INSERT INTO tenants (id, slug, name) VALUES ('{DEFAULT_TENANT_ID}', 'default', 'Default')")

    for table in _SCOPED_TABLES:
        op.add_column(table, sa.Column("tenant_id", PGUUID(as_uuid=True), nullable=True))
        op.execute(f"UPDATE {table} SET tenant_id = '{DEFAULT_TENANT_ID}'")
        op.alter_column(table, "tenant_id", nullable=False)
        op.create_foreign_key(f"fk_{table}_tenant", table, "tenants", ["tenant_id"], ["id"])
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])

    op.execute("DROP TABLE IF EXISTS message_retrievals")
    op.execute("DROP TABLE IF EXISTS document_chunks")

    op.alter_column("files", "file_path", new_column_name="storage_key")


def downgrade() -> None:
    op.alter_column("files", "storage_key", new_column_name="file_path")

    op.create_table(
        "document_chunks",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("source_file", sa.String(512), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("qdrant_id", sa.String(255), unique=True),
        sa.Column("meta_data", JSONB(), server_default="{}"),
        sa.Column("indexed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_file", "chunk_index", name="doc_chunks_source_index_unique"),
    )
    op.create_table(
        "message_retrievals",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", PGUUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "document_chunk_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("snippet", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("message_id", "document_chunk_id", name="message_retrievals_unique"),
    )

    for table in reversed(_SCOPED_TABLES):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_constraint(f"fk_{table}_tenant", table, type_="foreignkey")
        op.drop_column(table, "tenant_id")

    op.drop_table("tenants")

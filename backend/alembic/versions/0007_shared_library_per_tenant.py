"""
Make shared-library filenames unique per tenant

Revision ID: 0007
Revises: 0006
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_files_shared_filename", table_name="files")
    op.create_index(
        "uq_files_shared_tenant_filename",
        "files",
        ["tenant_id", "filename"],
        unique=True,
        postgresql_where=sa.text("scope = 'shared'"),
    )


def downgrade() -> None:
    op.drop_index("uq_files_shared_tenant_filename", table_name="files")
    op.create_index(
        "uq_files_shared_filename",
        "files",
        ["filename"],
        unique=True,
        postgresql_where=sa.text("scope = 'shared'"),
    )

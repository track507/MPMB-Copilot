"""
Backfill session owners and require them

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ? Legacy rows predate owner stamping; claim them for the oldest admin
    # ? Mirrors auth_service.claim_orphan_sessions at first-run setup
    op.execute(
        """
        UPDATE sessions
        SET user_id = (SELECT id::text FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1)
        WHERE user_id IS NULL
        """
    )
    # ! Anything still unowned has no admin to inherit it and cannot belong to anyone
    op.execute("DELETE FROM sessions WHERE user_id IS NULL")
    op.alter_column("sessions", "user_id", existing_type=sa.String(255), nullable=False)


def downgrade() -> None:
    op.alter_column("sessions", "user_id", existing_type=sa.String(255), nullable=True)

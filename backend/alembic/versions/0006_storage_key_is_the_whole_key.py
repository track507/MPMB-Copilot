"""
Store the whole storage key, including its tenants/ segment

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ! Keys were stored relative to the uploads subtree, so they were a fragment no other reader could resolve
# ? Everything else in the scheme is relative to the storage root, which is why this one had to move rather than the rest
_ADD_PREFIX = "update files set storage_key = 'tenants/' || storage_key where storage_key not like 'tenants/%'"
_DROP_PREFIX = "update files set storage_key = substring(storage_key from 9) where storage_key like 'tenants/%'"


def upgrade() -> None:
    op.execute(_ADD_PREFIX)


def downgrade() -> None:
    op.execute(_DROP_PREFIX)

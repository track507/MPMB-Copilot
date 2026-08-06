import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision = "0003"
down_version = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM files")

    op.add_column("files", sa.Column("scope", sa.String(16), nullable=False))
    op.add_column("files", sa.Column("owner_user_id", sa.String(255), nullable=False))
    op.alter_column("files", "session_id", existing_type=PGUUID(as_uuid=True), nullable=True)
    op.alter_column("files", "file_hash", existing_type=sa.String(64), nullable=False)

    op.create_check_constraint(
        "ck_files_session_scope",
        "files",
        "(scope = 'session') = (session_id IS NOT NULL)",
    )
    op.create_index(
        "uq_files_session_filename",
        "files",
        ["session_id", "filename"],
        unique=True,
        postgresql_where=sa.text("scope = 'session'"),
    )
    op.create_index(
        "uq_files_global_owner_filename",
        "files",
        ["owner_user_id", "filename"],
        unique=True,
        postgresql_where=sa.text("scope = 'global'"),
    )
    op.create_index(
        "uq_files_shared_filename",
        "files",
        ["filename"],
        unique=True,
        postgresql_where=sa.text("scope = 'shared'"),
    )


def downgrade() -> None:
    op.drop_index("uq_files_shared_filename", table_name="files")
    op.drop_index("uq_files_global_owner_filename", table_name="files")
    op.drop_index("uq_files_session_filename", table_name="files")
    op.drop_constraint("ck_files_session_scope", "files", type_="check")
    op.alter_column("files", "file_hash", existing_type=sa.String(64), nullable=True)
    op.alter_column("files", "session_id", existing_type=PGUUID(as_uuid=True), nullable=False)
    op.drop_column("files", "owner_user_id")
    op.drop_column("files", "scope")

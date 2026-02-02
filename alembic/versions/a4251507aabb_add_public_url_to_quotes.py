"""Add public_url to quotes

Revision ID: a4251507aabb
Revises: 8a40197da8d5
Create Date: 2025-12-03 17:47:28.709641
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "a4251507aabb"
down_revision: Union[str, Sequence[str], None] = "8a40197da8d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sqlite_index_exists(op_, index_name: str) -> bool:
    conn = op_.get_bind()
    res = conn.execute(
        text("SELECT 1 FROM sqlite_master " "WHERE type='index' AND name=:name"),
        {"name": index_name},
    ).fetchone()
    return res is not None


def _sqlite_table_exists(op_, table_name: str) -> bool:
    conn = op_.get_bind()
    res = conn.execute(
        text("SELECT 1 FROM sqlite_master " "WHERE type='table' AND name=:name"),
        {"name": table_name},
    ).fetchone()
    return res is not None


def upgrade() -> None:
    """Upgrade schema."""

    # ---- DROP INDEX (only if exists) ----
    ix_candidates = [
        op.f("ix_upload_status_object_key"),
        "ix_upload_status_object_key",
    ]

    for ix_name in ix_candidates:
        if _sqlite_index_exists(op, ix_name):
            op.drop_index(ix_name, table_name="upload_status")
            break

    # ---- DROP TABLE (only if exists) ----
    if _sqlite_table_exists(op, "upload_status"):
        op.drop_table("upload_status")


def downgrade() -> None:
    """Downgrade schema."""

    op.create_table(
        "upload_status",
        sa.Column("id", sa.VARCHAR(), nullable=False),
        sa.Column("user_id", sa.VARCHAR(), nullable=False),
        sa.Column("object_key", sa.VARCHAR(), nullable=False),
        sa.Column("status", sa.VARCHAR(), nullable=True),
        sa.Column("verified_at", sa.DATETIME(), nullable=True),
        sa.Column("error", sa.TEXT(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_upload_status_object_key"),
        "upload_status",
        ["object_key"],
        unique=False,
    )

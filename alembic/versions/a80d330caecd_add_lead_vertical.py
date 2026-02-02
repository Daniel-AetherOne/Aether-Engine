"""add lead vertical

Revision ID: a80d330caecd
Revises: a4251507aabb
Create Date: 2025-12-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "a80d330caecd"
down_revision = "a4251507aabb"
branch_labels = None
depends_on = None


def _sqlite_column_exists(op_, table: str, column: str) -> bool:
    conn = op_.get_bind()
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    # SQLite-safe: only add if missing
    if not _sqlite_column_exists(op, "leads", "vertical"):
        op.add_column(
            "leads", sa.Column("vertical", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    # SQLite can't easily drop columns; for MVP we leave downgrade as a no-op
    pass

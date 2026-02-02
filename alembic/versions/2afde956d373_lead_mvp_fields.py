"""lead mvp fields

Revision ID: 2afde956d373
Revises: a80d330caecd
Create Date: 2026-01-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "2afde956d373"
down_revision = "a80d330caecd"
branch_labels = None
depends_on = None


def _sqlite_column_exists(op_, table: str, column: str) -> bool:
    conn = op_.get_bind()
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if not _sqlite_column_exists(op, table, column.name):
        op.add_column(table, column)


def upgrade():
    _add_column_if_missing(
        "leads", sa.Column("error_message", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        "leads", sa.Column("intake_payload", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        "leads", sa.Column("estimate_json", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        "leads", sa.Column("estimate_html_key", sa.String(length=1024), nullable=True)
    )
    _add_column_if_missing(
        "leads", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    # SQLite can't easily drop columns; for MVP we leave downgrade as a no-op
    pass

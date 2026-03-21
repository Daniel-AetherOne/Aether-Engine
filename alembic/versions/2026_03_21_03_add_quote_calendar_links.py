"""add quote calendar links table

Revision ID: 2026_03_21_03
Revises: 2026_03_21_02
Create Date: 2026-03-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_03_21_03"
down_revision: Union[str, Sequence[str], None] = "2026_03_21_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quote_calendar_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("quote_id", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="google"),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "quote_id",
            "provider",
            name="uq_quote_calendar_links_quote_provider",
        ),
    )
    op.create_index(
        "ix_quote_calendar_links_tenant_id",
        "quote_calendar_links",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_quote_calendar_links_quote_id",
        "quote_calendar_links",
        ["quote_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_quote_calendar_links_quote_id", table_name="quote_calendar_links")
    op.drop_index("ix_quote_calendar_links_tenant_id", table_name="quote_calendar_links")
    op.drop_table("quote_calendar_links")

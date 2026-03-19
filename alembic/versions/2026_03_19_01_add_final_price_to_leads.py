"""add final_price to leads

Revision ID: 2026_03_19_01
Revises: 2026_03_18_01
Create Date: 2026-03-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_03_19_01"
down_revision: Union[str, Sequence[str], None] = "2026_03_18_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add final_price column to leads."""
    op.add_column(
        "leads",
        sa.Column("final_price", sa.Numeric(precision=12, scale=2), nullable=True),
    )


def downgrade() -> None:
    """Drop final_price column from leads."""
    op.drop_column("leads", "final_price")


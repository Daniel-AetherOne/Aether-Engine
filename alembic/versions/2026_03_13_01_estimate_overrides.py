"""add estimate_overrides_json to leads

Revision ID: 2026_03_13_01
Revises: da8e1c6c28aa
Create Date: 2026-03-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_03_13_01"
down_revision: Union[str, Sequence[str], None] = "da8e1c6c28aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add estimate_overrides_json column to leads."""
    op.add_column(
        "leads",
        sa.Column("estimate_overrides_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop estimate_overrides_json column from leads."""
    op.drop_column("leads", "estimate_overrides_json")


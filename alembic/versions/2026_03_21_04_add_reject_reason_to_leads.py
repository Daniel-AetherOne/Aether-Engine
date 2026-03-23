"""add reject reason to leads

Revision ID: 2026_03_21_04
Revises: 2026_03_21_03
Create Date: 2026-03-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_03_21_04"
down_revision: Union[str, Sequence[str], None] = "2026_03_21_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("reject_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "reject_reason")

"""merge heads

Revision ID: 946c4d3dddc6
Revises: 2afde956d373, 7bbd27c02ea5
Create Date: 2026-01-24 12:23:41.426264

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '946c4d3dddc6'
down_revision: Union[str, Sequence[str], None] = ('2afde956d373', '7bbd27c02ea5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

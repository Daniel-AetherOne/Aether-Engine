"""backfill starter billing defaults for legacy tenants

Revision ID: 2026_03_20_02
Revises: 2026_03_20_01
Create Date: 2026-03-20
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2026_03_20_02"
down_revision: Union[str, Sequence[str], None] = "2026_03_20_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only touch legacy rows with missing billing state and no Stripe subscription.
    op.execute(
        """
        UPDATE tenants
        SET plan_code = COALESCE(NULLIF(TRIM(plan_code), ''), 'starter_99'),
            subscription_status = COALESCE(NULLIF(TRIM(subscription_status), ''), 'trialing')
        WHERE (plan_code IS NULL OR TRIM(plan_code) = '' OR subscription_status IS NULL OR TRIM(subscription_status) = '')
          AND (stripe_subscription_id IS NULL OR TRIM(stripe_subscription_id) = '');
        """
    )


def downgrade() -> None:
    # No-op: avoid wiping valid billing state.
    pass


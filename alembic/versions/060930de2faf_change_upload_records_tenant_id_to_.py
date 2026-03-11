from alembic import op
import sqlalchemy as sa

revision = "060930de2faf"
down_revision = "a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "upload_records",
        "tenant_id",
        existing_type=sa.Integer(),
        type_=sa.String(length=100),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "upload_records",
        "tenant_id",
        existing_type=sa.String(length=100),
        type_=sa.Integer(),
        existing_nullable=False,
    )

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "a1b2c3d4"
down_revision = "69ddfaaf8af8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenants",
        sa.Column("slug", sa.String(length=120), nullable=True),
    )

    op.create_index(
        "ix_tenants_slug",
        "tenants",
        ["slug"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_tenants_slug", table_name="tenants")

    op.drop_column("tenants", "slug")

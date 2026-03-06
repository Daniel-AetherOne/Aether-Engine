from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "69ddfaaf8af8"
down_revision = "3310ae409395"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants", sa.Column("company_name", sa.String(length=200), nullable=True)
    )
    op.add_column("tenants", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("tenants", sa.Column("phone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "phone")
    op.drop_column("tenants", "email")
    op.drop_column("tenants", "company_name")

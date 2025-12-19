from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a80d330caecd"
down_revision = "a4251507aabb"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("leads", sa.Column("vertical", sa.String(length=64), nullable=True))
    op.create_index("ix_leads_vertical", "leads", ["vertical"])


def downgrade():
    op.drop_index("ix_leads_vertical", table_name="leads")
    op.drop_column("leads", "vertical")

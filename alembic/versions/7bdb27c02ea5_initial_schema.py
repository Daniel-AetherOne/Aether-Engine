"""initial schema

Revision ID: <nieuw_id>
Revises:
Create Date: 2026-01-22
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "7bbd27c02ea5"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("vertical", sa.String(64)),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(50)),
        sa.Column("status", sa.String(50), nullable=False, server_default="NEW"),
        sa.Column("notes", sa.Text),
        sa.Column("intake_payload", sa.Text),
        sa.Column("estimate_json", sa.Text),
        sa.Column("estimate_html_key", sa.String(1024)),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "lead_files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "lead_id",
            sa.Integer,
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
    )


def downgrade():
    op.drop_table("lead_files")
    op.drop_table("leads")

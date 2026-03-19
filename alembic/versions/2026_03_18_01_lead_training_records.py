"""add lead_training_records table

Revision ID: 2026_03_18_01
Revises: 2026_03_13_01
Create Date: 2026-03-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "2026_03_18_01"
down_revision: Union[str, Sequence[str], None] = "2026_03_13_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create lead_training_records table."""
    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind and bind.dialect else ""
    json_type = postgresql.JSONB if dialect_name == "postgresql" else sa.JSON
    lead_id_type: sa.types.TypeEngine = sa.String(length=100)

    # Keep FK column type exactly aligned with leads.id in target DB.
    inspector = inspect(bind)
    for column in inspector.get_columns("leads"):
        if column.get("name") == "id":
            reflected_type = column.get("type")
            if reflected_type is not None:
                lead_id_type = reflected_type
            break

    op.create_table(
        "lead_training_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("lead_id", lead_id_type, nullable=False),
        sa.Column("capture_version", sa.String(length=50), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("outcome_reason", sa.Text(), nullable=True),
        sa.Column("intake_snapshot", json_type, nullable=True),
        sa.Column("photo_refs", json_type, nullable=True),
        sa.Column("estimate_input", json_type, nullable=True),
        sa.Column("estimate_output", json_type, nullable=True),
        sa.Column("pricing_result", json_type, nullable=True),
        sa.Column("metadata_json", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "lead_id",
            name="uq_lead_training_tenant_lead",
        ),
    )
    op.create_index(
        op.f("ix_lead_training_records_tenant_id"),
        "lead_training_records",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_lead_training_records_lead_id"),
        "lead_training_records",
        ["lead_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop lead_training_records table."""
    op.drop_index(
        op.f("ix_lead_training_records_lead_id"),
        table_name="lead_training_records",
    )
    op.drop_index(
        op.f("ix_lead_training_records_tenant_id"),
        table_name="lead_training_records",
    )
    op.drop_table("lead_training_records")


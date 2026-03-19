"""align lead id column types for existing render databases

Revision ID: 2026_03_19_02
Revises: 2026_03_19_01
Create Date: 2026-03-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.sqltypes import String as SAString


# revision identifiers, used by Alembic.
revision: str = "2026_03_19_02"
down_revision: Union[str, Sequence[str], None] = "2026_03_19_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_string_type(column_type: sa.types.TypeEngine) -> bool:
    return isinstance(column_type, SAString)


def upgrade() -> None:
    """Align leads.id and required lead_id foreign keys to String(100)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("leads"):
        return

    lead_tables = ["lead_files", "lead_training_records", "jobs", "upload_records"]

    # Drop FK constraints to leads.id before type conversion.
    dropped_fks: list[tuple[str, str, list[str], list[str], str | None]] = []
    for table_name in lead_tables:
        if not inspector.has_table(table_name):
            continue
        for fk in inspector.get_foreign_keys(table_name):
            referred_table = fk.get("referred_table")
            constrained_columns = fk.get("constrained_columns") or []
            if referred_table == "leads" and "lead_id" in constrained_columns:
                constraint_name = fk.get("name")
                if constraint_name:
                    op.drop_constraint(
                        constraint_name,
                        table_name,
                        type_="foreignkey",
                    )
                    dropped_fks.append(
                        (
                            table_name,
                            constraint_name,
                            constrained_columns,
                            fk.get("referred_columns") or ["id"],
                            (fk.get("options") or {}).get("ondelete"),
                        )
                    )

    # Convert child lead_id columns first.
    for table_name in lead_tables:
        if not inspector.has_table(table_name):
            continue
        lead_id_col = next(
            (c for c in inspector.get_columns(table_name) if c.get("name") == "lead_id"),
            None,
        )
        if lead_id_col is None:
            continue
        if not _is_string_type(lead_id_col.get("type")):
            op.alter_column(
                table_name,
                "lead_id",
                existing_type=lead_id_col.get("type"),
                type_=sa.String(length=100),
                existing_nullable=lead_id_col.get("nullable", True),
                postgresql_using="lead_id::text",
            )

    # Convert parent PK column.
    lead_id_col = next(
        (c for c in inspector.get_columns("leads") if c.get("name") == "id"),
        None,
    )
    if lead_id_col is not None and not _is_string_type(lead_id_col.get("type")):
        op.alter_column(
            "leads",
            "id",
            existing_type=lead_id_col.get("type"),
            type_=sa.String(length=100),
            existing_nullable=lead_id_col.get("nullable", False),
            postgresql_using="id::text",
        )

    # Recreate dropped FK constraints.
    for table_name, constraint_name, columns, referred_columns, ondelete in dropped_fks:
        op.create_foreign_key(
            constraint_name,
            table_name,
            "leads",
            columns,
            referred_columns,
            ondelete=ondelete,
        )


def downgrade() -> None:
    """No-op downgrade: reverting may break existing string IDs."""
    pass


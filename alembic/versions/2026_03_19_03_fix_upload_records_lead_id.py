"""fix upload_records.lead_id type for existing render dbs

Render DBs may already be on revision 2026_03_19_02, while this specific
column still remains integer. This migration aligns it with leads.id.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.sqltypes import String as SAString


revision: str = "2026_03_19_03"
down_revision: Union[str, Sequence[str], None] = "2026_03_19_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_string_type(column_type: sa.types.TypeEngine) -> bool:
    return isinstance(column_type, SAString)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("upload_records"):
        return

    upload_cols = inspector.get_columns("upload_records")
    lead_id_col = next((c for c in upload_cols if c.get("name") == "lead_id"), None)
    if lead_id_col is None:
        return

    existing_fk = None
    for fk in inspector.get_foreign_keys("upload_records"):
        referred_table = fk.get("referred_table")
        constrained_columns = fk.get("constrained_columns") or []
        if referred_table == "leads" and "lead_id" in constrained_columns:
            existing_fk = fk
            break

    # Drop FK before altering column type.
    if existing_fk and existing_fk.get("name"):
        op.drop_constraint(existing_fk["name"], "upload_records", type_="foreignkey")

    if not _is_string_type(lead_id_col.get("type")):
        op.alter_column(
            "upload_records",
            "lead_id",
            existing_type=lead_id_col.get("type"),
            type_=sa.String(length=100),
            existing_nullable=lead_id_col.get("nullable", True),
            postgresql_using="lead_id::text",
        )

    # Recreate FK using previous ondelete (if present).
    fk_name = (existing_fk or {}).get("name") or "fk_upload_records_lead_id_leads"
    ondelete = ((existing_fk or {}).get("options") or {}).get("ondelete")

    op.create_foreign_key(
        fk_name,
        "upload_records",
        "leads",
        ["lead_id"],
        ["id"],
        ondelete=ondelete,
    )


def downgrade() -> None:
    """No safe downgrade; keep as no-op."""
    pass


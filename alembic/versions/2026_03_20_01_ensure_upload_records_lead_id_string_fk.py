"""ensure upload_records.lead_id matches leads.id type and foreign key

Revision ID: 2026_03_20_01
Revises: 2026_03_19_03
Create Date: 2026-03-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.sqltypes import String as SAString


# revision identifiers, used by Alembic.
revision: str = "2026_03_20_01"
down_revision: Union[str, Sequence[str], None] = "2026_03_19_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_string_type(column_type: sa.types.TypeEngine) -> bool:
    return isinstance(column_type, SAString)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("upload_records") or not inspector.has_table("leads"):
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

    fk_name = (existing_fk or {}).get("name") or "fk_upload_records_lead_id_leads"
    ondelete = ((existing_fk or {}).get("options") or {}).get("ondelete") or "CASCADE"

    op.create_foreign_key(
        fk_name,
        "upload_records",
        "leads",
        ["lead_id"],
        ["id"],
        ondelete=ondelete,
    )


def downgrade() -> None:
    """No-op downgrade to avoid reintroducing type mismatch."""
    pass


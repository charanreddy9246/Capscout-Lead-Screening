"""Next Action is the lead's stage; Loan Stage is merged into it

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-26

For converted leads: Next Action becomes the stage (the Loan Stage if one was set, otherwise the old
Next Action translated). Prospects keep their old values (nothing is deleted), they are just not asked.
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.fields.seed import sync_catalog

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY = {
    "Documents Pending": "Document collection",
    "Lender Matching": "Identify bank",
    "Login": "Login",
    "Sanction": "Sanction",
    "Disbursed": "Disbursement",
}


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, current_values FROM customers WHERE conversion_status = 'CONVERTED'")).all()
    for cid, vals in rows:
        vals = dict(vals or {})
        stage = vals.pop("loan_stage", None) or LEGACY.get(vals.get("next_action") or "")
        if stage:
            vals["next_action"] = stage
        elif vals.get("next_action") != "Dropped":
            vals.pop("next_action", None)  # an old prospect value such as Qualified is not a stage
        conn.execute(sa.text("UPDATE customers SET current_values = CAST(:v AS jsonb) WHERE id = :id"), {"v": json.dumps(vals), "id": cid})
    for old, new in LEGACY.items():
        conn.execute(sa.text("UPDATE follow_ups SET purpose = :new WHERE purpose = :old"), {"old": old, "new": new})
    conn.execute(sa.text("UPDATE follow_ups SET purpose = NULL WHERE purpose IN ('New', 'Qualified', 'Dropped')"))
    sync_catalog(conn)


def downgrade() -> None:
    pass

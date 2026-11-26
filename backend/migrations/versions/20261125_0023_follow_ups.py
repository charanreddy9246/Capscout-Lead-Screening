"""follow-ups: a table of planned contacts, replacing the single Next Action date

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.fields.seed import sync_catalog

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "follow_ups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("staff_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("meetings.id")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.String(200)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("outcome", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('PENDING', 'DONE')", name="ck_followupstatus"),
    )
    op.create_index("ix_follow_ups_customer_id", "follow_ups", ["customer_id"])
    op.create_index("ix_follow_ups_staff_id", "follow_ups", ["staff_id"])
    op.create_index("ix_follow_ups_status_due", "follow_ups", ["status", "due_at"])

    # Keep what exists: every customer that already has a Next Action Date gets one pending follow-up
    # (10:00 India time, since no time was ever stored). Nothing is deleted; the old values stay as they are.
    op.execute(
        r"""
        INSERT INTO follow_ups (id, customer_id, staff_id, due_at, purpose, status)
        SELECT gen_random_uuid(), c.id, c.owner_staff_id,
               ((c.current_values->>'next_action_date')::date + time '10:00') AT TIME ZONE 'Asia/Kolkata',
               c.current_values->>'next_action', 'PENDING'
        FROM customers c
        WHERE c.current_values->>'next_action_date' ~ '^\d{4}-\d{2}-\d{2}$'
          AND coalesce(c.current_values->>'next_action', '') <> 'Dropped'
        """
    )
    sync_catalog(op.get_bind())  # the new "Follow-up Time" field; Next Visit Date is switched off


def downgrade() -> None:
    op.drop_table("follow_ups")

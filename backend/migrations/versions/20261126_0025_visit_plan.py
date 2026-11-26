"""daily visit plan: priority flag and manual order on follow-ups

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("follow_ups", sa.Column("is_priority", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("follow_ups", sa.Column("sort_order", sa.Integer()))


def downgrade() -> None:
    op.drop_column("follow_ups", "sort_order")
    op.drop_column("follow_ups", "is_priority")

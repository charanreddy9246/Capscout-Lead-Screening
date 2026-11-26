"""staff sign-in: email and 10-digit mobile

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("staff", sa.Column("email", sa.String(254), nullable=True))
    op.add_column("staff", sa.Column("phone", sa.String(10), nullable=True))
    op.create_unique_constraint("uq_staff_email", "staff", ["email"])
    op.create_unique_constraint("uq_staff_phone", "staff", ["phone"])


def downgrade() -> None:
    op.drop_constraint("uq_staff_phone", "staff", type_="unique")
    op.drop_constraint("uq_staff_email", "staff", type_="unique")
    op.drop_column("staff", "phone")
    op.drop_column("staff", "email")

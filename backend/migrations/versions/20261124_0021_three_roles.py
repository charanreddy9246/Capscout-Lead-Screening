"""three roles: SM, ADMIN, SUPER_ADMIN

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_staffrole", "staff", type_="check")
    # Field staff and supervisors both become SMs (the supervisor role is gone).
    op.execute("UPDATE staff SET role = 'SM' WHERE role IN ('FIELD_STAFF', 'SUPERVISOR')")
    op.create_check_constraint("ck_staffrole", "staff", "role IN ('SM', 'ADMIN', 'SUPER_ADMIN')")


def downgrade() -> None:
    op.drop_constraint("ck_staffrole", "staff", type_="check")
    op.execute("UPDATE staff SET role = 'FIELD_STAFF' WHERE role = 'SM'")
    op.execute("UPDATE staff SET role = 'ADMIN' WHERE role = 'SUPER_ADMIN'")
    op.create_check_constraint("ck_staffrole", "staff", "role IN ('FIELD_STAFF', 'SUPERVISOR', 'ADMIN')")

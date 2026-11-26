"""staff: sign in by email; the employee code is dropped

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-26

Everybody now has an email and signs in with it. An account created before this that has no email
(the first Super Admin, made from the command line) gets a placeholder `<code>@capscout.local`, so it can
still sign in; change it with `create_staff.py ... --update-contact --email real@address`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE staff SET email = lower(employee_code) || '@capscout.local' WHERE email IS NULL OR email = ''")
    op.alter_column("staff", "email", existing_type=sa.String(254), nullable=False)
    op.drop_column("staff", "employee_code")  # takes its unique constraint with it


def downgrade() -> None:
    op.add_column("staff", sa.Column("employee_code", sa.String(32), nullable=True))
    op.execute("UPDATE staff SET employee_code = upper(split_part(email, '@', 1)) || substr(id::text, 1, 4)")
    op.alter_column("staff", "employee_code", nullable=False)
    op.create_unique_constraint("staff_employee_code_key", "staff", ["employee_code"])
    op.alter_column("staff", "email", existing_type=sa.String(254), nullable=True)

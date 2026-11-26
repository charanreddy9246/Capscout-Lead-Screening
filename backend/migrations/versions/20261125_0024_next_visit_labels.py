"""Next Visit Date and Time labels

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op

from app.fields.seed import sync_catalog

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sync_catalog(op.get_bind())


def downgrade() -> None:
    pass

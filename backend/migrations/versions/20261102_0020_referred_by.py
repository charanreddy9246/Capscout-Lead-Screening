"""Source Name is now labelled Referred By

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-02
"""
from typing import Sequence, Union

from alembic import op

from app.fields.seed import sync_catalog

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sync_catalog(op.get_bind())


def downgrade() -> None:
    pass

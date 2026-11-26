"""customers.zoho_deal_id: the Zoho Deal a lead became

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("zoho_deal_id", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_customers_zoho_deal_id", "customers", ["zoho_deal_id"])


def downgrade() -> None:
    op.drop_constraint("uq_customers_zoho_deal_id", "customers", type_="unique")
    op.drop_column("customers", "zoho_deal_id")

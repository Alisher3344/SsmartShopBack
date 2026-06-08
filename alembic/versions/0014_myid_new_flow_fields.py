"""MyID SDK new flow uchun qo'shimcha maydonlar.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-03

Yangi:
- users.myid_reuid_expires_at — reuid amal qilish muddati (secondary flow)
- users.myid_comparison_value — yuz solishtirish reytingi (0.000-1.000)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("myid_reuid_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("myid_comparison_value", sa.Numeric(4, 3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "myid_comparison_value")
    op.drop_column("users", "myid_reuid_expires_at")

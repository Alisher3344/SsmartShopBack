"""MyID javobini xom JSONB sifatida saqlash uchun maydon.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-25

Yangi:
- users.myid_raw — `/api/v1/users/me` dan kelgan to'liq JSON
  (kelajakda field mapping, audit, qo'shimcha scoring uchun)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("myid_raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "myid_raw")

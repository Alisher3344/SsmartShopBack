"""MyID identifikatsiyasi uchun User maydonlari.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-21

Yangi:
- users.myid_passport_serial — MyID qaytargan pasport seriasi (AA1234567 kabi)
- users.myid_verified_at — Oxirgi muvaffaqiyatli MyID tasdig'i vaqti
- users.myid_reuid — SDK new flow uchun qayta foydalanish ID'si
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("myid_passport_serial", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("myid_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users", sa.Column("myid_reuid", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "myid_reuid")
    op.drop_column("users", "myid_verified_at")
    op.drop_column("users", "myid_passport_serial")

"""Atmos integratsiyasidan voz kechish — payment_transactions va bound_cards drop

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-21

Atmos kodlari va endpointlaridan to'liq voz kechildi. Tegishli jadvallar dropped.
Order.payment_method va Order.payment_status saqlanadi — yangi payment provider
ulanganda qayta ishlatiladi.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS payment_transactions CASCADE")
    op.execute("DROP TABLE IF EXISTS bound_cards CASCADE")


def downgrade() -> None:
    # Downgrade qo'llab-quvvatlanmaydi — atmos kodi olib tashlandi.
    # Agar kerak bo'lsa, 0002/0003/0005 migrationlarini qayta ishlatib bo'lmaydi
    # chunki model fayllar yo'q. Yangi payment integratsiyasidan keyin yangi schema.
    pass

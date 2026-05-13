"""SMS-OTP test foydalanuvchilarini tozalash + phone unique partial index

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-13

Sabab:
- SMS-OTP login eski flow'da foydalanuvchini darrov yaratardi (parol yo'q).
- Yangi flow: register (phone + OTP + parol + ism) yoki login (phone + parol).
- Eski phone-only test userlarni o'chiramiz (parol yo'q, telegram yo'q),
  ular yangi flow orqali qaytadan ro'yxatdan o'tishadi.
- Phone ustuniga partial unique index — null bo'lmagan qiymatlar uchun.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Eski SMS-OTP test foydalanuvchilarni o'chirish:
    # - role = 'user' (oddiy foydalanuvchi, admin emas)
    # - hashed_password NULL (parol o'rnatilmagan)
    # - telegram_id NULL (Telegram orqali kelmagan)
    # - email NULL (email orqali ro'yxatdan o'tmagan)
    # Bularning orders/reviews'i CASCADE/SET NULL bilan tegishli ravishda hal bo'ladi.
    op.execute("""
        DELETE FROM users
        WHERE role = 'user'
          AND hashed_password IS NULL
          AND telegram_id IS NULL
          AND email IS NULL
    """)

    # Phone raqamlarni normallashtirish — "+998..." yoki "998..." bo'lib chalkashmasin
    # Faqat raqamlar qoldiradi (998xxxxxxxxx formati)
    op.execute("""
        UPDATE users
        SET phone = regexp_replace(phone, '\\D', '', 'g')
        WHERE phone IS NOT NULL
    """)

    # Endi phone null bo'lmagan qatorlar uchun unique index
    # Partial index — bir nechta NULL ruxsat etiladi, lekin bir xil non-null qiymat takrorlanmaydi
    op.create_index(
        "ux_users_phone_not_null",
        "users",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_users_phone_not_null", table_name="users")
    # O'chirilgan foydalanuvchilarni tiklab bo'lmaydi — downgrade noaniq holatga olib keladi

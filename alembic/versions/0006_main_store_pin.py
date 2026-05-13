"""Default magazinni olib tashlash: orphan ma'lumotlarni asosiy magazinga ko'chirish + is_main

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-13

Maqsad:
- "Default magazin" (store_id IS NULL) tushunchasi olib tashlanadi.
- Orphan products/orders eng kichik id'li mavjud magazinga (SSMART magazin Qarshi, id=1)
  ko'chiriladi.
- `stores.is_main` BOOLEAN ustun qo'shiladi. Faqat bitta magazin is_main=true bo'lishi
  mumkin (partial unique index orqali tekshiriladi).
- Boshlang'ich holatda eng kichik id'li magazin asosiy deb belgilanadi.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) stores.is_main ustuni
    op.add_column(
        "stores",
        sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # 2) Asosiy magazinni belgilash — eng kichik id'li magazin.
    #    SsmartShop production'da bu SSMART magazin Qarshi (id=1).
    op.execute("""
        UPDATE stores
        SET is_main = true
        WHERE id = (SELECT id FROM stores ORDER BY id LIMIT 1)
    """)

    # 3) Orphan products va orders'ni asosiy magazinga ko'chirish.
    op.execute("""
        UPDATE products
        SET store_id = (SELECT id FROM stores WHERE is_main = true LIMIT 1)
        WHERE store_id IS NULL
          AND EXISTS (SELECT 1 FROM stores WHERE is_main = true)
    """)
    op.execute("""
        UPDATE orders
        SET store_id = (SELECT id FROM stores WHERE is_main = true LIMIT 1)
        WHERE store_id IS NULL
          AND EXISTS (SELECT 1 FROM stores WHERE is_main = true)
    """)

    # 4) Partial unique index — bir vaqtning o'zida faqat 1 ta is_main=true bo'lishi mumkin.
    op.create_index(
        "ux_stores_is_main_true",
        "stores",
        ["is_main"],
        unique=True,
        postgresql_where=sa.text("is_main = true"),
    )


def downgrade() -> None:
    op.drop_index("ux_stores_is_main_true", table_name="stores")
    op.drop_column("stores", "is_main")
    # products/orders'ni "orphan" ga qaytarmaymiz — bu ma'lumotni buzgan bo'lardi

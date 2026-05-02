"""
Berilgan ID bo'yicha mahsulotlarni DB dan o'chiradi.
Bog'liq sharhlar (reviews) CASCADE bilan avtomatik o'chiriladi.
Buyurtmalardagi snapshot (orders.items) saqlanadi (tarix uchun).

Foydalanish:
  python delete_products.py 4 5
"""
import asyncio
import sys

from sqlalchemy import delete, select

from app.db.database import AsyncSessionLocal
from app.models.product import Product


async def main(ids: list[int]):
    async with AsyncSessionLocal() as db:
        # Topilganlarni ko'rsatamiz
        res = await db.execute(select(Product).where(Product.id.in_(ids)))
        existing = list(res.scalars().all())
        if not existing:
            print(f"Hech qaysi ID topilmadi: {ids}")
            return

        print("O'chiriladigan mahsulotlar:")
        for p in existing:
            name = (p.name or {}).get("uz", "—")
            print(f"  • #{p.id}: {name}  (store_id={p.store_id}, stock={p.stock})")

        # O'chirish
        result = await db.execute(delete(Product).where(Product.id.in_(ids)))
        await db.commit()
        print(f"\n[OK] {result.rowcount} ta mahsulot o'chirildi")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default: 4 va 5
        ids = [4, 5]
        print(f"-> Default ID lar: {ids}")
    else:
        ids = [int(x) for x in sys.argv[1:]]
    asyncio.run(main(ids))

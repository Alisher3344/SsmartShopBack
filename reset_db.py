"""
DB'ni butunlay drop qilib qaytadan yaratadi.
Backend keyingi safar ishga tushganda lifespan'da:
  - Database va jadvallarni qaytadan yaratadi
  - Superadmin foydalanuvchini seed qiladi (superadmin@ssmart.uz / super123)
  - Default pickup point'ni yaratadi

Foydalanish:
  1. Avval uvicorn'ni to'xtating (Ctrl+C)
  2. python reset_db.py
  3. uvicorn app.main:app --reload
"""
import asyncio
from urllib.parse import urlparse

import asyncpg

from app.core.config import settings


async def main():
    parsed = urlparse(settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql"))
    db_name = parsed.path.lstrip("/")

    print(f"-> {db_name} database'ga ulanyapmiz...")
    conn = await asyncpg.connect(
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
        database="postgres",
    )
    try:
        # Boshqa ulanishlarni majburan yopish (drop uchun shart)
        print("-> Eski ulanishlarni yopyapmiz...")
        await conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1 AND pid <> pg_backend_pid()
            """,
            db_name,
        )

        print(f"-> {db_name} drop qilinmoqda...")
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        print(f"-> {db_name} qaytadan yaratildi")
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()

    print("\n[OK] Database tozalandi.")
    print("Endi uvicorn'ni ishga tushiring — superadmin avtomatik yaratiladi:")
    print("  username: superadmin")
    print("  email:    superadmin@ssmart.uz")
    print("  password: super123")


if __name__ == "__main__":
    asyncio.run(main())

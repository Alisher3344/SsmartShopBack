import json
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from app.core.config import settings
from app.core.telegram_bot import start_bot, stop_bot
from app.db.database import AsyncSessionLocal, Base, engine
from app.routers import banner as banner_router
from app.routers import order as order_router
from app.routers import pickup_point as pickup_point_router
from app.routers import product as product_router
from app.routers import review as review_router
from app.routers import sales_admin as sales_admin_router
from app.routers import staff_admin as staff_admin_router
from app.routers import store as store_router
from app.routers import upload as upload_router
from app.routers import user as user_router
from app.services import pickup_point_service, user_service

# Modellar - Base.metadata to'liq bo'lishi uchun import qilamiz
from app.models import auth_session as _auth_session_model  # noqa: F401
from app.models import banner as _banner_model  # noqa: F401
from app.models import order as _order_model  # noqa: F401
from app.models import pickup_point as _pickup_point_model  # noqa: F401
from app.models import product as _product_model  # noqa: F401
from app.models import review as _review_model  # noqa: F401
from app.models import store as _store_model  # noqa: F401
from app.models import user as _user_model  # noqa: F401

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def ensure_database_exists():
    """ssmartshop DB mavjud bo'lmasa - yaratamiz."""
    parsed = urlparse(settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql"))
    db_name = parsed.path.lstrip("/")
    conn = await asyncpg.connect(
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"[startup] '{db_name}' database yaratildi")
    finally:
        await conn.close()


# users jadvalining yangi (Telegram) ustunlari uchun yengil migratsiya
USER_TABLE_MIGRATIONS = [
    "ALTER TABLE users ALTER COLUMN email DROP NOT NULL",
    "ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_id BIGINT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(64)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(32)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pickup_point_id INTEGER REFERENCES pickup_points(id) ON DELETE SET NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(64)",
    # Eski userlarga email prefiksidan username generatsiya qilamiz (NULL bo'lsa)
    "UPDATE users SET username = SPLIT_PART(email, '@', 1) WHERE username IS NULL AND email IS NOT NULL",
    # Duplikat username'larga _id qo'shamiz (unique index buzilmasligi uchun)
    """
    UPDATE users u SET username = u.username || '_' || u.id
    FROM (
        SELECT id, username,
               ROW_NUMBER() OVER (PARTITION BY username ORDER BY id) AS rn
        FROM users WHERE username IS NOT NULL
    ) d
    WHERE u.id = d.id AND d.rn > 1
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_id ON users (telegram_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)",
    # Orders jadvalining yangi ustunlari
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS pickup_code VARCHAR(16)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS transit_code VARCHAR(16)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS received_at TIMESTAMP WITH TIME ZONE",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP WITH TIME ZONE",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_pickup_code ON orders (pickup_code)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_transit_code ON orders (transit_code)",
    # Products jadvali: ko'p rasm
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS images JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_popular BOOLEAN NOT NULL DEFAULT FALSE",
    # Magazinlar (Store)
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id) ON DELETE SET NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id) ON DELETE SET NULL",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id) ON DELETE SET NULL",
    # Bannerlar: til bo'yicha rasm (UZ + RU)
    "ALTER TABLE banners ADD COLUMN IF NOT EXISTS image_uz TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE banners ADD COLUMN IF NOT EXISTS image_ru TEXT NOT NULL DEFAULT ''",
    # Mavjud bannerlarda image qiymatini ikkala tilga ko'chiramiz
    "UPDATE banners SET image_uz = image WHERE image_uz = '' AND image <> ''",
    "UPDATE banners SET image_ru = image WHERE image_ru = '' AND image <> ''",
    # Banner joyi (slot): 'home' (karusel) yoki 'bu' (/b-u sahifa)
    "ALTER TABLE banners ADD COLUMN IF NOT EXISTS slot VARCHAR(20) NOT NULL DEFAULT 'home'",
    # Products: yetkazib berish kuni (admin tanlaydi: 1/3/5/7 ...)
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS delivery_days INTEGER NOT NULL DEFAULT 3",
]


def fetch_telegram_bot_username(token: str) -> str | None:
    """Telegram getMe orqali bot username olish."""
    if not token:
        return None
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
        if data.get("ok"):
            return data["result"].get("username")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"[startup] Telegram getMe xatosi: {e}")
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_database_exists()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Har bir migratsiya alohida tranzaksiyada — bittasi yiqilsa,
    # qolganlari ishlayveradi (eski DB bilan moslik uchun)
    for stmt in USER_TABLE_MIGRATIONS:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
        except Exception as e:
            print(f"[migration] '{stmt[:60].strip()}...' o'tkazildi: {e}")

    # Telegram bot username avto-aniqlash
    if settings.TELEGRAM_BOT_TOKEN and not settings.TELEGRAM_BOT_USERNAME:
        username = fetch_telegram_bot_username(settings.TELEGRAM_BOT_TOKEN)
        if username:
            settings.TELEGRAM_BOT_USERNAME = username
            print(f"[startup] Telegram bot: @{username}")
        else:
            print("[startup] Telegram bot username aniqlab bo'lmadi (token noto'g'ri yoki internet yo'q)")

    # Faqat super admin foydalanuvchisi
    async with AsyncSessionLocal() as db:
        await user_service.ensure_admin_user(
            db, "superadmin@ssmart.uz", "pa$$_sSm@rt_shop-_-", "Super Admin", "superadmin",
            username="!ogin_Ssm@rt_shop#",
        )
        await pickup_point_service.ensure_default_point(db)

    # Telegram botni ishga tushiramiz
    await start_bot()
    try:
        yield
    finally:
        await stop_bot()


app = FastAPI(title="SSMART API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/")
async def root():
    return {"status": "ok", "service": "ssmart-api"}


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(user_router.router, prefix="/api")
app.include_router(product_router.router, prefix="/api")
app.include_router(banner_router.router, prefix="/api")
app.include_router(pickup_point_router.router, prefix="/api")
app.include_router(sales_admin_router.router, prefix="/api")
app.include_router(order_router.router, prefix="/api")
app.include_router(review_router.router, prefix="/api")
app.include_router(store_router.router, prefix="/api")
app.include_router(staff_admin_router.router, prefix="/api")
app.include_router(upload_router.router, prefix="/api")

import json
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import settings
from app.core.telegram_bot import start_bot, stop_bot
from app.db.database import AsyncSessionLocal, engine
from app.routers import banner as banner_router
from app.routers import bound_card as bound_card_router
from app.routers import order as order_router
from app.routers import payment as payment_router
from app.routers import pickup_point as pickup_point_router
from app.routers import product as product_router
from app.routers import review as review_router
from app.routers import sales_admin as sales_admin_router
from app.routers import scoring as scoring_router
from app.routers import staff_admin as staff_admin_router
from app.routers import store as store_router
from app.routers import upload as upload_router
from app.routers import sms_otp as sms_otp_router
from app.routers import admin_users as admin_users_router
from app.routers import mobile as mobile_router
from app.routers import user as user_router
from app.services import pickup_point_service, user_service

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# alembic.ini backend root'da (Dockerfile uni /app ga ko'chiradi)
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


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


def _alembic_config(connection: Connection) -> AlembicConfig:
    cfg = AlembicConfig(str(ALEMBIC_INI))
    cfg.attributes["connection"] = connection
    return cfg


def _run_alembic(connection: Connection) -> None:
    """Alembic upgrade head — yangi/normal DB uchun.

    Mavjud (alembic'sgacha bo'lgan) DB'da `alembic_version` jadvali yo'q,
    lekin biznes jadvallar bor. Bunda 0001 migration'ni qayta yugurtirib
    bo'lmaydi — `stamp head` qilamiz, keyin upgrade (no-op).
    """
    has_alembic_table = connection.execute(
        text("SELECT to_regclass('public.alembic_version')")
    ).scalar()
    has_users_table = connection.execute(
        text("SELECT to_regclass('public.users')")
    ).scalar()

    cfg = _alembic_config(connection)

    if has_alembic_table is None and has_users_table is not None:
        print("[alembic] Mavjud DB topildi (alembic_version yo'q) — stamp head qilinmoqda")
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")
    print("[alembic] upgrade head bajarildi")


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

    # Schema migratsiyalari endi to'liq Alembic orqali
    async with engine.begin() as conn:
        await conn.run_sync(_run_alembic)

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
app.include_router(sms_otp_router.router, prefix="/api")
app.include_router(admin_users_router.router, prefix="/api")
app.include_router(mobile_router.router, prefix="/api")
app.include_router(product_router.router, prefix="/api")
app.include_router(banner_router.router, prefix="/api")
app.include_router(pickup_point_router.router, prefix="/api")
app.include_router(sales_admin_router.router, prefix="/api")
app.include_router(order_router.router, prefix="/api")
app.include_router(payment_router.router, prefix="/api")
app.include_router(bound_card_router.router, prefix="/api")
app.include_router(scoring_router.router, prefix="/api")
app.include_router(review_router.router, prefix="/api")
app.include_router(store_router.router, prefix="/api")
app.include_router(staff_admin_router.router, prefix="/api")
app.include_router(upload_router.router, prefix="/api")

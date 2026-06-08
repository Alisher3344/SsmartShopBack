import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

# Logging — uvicorn'dan oldin (basicConfig force=True bilan uvicorn'ning
# default handlerlarini almashtiramiz). Aks holda `logging.getLogger(__name__)`
# ishlatadigan app-level loglar (myid callback debug, exception trace) docker
# stdout'ga chiqmaydi. uvicorn.access/error loglari ham shu yo'l orqali ketadi.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
# uvicorn lifespan startup'idan keyin root level WARNING'ga qaytariladi.
# Shuning uchun bizning `app.*` namespace logger'lari uchun aniq INFO
# level qo'yamiz — child logger'lar (app.access, app.routers.myid, ...)
# bu level'ni inherit qiladi va root.level'ga bog'liq bo'lmaydi.
logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger(__name__).info("Logging initialised (stdout, INFO+, app namespace)")

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
from app.db.database import AsyncSessionLocal, engine
from app.routers import banner as banner_router
from app.routers import instalment as instalment_router
from app.routers import katm as katm_router
from app.routers import order as order_router
from app.routers import pickup_point as pickup_point_router
from app.routers import product as product_router
from app.routers import review as review_router
from app.routers import sales_admin as sales_admin_router
from app.routers import scoring as scoring_router
from app.routers import staff_admin as staff_admin_router
from app.routers import store as store_router
from app.routers import tv_admins as tv_admins_router
from app.routers import tv_carousel as tv_carousel_router
from app.routers import pro_carousel as pro_carousel_router
from app.routers import upload as upload_router
from app.routers import sms_otp as sms_otp_router
from app.routers import admin_users as admin_users_router
from app.routers import mobile as mobile_router
from app.routers import mobile_katm as mobile_katm_router
from app.routers import mobile_myid as mobile_myid_router
from app.routers import myid as myid_router
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # uvicorn boshlanish paytida o'z LOGGING_CONFIG'i orqali root logger
    # handlerlarini tozalaydi. Lifespan startup'da basicConfig'ni qayta
    # qo'llab, application loglar (myid debug, exceptions) stdout'ga
    # chiqishini ta'minlaymiz. force=True majburiy.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logging.getLogger("app").setLevel(logging.INFO)
    logging.getLogger("app.main").info("Lifespan startup — logging re-applied (app=INFO)")

    await ensure_database_exists()

    # Schema migratsiyalari to'liq Alembic orqali
    async with engine.begin() as conn:
        await conn.run_sync(_run_alembic)

    # Faqat super admin foydalanuvchisi
    async with AsyncSessionLocal() as db:
        await user_service.ensure_admin_user(
            db, "superadmin@ssmart.uz", "pa$$_sSm@rt_shop-_-", "Super Admin", "superadmin",
            username="!ogin_Ssm@rt_shop#",
        )
        await pickup_point_service.ensure_default_point(db)

    yield


# Swagger UI'da tag'lar shu tartibda chiqadi. Mantiqiy guruhlar:
# autentifikatsiya → katalog → buyurtma → admin → utility.
OPENAPI_TAGS = [
    # Autentifikatsiya
    {"name": "users", "description": "Ro'yxatdan o'tish, login, parol tiklash, profil (SMS OTP + email)"},
    {"name": "myid", "description": "MyID (Uzinfocom) biometrik identifikatsiya — OAuth redirect va QR inplace"},
    # Katalog (publik)
    {"name": "products", "description": "Mahsulotlar katalogi (ko'p tilli, ko'p rasm, badges, specifications)"},
    {"name": "banners", "description": "Bosh sahifa banner'lari (UZ/RU rasm, slot bo'yicha)"},
    {"name": "stores", "description": "Magazinlar (asosiy magazin + filiallar)"},
    {"name": "reviews", "description": "Mahsulot sharhlari — faqat yetkazib berilgan buyurtma uchun"},
    # Buyurtma flow
    {"name": "orders", "description": "Buyurtma lifecycle: confirmed → ready → delivered"},
    {"name": "pickup-points", "description": "Punktlar (qabul/topshirish), transit/pickup code'lar"},
    {"name": "instalment", "description": "Paymo orqali rassrochka — yaratish, status, bekor qilish"},
    {"name": "scoring", "description": "Paymo karta scoring — kredit baholash uchun"},
    {"name": "katm", "description": "KATM kredit byurosi — kredit tarixi va ban tekshiruvi"},
    # Admin
    {"name": "admin-users", "description": "Superadmin: barcha foydalanuvchilarni boshqarish"},
    {"name": "sales-admins", "description": "Sotuv admini paneli — magazin mahsulotlari va buyurtmalar"},
    {"name": "staff", "description": "Magazin xodimi paneli (staff role)"},
    # Utility
    {"name": "upload", "description": "Rasm yuklash (admin only) — /uploads ga saqlanadi"},
]

app = FastAPI(
    title="SSMART API",
    version="0.3.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

_access_log = logging.getLogger("app.access")


_logger_recovery_done = False


def _ensure_app_logging():
    """Boshqa kutubxonalar (prometheus_fastapi_instrumentator yoki uvicorn)
    `dictConfig(disable_existing_loggers=True)` orqali bizning `app.*`
    loggerlarni o'chirib qo'yishi mumkin, va root StreamHandler'ni stderr'ga
    rebind qilishi mumkin. Birinchi request'da bularni qayta to'g'rilaymiz —
    tezkor va idempotent.
    """
    global _logger_recovery_done
    if _logger_recovery_done:
        return
    _logger_recovery_done = True
    for name in ("app", "app.main", "app.access", "app.routers.myid"):
        lg = logging.getLogger(name)
        lg.disabled = False
        lg.setLevel(logging.INFO)
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.StreamHandler) and h.stream is not sys.stdout:
            h.stream = sys.stdout


@app.middleware("http")
async def _log_requests(request, call_next):
    """Har bir HTTP so'rovni log qiladi."""
    import time as _t
    _ensure_app_logging()
    start = _t.monotonic()
    try:
        response = await call_next(request)
        elapsed_ms = (_t.monotonic() - start) * 1000
        _access_log.info(
            "%s %s%s -> %d (%.0fms)",
            request.method,
            request.url.path,
            ("?" + request.url.query) if request.url.query else "",
            response.status_code,
            elapsed_ms,
        )
        return response
    except Exception:
        elapsed_ms = (_t.monotonic() - start) * 1000
        _access_log.exception(
            "%s %s -> EXCEPTION (%.0fms)",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Flutter mobile ilova uchun alohida sub-application — alohida Swagger
# (/api/mobile/docs) va alohida OpenAPI (/api/mobile/openapi.json).
mobile_app = FastAPI(
    title="SSMART Mobile API",
    description="Flutter APK uchun shop-only API: auth, profil, katalog, buyurtmalar, sharhlar.",
    version="0.3.0",
    openapi_tags=[
        {"name": "mobile", "description": "Flutter mobile ilova endpointlari"},
    ],
    servers=[{"url": "/api/mobile", "description": "Mount prefix"}],
)
mobile_app.include_router(mobile_router.router)
mobile_app.include_router(mobile_myid_router.router)
mobile_app.include_router(mobile_katm_router.router)
app.mount("/api/mobile", mobile_app)

# Ssmart TV uchun alohida sub-application — alohida Swagger (/api/tv/docs)
# va alohida OpenAPI (/api/tv/openapi.json). Hozircha bo'sh skeleton:
# TV endpointlari (tv_carousel, tv_admins, ...) keyin shu yerga ko'chiriladi.
tv_app = FastAPI(
    title="SSMART TV API",
    description="Ssmart TV uchun alohida API: karusel, TV adminlar, ...",
    version="0.3.0",
    openapi_tags=[
        {"name": "tv", "description": "Ssmart TV endpointlari"},
    ],
    servers=[{"url": "/api/tv", "description": "Mount prefix"}],
)
app.mount("/api/tv", tv_app)

# Ssmart Ustalar (Pro) uchun alohida sub-application — alohida Swagger
# (/api/pro/docs) va alohida OpenAPI (/api/pro/openapi.json). Hozircha bo'sh
# skeleton: Ustalar endpointlari (pro_carousel, ...) keyin shu yerga ko'chiriladi.
pro_app = FastAPI(
    title="SSMART Ustalar API",
    description="Ssmart Ustalar (Pro) uchun alohida API: karusel, ...",
    version="0.3.0",
    openapi_tags=[
        {"name": "pro", "description": "Ssmart Ustalar (Pro) endpointlari"},
    ],
    servers=[{"url": "/api/pro", "description": "Mount prefix"}],
)
app.mount("/api/pro", pro_app)

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/")
async def root():
    return {"status": "ok", "service": "ssmart-api"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Autentifikatsiya ---
app.include_router(user_router.router, prefix="/api")
app.include_router(sms_otp_router.router, prefix="/api")
# MyID OAuth callback'lari `/auth/myid/*` da (Jasur tomonida shu URL'lar
# ro'yxatga olingan). API emas, balki tashqi tizim webhook'lari.
app.include_router(myid_router.router)

# Mobile API alohida sub-app sifatida `/api/mobile`'ga mount qilingan (yuqorida).
# Swagger: /api/mobile/docs

# --- Katalog (publik) ---
app.include_router(product_router.router, prefix="/api")
app.include_router(banner_router.router, prefix="/api")
app.include_router(store_router.router, prefix="/api")
app.include_router(review_router.router, prefix="/api")

# --- Buyurtma flow ---
app.include_router(order_router.router, prefix="/api")
app.include_router(pickup_point_router.router, prefix="/api")
app.include_router(instalment_router.router, prefix="/api")
app.include_router(scoring_router.router, prefix="/api")
app.include_router(katm_router.router, prefix="/api")

# --- Admin panellar ---
app.include_router(admin_users_router.router, prefix="/api")
app.include_router(sales_admin_router.router, prefix="/api")
app.include_router(staff_admin_router.router, prefix="/api")
app.include_router(tv_admins_router.router, prefix="/api")
app.include_router(tv_carousel_router.router, prefix="/api")
app.include_router(pro_carousel_router.router, prefix="/api")

# --- Utility ---
app.include_router(upload_router.router, prefix="/api")

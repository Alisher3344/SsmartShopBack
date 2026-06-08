"""Alembic environment — async-aware.

DB URL'ni `app.core.config.settings.DATABASE_URL` dan oladi.
Ikki rejimda ishlaydi:
  * CLI: `alembic upgrade head` — o'zi async engine yaratadi.
  * Dasturiy: `main.py` lifespan ichidan run_sync orqali sync `Connection`
    yuboriladi (`config.attributes["connection"]`).
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.config import settings
from app.db.database import Base

# Modellarni import qilamiz — Base.metadata to'liq bo'lishi uchun
from app.models import banner  # noqa: F401
from app.models import instalment  # noqa: F401
from app.models import katm  # noqa: F401
from app.models import order  # noqa: F401
from app.models import pickup_point  # noqa: F401
from app.models import product  # noqa: F401
from app.models import review  # noqa: F401
from app.models import sms_otp  # noqa: F401
from app.models import store  # noqa: F401
from app.models import user  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# settings.DATABASE_URL formati: postgresql+asyncpg://...
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    # main.py lifespan'dan kelgan sync `Connection` (run_sync wrapper) — uni ishlatamiz.
    existing_connection = config.attributes.get("connection", None)
    if existing_connection is not None:
        do_run_migrations(existing_connection)
        return

    # CLI yo'l: URL async (asyncpg) bo'lsa async engine, aks holda sync engine.
    url = config.get_main_option("sqlalchemy.url", "")
    if "+asyncpg" in url or "+aiosqlite" in url:
        asyncio.run(run_async_migrations())
    else:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            do_run_migrations(connection)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

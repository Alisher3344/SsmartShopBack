import hashlib
import hmac
import logging
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import ProfileUpdate, TelegramAuthIn, UserCreate

log = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


def _delete_uploaded_file(url: str | None) -> None:
    """Eski rasm faylini /uploads dan o'chiradi (mavjud bo'lsa)."""
    if not url or not url.startswith("/uploads/"):
        return
    fname = url.rsplit("/", 1)[-1]
    # Xavfsizlik: traversal'ga ruxsat bermaslik
    if not fname or "/" in fname or fname.startswith("."):
        return
    fpath = UPLOAD_DIR / fname
    try:
        if fpath.is_file():
            fpath.unlink()
    except OSError as e:
        log.warning("Eski rasm o'chirilmadi: %s — %s", fpath, e)

TELEGRAM_AUTH_MAX_AGE = 86400  # 1 kun


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, login: str, password: str) -> User | None:
    """login - username yoki email."""
    user = await get_user_by_username(db, login)
    if not user:
        user = await get_user_by_email(db, login)
    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        return None
    return user


async def get_user_by_telegram_id(db: AsyncSession, telegram_id: int) -> User | None:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def list_pickup_admins(db: AsyncSession, pickup_point_id: int) -> list[User]:
    """Berilgan pickup point uchun barcha adminlar ro'yxati."""
    result = await db.execute(
        select(User)
        .where(
            User.pickup_point_id == pickup_point_id,
            User.role == "pickup_admin",
        )
        .order_by(User.id.asc())
    )
    return list(result.scalars().all())


async def get_pickup_admin_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id, User.role == "pickup_admin")
    )
    return result.scalar_one_or_none()


async def create_pickup_admin(
    db: AsyncSession,
    pickup_point_id: int,
    *,
    username: str,
    password: str,
    full_name: str,
    phone: str,
) -> User:
    user = User(
        username=username,
        full_name=full_name,
        phone=phone,
        hashed_password=hash_password(password),
        role="pickup_admin",
        is_active=True,
        pickup_point_id=pickup_point_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_pickup_admin(
    db: AsyncSession,
    user: User,
    *,
    username: str | None = None,
    password: str | None = None,
    full_name: str | None = None,
    phone: str | None = None,
    is_active: bool | None = None,
) -> User:
    if username is not None:
        user.username = username
    if password:
        user.hashed_password = hash_password(password)
    if full_name is not None:
        user.full_name = full_name
    if phone is not None:
        user.phone = phone
    if is_active is not None:
        user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    return user


async def delete_pickup_admin(db: AsyncSession, user: User) -> None:
    await db.delete(user)
    await db.commit()


# ===== Sotuv adminlari (mahsulot/banner ruxsati) =====

async def list_sales_admins(db: AsyncSession) -> list[User]:
    result = await db.execute(
        select(User).where(User.role == "admin").order_by(User.id.asc())
    )
    return list(result.scalars().all())


async def get_sales_admin_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id, User.role == "admin")
    )
    return result.scalar_one_or_none()


async def create_sales_admin(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    full_name: str,
    phone: str | None = None,
    store_id: int | None = None,
) -> User:
    user = User(
        username=username,
        full_name=full_name,
        phone=phone,
        hashed_password=hash_password(password),
        role="admin",
        is_active=True,
        store_id=store_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_sales_admin(
    db: AsyncSession,
    user: User,
    *,
    username: str | None = None,
    password: str | None = None,
    full_name: str | None = None,
    phone: str | None = None,
    is_active: bool | None = None,
    store_id: int | None = None,
) -> User:
    if username is not None:
        user.username = username
    if password:
        user.hashed_password = hash_password(password)
    if full_name is not None:
        user.full_name = full_name
    if phone is not None:
        user.phone = phone
    if is_active is not None:
        user.is_active = is_active
    if store_id is not None:
        user.store_id = store_id
    await db.commit()
    await db.refresh(user)
    return user


async def delete_sales_admin(db: AsyncSession, user: User) -> None:
    await db.delete(user)
    await db.commit()


# ===== Staff (Magazin admini) — alohida rol =====

async def list_staff_admins(db: AsyncSession, store_id: int | None = None) -> list[User]:
    q = select(User).where(User.role == "staff").order_by(User.id.asc())
    if store_id is not None:
        q = q.where(User.store_id == store_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_staff_admin_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id, User.role == "staff")
    )
    return result.scalar_one_or_none()


async def create_staff_admin(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    full_name: str,
    store_id: int,
    phone: str | None = None,
) -> User:
    user = User(
        username=username,
        full_name=full_name,
        phone=phone,
        hashed_password=hash_password(password),
        role="staff",
        is_active=True,
        store_id=store_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_staff_admin(
    db: AsyncSession,
    user: User,
    *,
    username: str | None = None,
    password: str | None = None,
    full_name: str | None = None,
    phone: str | None = None,
    is_active: bool | None = None,
    store_id: int | None = None,
) -> User:
    if username is not None:
        user.username = username
    if password:
        user.hashed_password = hash_password(password)
    if full_name is not None:
        user.full_name = full_name
    if phone is not None:
        user.phone = phone
    if is_active is not None:
        user.is_active = is_active
    if store_id is not None:
        user.store_id = store_id
    await db.commit()
    await db.refresh(user)
    return user


async def delete_staff_admin(db: AsyncSession, user: User) -> None:
    await db.delete(user)
    await db.commit()


def verify_telegram_auth(data: TelegramAuthIn, bot_token: str) -> bool:
    """Telegram Login Widget'dan kelgan ma'lumotlarni tekshirish."""
    if not bot_token:
        return False
    if abs(time.time() - data.auth_date) > TELEGRAM_AUTH_MAX_AGE:
        return False
    payload = data.model_dump(exclude_none=True)
    received_hash = payload.pop("hash", None)
    if not received_hash:
        return False
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, received_hash)


async def get_user_by_phone(db: AsyncSession, phone: str) -> User | None:
    result = await db.execute(select(User).where(User.phone == phone))
    return result.scalar_one_or_none()


async def update_profile(db: AsyncSession, user: User, data: ProfileUpdate) -> User:
    """Profil yangilash: ism + familiya → full_name, tug'ilgan kun, rasm.
    Yangi rasm yuborilsa, eski rasm fayli o'chiriladi."""
    sent = data.model_fields_set

    # Ism + familiya birlashtirish (har birini alohida yuborish mumkin)
    first = (data.first_name or '').strip() if 'first_name' in sent else None
    last = (data.last_name or '').strip() if 'last_name' in sent else None

    if 'first_name' in sent or 'last_name' in sent:
        current_full = (user.full_name or '').strip()
        parts = current_full.split(' ', 1) if current_full else ['', '']
        cur_first = parts[0] if len(parts) > 0 else ''
        cur_last = parts[1] if len(parts) > 1 else ''
        new_first = first if first is not None else cur_first
        new_last = last if last is not None else cur_last
        combined = f"{new_first} {new_last}".strip()
        user.full_name = combined or None

    if 'birth_date' in sent:
        user.birth_date = data.birth_date

    if 'photo_url' in sent:
        new_url = data.photo_url
        old_url = user.photo_url
        if new_url != old_url:
            _delete_uploaded_file(old_url)
        user.photo_url = new_url

    await db.commit()
    await db.refresh(user)
    return user


async def get_or_create_phone_user(
    db: AsyncSession,
    phone: str,
    telegram_id: int | None = None,
    telegram_username: str | None = None,
    full_name: str | None = None,
) -> User:
    """Telefon raqam bo'yicha foydalanuvchi topish yoki yaratish (Bot OTP login uchun)."""
    user = None
    if telegram_id:
        user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        user = await get_user_by_phone(db, phone)
    if user:
        # Profilni yangilab turamiz
        user.phone = phone
        if telegram_id:
            user.telegram_id = telegram_id
        if telegram_username:
            user.telegram_username = telegram_username
        if full_name:
            user.full_name = full_name
        await db.commit()
        await db.refresh(user)
        return user
    user = User(
        phone=phone,
        telegram_id=telegram_id,
        telegram_username=telegram_username,
        full_name=full_name or f"+{phone}",
        role="user",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_or_create_telegram_user(db: AsyncSession, data: TelegramAuthIn) -> User:
    user = await get_user_by_telegram_id(db, data.id)
    full_name = " ".join(filter(None, [data.first_name, data.last_name])) or data.username or f"tg_{data.id}"
    if user:
        # Profilni yangilab turamiz
        user.full_name = full_name
        user.telegram_username = data.username
        user.photo_url = data.photo_url
        await db.commit()
        await db.refresh(user)
        return user
    user = User(
        telegram_id=data.id,
        telegram_username=data.username,
        full_name=full_name,
        photo_url=data.photo_url,
        role="user",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def ensure_admin_user(
    db: AsyncSession, email: str, password: str, full_name: str, role: str,
    username: str | None = None,
) -> User:
    """Yaratadi yoki yangilaydi - parol/rol har startda kafolatlanadi."""
    user = await get_user_by_email(db, email)
    if user:
        user.hashed_password = hash_password(password)
        user.role = role
        user.full_name = full_name
        user.is_active = True
        if username:
            user.username = username
        await db.commit()
        await db.refresh(user)
        print(f"[seed] Admin user yangilandi: {email} (role={role})")
        return user
    user = User(
        email=email,
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    print(f"[seed] Yangi admin user yaratildi: {email} (role={role})")
    return user

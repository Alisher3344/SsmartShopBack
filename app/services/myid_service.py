"""MyID identifikatsiyasi uchun shared service.

Web (OAuth redirect, `routers/myid.py`) va Mobile (SDK new flow,
`routers/mobile_myid.py`) router'lari shu service'dan foydalanadi.

Web javob shakli: `info` = profile dict (common_data, doc_data, ...) bevosita.
Mobile (new flow) javob shakli: `raw` = `{data: {profile: {...}, comparison_value, ...}, reuid: {...}}`,
`info` = `raw.data.profile`. Service `raw`'dan `comparison_value` va `reuid`'ni
o'qiydi (mavjud bo'lsa).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


def parse_myid_date(raw: str) -> date | None:
    """MyID `DD.MM.YYYY` yoki ISO sanani Python date'ga o'tkazadi."""
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


async def find_or_create_user_from_myid(
    db: AsyncSession,
    info: dict[str, Any],
    raw: dict[str, Any] | None = None,
) -> User:
    """MyID'dan kelgan ma'lumotlarga asosan User topish yoki yaratish.

    Strategiya:
      1. Telefon raqam mos kelsa — mavjud User'ga MyID'ni biriktiramiz.
      2. PINFL mos kelsa — biriktiramiz.
      3. Aks holda yangi User yaratamiz.

    Maydon ustunligi:
      - `full_name`, `middlename`, `address`, `birth_date`, `pinfl`,
        `myid_passport_serial` — MyID har doim ustun (qayta scan'da ham yangilanadi)
      - `email`, `phone` — faqat bo'sh bo'lsa to'ldiramiz (foydalanuvchi qo'lda
        boshqa qiymat kiritgan bo'lishi mumkin)
      - `myid_raw` — xom JSON to'liq saqlanadi (kelajakda audit/scoring uchun)
    """
    common = info.get("common_data") if isinstance(info.get("common_data"), dict) else {}
    doc = info.get("doc_data") if isinstance(info.get("doc_data"), dict) else {}
    contacts = info.get("contacts") if isinstance(info.get("contacts"), dict) else {}
    address_obj = info.get("address") if isinstance(info.get("address"), dict) else {}

    pinfl = (
        common.get("pinfl")
        or common.get("pnfl")
        or info.get("pinfl")
        or info.get("pnfl")
    )
    passport_serial = (
        doc.get("pass_data")
        or doc.get("pasport_seria")
        or doc.get("passport_serial")
        or info.get("passport_serial")
    )
    phone = contacts.get("phone") or info.get("phone")
    email = contacts.get("email") or info.get("email")

    first_name = common.get("first_name") or info.get("first_name") or info.get("name")
    middle_name = (
        common.get("middle_name")
        or info.get("middle_name")
        or info.get("middlename")
    )
    last_name = (
        common.get("last_name") or info.get("last_name") or info.get("surname")
    )
    full_name = " ".join(filter(None, [last_name, first_name, middle_name])).strip() or None

    address = (
        address_obj.get("permanent_address")
        or address_obj.get("permanent")
        or address_obj.get("full")
        or info.get("permanent_address")
    )
    if isinstance(address, dict):
        address = address.get("full") or address.get("text") or json.dumps(address, ensure_ascii=False)

    birth_date_raw = (
        common.get("birth_date") or info.get("birth_date") or info.get("date_of_birth")
    )

    norm_phone: str | None = None
    if phone:
        digits = "".join(ch for ch in str(phone) if ch.isdigit())
        if digits.startswith("998") and len(digits) == 12:
            norm_phone = digits
        elif len(digits) == 9:
            norm_phone = "998" + digits

    user: User | None = None
    if norm_phone:
        user = (
            await db.execute(select(User).where(User.phone == norm_phone))
        ).scalar_one_or_none()
    if not user and pinfl:
        user = (
            await db.execute(select(User).where(User.passport == pinfl))
        ).scalar_one_or_none()

    if user is None:
        user = User(
            phone=norm_phone,
            email=email,
            full_name=full_name,
            role="user",
            is_active=True,
        )
        db.add(user)

    if pinfl:
        user.passport = pinfl
    if passport_serial:
        user.myid_passport_serial = passport_serial
    if middle_name:
        user.middlename = middle_name
    if address:
        user.address = str(address)[:512]
    if full_name:
        user.full_name = full_name
    if email and not user.email:
        user.email = email
    if norm_phone and not user.phone:
        user.phone = norm_phone
    if birth_date_raw:
        user.birth_date = parse_myid_date(str(birth_date_raw)) or user.birth_date

    # New flow: comparison_value (yuz solishtirish reytingi) va reuid (qayta-auth)
    if raw is not None:
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        cmp_raw = data.get("comparison_value") if data else raw.get("comparison_value")
        if cmp_raw is not None:
            try:
                user.myid_comparison_value = Decimal(str(cmp_raw))
            except (InvalidOperation, ValueError):
                pass
        reuid_obj = raw.get("reuid")
        if isinstance(reuid_obj, dict):
            reuid_value = reuid_obj.get("value")
            if reuid_value:
                user.myid_reuid = str(reuid_value)
            reuid_exp = reuid_obj.get("expires_at")
            if reuid_exp is not None:
                try:
                    user.myid_reuid_expires_at = datetime.fromtimestamp(
                        int(reuid_exp), tz=timezone.utc
                    )
                except (TypeError, ValueError, OSError):
                    pass
        elif isinstance(reuid_obj, str) and reuid_obj:
            user.myid_reuid = reuid_obj

    user.myid_raw = raw if raw is not None else info
    user.myid_verified_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user)
    return user

"""KATM kredit byurosi servisi (Faza 1 — kredit tarixi tekshiruvi).

Oqim:
  1. record_consent / get_active_consent — mijoz roziligi (pAgreementId/pAgreementDate).
  2. credit_check — claim ro'yxati (KATM-SIR) -> kredit hisoboti (05000 inline yoki
     05050 pending+token). Request handler'da BLOK QILINMAYDI — pending bo'lsa darhol
     token qaytariladi, klient poll_report orqali ko'radi.
  3. poll_report — 05050 hisobotni >=60s interval bilan tekshiradi.
  4. ban_check — kreditlash taqiqi (mustaqil, rozilik/claim shart emas).
"""
from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.katm import KATMBusinessError, KATMError, katm
from app.models.instalment import Instalment
from app.models.katm import KATMConsent, KATMRequest
from app.models.user import User
from app.schemas.katm import BanStatusOut, CreditCheckIn, CreditReportOut
from app.services.instalment_service import _split_name

log = logging.getLogger(__name__)

# Uzbekiston vaqt mintaqasi (+05:00) — KATM sanalari uchun
_UZ_TZ = timezone(timedelta(hours=5))
# Hisobot poll'lari orasidagi minimal interval (KATM talabi: >=60s)
_POLL_MIN_SECONDS = 60


# ===== Formatlash / parse helperlari =====

def _katm_dt(dt: datetime) -> str:
    """yyyy-MM-dd'T'HH:mm:ss.SSSZ (mas. 2026-06-04T12:30:00.000+0500)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UZ_TZ)
    dt = dt.astimezone(_UZ_TZ)
    millis = f"{dt.microsecond // 1000:03d}"
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + millis + dt.strftime("%z")


def _myid_profile(user: User) -> dict[str, Any]:
    """user.myid_raw ikki shaklda bo'lishi mumkin: web (profile to'g'ridan) yoki
    mobile (`{data: {profile: {...}}}`). Profil dict'ini normallashtirib qaytaradi."""
    raw = user.myid_raw if isinstance(user.myid_raw, dict) else {}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else None
    if data and isinstance(data.get("profile"), dict):
        return data["profile"]
    return raw


def _decode_report(b64: str | None, fmt: int) -> tuple[str | None, dict | None]:
    """base64 -> matn; format=1 (JSON) bo'lsa parse qilib dict qaytaradi."""
    if not b64:
        return None, None
    try:
        text = base64.b64decode(b64).decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        log.warning("KATM report base64 decode xatosi: %s", e)
        return None, None
    if fmt == 1:
        try:
            return text, json.loads(text)
        except ValueError:
            return text, None
    return text, None  # XML — matn holida (base64 audit'da qoladi)


def _redact(payload: dict[str, Any]) -> dict[str, Any]:
    """Audit uchun maxfiy maydonlarni (parol, PAN) niqoblaymiz."""
    out = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    sec = out.get("security")
    if isinstance(sec, dict) and "pPassword" in sec:
        sec["pPassword"] = "***"
    return out


# ===== Identifikatsiya mapping =====

def _split_doc(user: User) -> tuple[str | None, str | None, int | None]:
    """(series, number, doc_type) — avval saqlangan KATM ustunlari, keyin
    myid_passport_serial'dan parse (mas. 'AB1234567' -> 'AB', '1234567')."""
    if user.katm_doc_series and user.katm_doc_number:
        return user.katm_doc_series, user.katm_doc_number, user.katm_doc_type

    serial = (user.myid_passport_serial or "").strip().upper()
    m = re.match(r"^([A-Z]+)\s*([0-9]+)$", serial)
    if not m:
        return None, None, None
    series, number = m.group(1)[:5], m.group(2)[:10]

    # doc_type: myid doc_data'dan, aks holda seria naqshidan heuristika
    doc_type: int | None = None
    profile = _myid_profile(user)
    doc = profile.get("doc_data") if isinstance(profile.get("doc_data"), dict) else {}
    raw_type = (
        doc.get("doc_type") or doc.get("document_type") or doc.get("type")
    )
    if raw_type is not None:
        rs = str(raw_type).lower()
        if "id" in rs or rs == "0":
            doc_type = 0
        elif "pass" in rs or rs == "6":
            doc_type = 6
    if doc_type is None:
        # 2 harf + 7 raqam — odatda biometrik pasport (6); aks holda ID karta (0)
        doc_type = 6 if (len(series) == 2 and len(number) == 7) else 0
    return series, number, doc_type


def _resolve_region(user: User, payload: CreditCheckIn) -> tuple[str | None, str | None]:
    """pRegion(2)/pLocalRegion(3) — payload override > saqlangan ustun > myid_raw parse."""
    if payload.region and payload.local_region:
        return payload.region, payload.local_region
    if user.katm_region and user.katm_local_region:
        return user.katm_region, user.katm_local_region

    # myid_raw address scope'idan nomzod kalitlarni qidiramiz
    profile = _myid_profile(user)
    addr = profile.get("address") if isinstance(profile.get("address"), dict) else {}
    region = (
        addr.get("region_id") or addr.get("region_code") or addr.get("region")
        or addr.get("soato_region")
    )
    district = (
        addr.get("district_id") or addr.get("district_code") or addr.get("district")
        or addr.get("soato_district") or addr.get("area")
    )
    region = str(region) if region not in (None, "") else None
    district = str(district) if district not in (None, "") else None
    return region, district


# ===== Rozilik (consent) =====

async def record_consent(
    db: AsyncSession,
    user: User,
    *,
    consent_text: str | None,
    scope: list[str],
    recorded_by: int | None,
) -> KATMConsent:
    """Yangi rozilik yozuvi — agreement_id satr id'dan generatsiya qilinadi (<=10, unique)."""
    consent = KATMConsent(
        user_id=user.id,
        agreement_id="PENDING",  # flush'dan keyin id bilan almashtiramiz
        agreement_date=datetime.now(_UZ_TZ),
        consent_text=consent_text,
        scope=scope,
        recorded_by_user_id=recorded_by,
    )
    db.add(consent)
    await db.flush()  # consent.id olamiz
    consent.agreement_id = f"A{consent.id}"  # unique, <=10 (id juda katta bo'lmaguncha)
    await db.commit()
    await db.refresh(consent)
    return consent


async def get_active_consent(db: AsyncSession, user: User) -> KATMConsent | None:
    res = await db.execute(
        select(KATMConsent)
        .where(KATMConsent.user_id == user.id, KATMConsent.revoked_at.is_(None))
        .order_by(KATMConsent.id.desc())
    )
    return res.scalars().first()


# ===== Validatsiya =====

def _validate_identity(user: User) -> None:
    missing = [f for f in ("passport", "address") if not getattr(user, f)]
    if not user.phone:
        missing.append("phone")
    if not (user.full_name and len(user.full_name.split()) >= 2):
        missing.append("full_name")
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"KATM uchun profil to'liq emas. Yetishmayotgan: {', '.join(missing)}",
        )


def _credit_amount_and_end(
    db_instalment: Instalment | None, payload: CreditCheckIn
) -> tuple[int, str]:
    """pCreditAmount (tiyin) va pCreditEndDate (KATM format)."""
    # 1) Aniq override payload'da
    if payload.credit_amount is not None and payload.credit_end_date:
        end = datetime.strptime(payload.credit_end_date, "%Y-%m-%d").replace(tzinfo=_UZ_TZ)
        return payload.credit_amount, _katm_dt(end)
    # 2) Mavjud Instalment'dan
    if db_instalment is not None:
        amount = payload.credit_amount or int(db_instalment.total_amount)
        end_dt: datetime | None = None
        if db_instalment.start_month and db_instalment.period:
            try:
                yy = int(db_instalment.start_month[:2])
                mm = int(db_instalment.start_month[2:4])
                total = (mm - 1) + int(db_instalment.period)
                year = 2000 + yy + total // 12
                month = total % 12 + 1
                day = min(db_instalment.pay_day or 1, 28)
                end_dt = datetime(year, month, day, tzinfo=_UZ_TZ)
            except (ValueError, IndexError):
                end_dt = None
        if payload.credit_end_date:
            end_dt = datetime.strptime(payload.credit_end_date, "%Y-%m-%d").replace(tzinfo=_UZ_TZ)
        if end_dt is None:
            end_dt = datetime.now(_UZ_TZ) + timedelta(days=365)
        return amount, _katm_dt(end_dt)
    # 3) Faqat tekshiruv uchun — payload yoki nominal
    if payload.credit_amount is None:
        raise HTTPException(
            status_code=422,
            detail="credit_amount kerak (foydalanuvchining aktiv rassrochkasi yo'q)",
        )
    end = (
        datetime.strptime(payload.credit_end_date, "%Y-%m-%d").replace(tzinfo=_UZ_TZ)
        if payload.credit_end_date
        else datetime.now(_UZ_TZ) + timedelta(days=365)
    )
    return payload.credit_amount, _katm_dt(end)


async def _latest_instalment(db: AsyncSession, user_id: int) -> Instalment | None:
    res = await db.execute(
        select(Instalment)
        .where(Instalment.user_id == user_id)
        .order_by(Instalment.id.desc())
    )
    return res.scalars().first()


# ===== Asosiy operatsiyalar =====

async def credit_check(
    db: AsyncSession, payload: CreditCheckIn
) -> CreditReportOut:
    """Claim ro'yxati + kredit hisoboti. Pending bo'lsa darhol token qaytaradi."""
    user = await db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    _validate_identity(user)

    pinfl = (user.passport or "").strip()
    if not re.fullmatch(r"\d{14}", pinfl):
        raise HTTPException(status_code=422, detail="PINFL (passport) 14 raqam bo'lishi kerak")

    series, number, doc_type = _split_doc(user)
    if not series or not number:
        raise HTTPException(
            status_code=422,
            detail="Pasport seria/raqami aniqlanmadi (myid_passport_serial yo'q)",
        )
    region, local_region = _resolve_region(user, payload)
    if not region or not local_region:
        raise HTTPException(
            status_code=422,
            detail="Region/tuman kodi (pRegion/pLocalRegion) aniqlanmadi — region/local_region bering",
        )

    # Rozilik
    consent = await get_active_consent(db, user)
    if consent is None:
        if payload.create_consent:
            consent = await record_consent(
                db, user,
                consent_text=payload.consent_text,
                scope=["credit_report", "ban_check"],
                recorded_by=None,
            )
        else:
            raise HTTPException(
                status_code=409,
                detail="Mijozda faol KATM roziligi yo'q (avval /katm/consent yoki create_consent=true)",
            )

    instalment = await _latest_instalment(db, user.id)
    credit_amount, credit_end = _credit_amount_and_end(instalment, payload)

    # Audit yozuvi — id'dan claim_id/report_id generatsiya
    req = KATMRequest(
        user_id=user.id,
        consent_id=consent.id,
        kind="credit_report",
        report_format=payload.report_format,
        status="CREATED",
    )
    db.add(req)
    await db.flush()
    req.claim_id = f"K{req.id}"
    req.report_id = req.id

    claim_args = dict(
        pClaimId=req.claim_id,
        pClaimDate=_katm_dt(datetime.now(_UZ_TZ)),
        pAgreementId=consent.agreement_id,
        pAgreementDate=_katm_dt(consent.agreement_date),
        pPinfl=pinfl,
        pDocSeries=series,
        pDocNumber=number,
        pDocType=doc_type if doc_type is not None else 6,
        pRegion=region,
        pLocalRegion=local_region,
        pAddress=(user.address or "")[:100],
        pPhone=(user.phone or "")[:13],
        pCreditAmount=credit_amount,
        pCreditEndDate=credit_end,
    )

    # 1) Claim ro'yxati (xatoda /trusted fallback)
    try:
        claim_resp = await katm.register_claim(**claim_args)
    except KATMBusinessError as e:
        trusted_resp = await _try_trusted_claim(user, claim_args, e)
        if trusted_resp is None:
            await _mark_error(db, req, e)
            raise HTTPException(status_code=400, detail=f"KATM {e.code}: {e.message}")
        claim_resp = trusted_resp
    except KATMError as e:
        await _mark_error(db, req, e)
        raise HTTPException(status_code=502, detail=str(e))

    katm_sir = claim_resp.get("clientId")
    if katm_sir:
        user.katm_client_id = str(katm_sir)
        req.katm_client_id = str(katm_sir)
    # Aniqlangan doc/region'ni keyingi safar uchun saqlaymiz
    user.katm_doc_series, user.katm_doc_number, user.katm_doc_type = series, number, doc_type
    user.katm_region, user.katm_local_region = region, local_region
    req.status = "CLAIM_OK"
    req.raw_claim = _redact({"request": claim_args, "response": claim_resp})

    # 2) Kredit hisoboti
    try:
        rep = await katm.get_credit_report(
            pClaimId=req.claim_id,
            pReportId=req.report_id,
            pLang=payload.lang,
            pReportFormat=payload.report_format,
        )
    except KATMBusinessError as e:
        await _mark_error(db, req, e)
        raise HTTPException(status_code=400, detail=f"KATM {e.code}: {e.message}")
    except KATMError as e:
        await _mark_error(db, req, e)
        raise HTTPException(status_code=502, detail=str(e))

    return await _apply_report(db, req, rep)


async def _try_trusted_claim(
    user: User, claim_args: dict[str, Any], err: KATMBusinessError
) -> dict[str, Any] | None:
    """Standart claim xato bo'lganda /trusted bilan urinish (qo'shimcha identity bo'lsa)."""
    profile = _myid_profile(user)
    common = profile.get("common_data") if isinstance(profile.get("common_data"), dict) else {}
    doc = profile.get("doc_data") if isinstance(profile.get("doc_data"), dict) else {}
    first, last, middle = _split_name(user)
    birth = user.birth_date
    issue = doc.get("issue_date") or doc.get("date_issue") or doc.get("doc_give_date")
    expire = doc.get("expiry_date") or doc.get("date_expire") or doc.get("doc_expire_date")
    sex = common.get("sex") or common.get("gender") or doc.get("sex")
    if not (first and last and birth and issue and expire and sex is not None):
        log.info("KATM trusted fallback uchun ma'lumot yetarli emas (err=%s)", err.code)
        return None
    male = 1 if str(sex).lower() in ("1", "m", "male", "erkak") else 2
    try:
        return await katm.register_claim_trusted(
            **claim_args,
            pFirstName=first,
            pLastName=last,
            pMiddleName=middle or None,
            pBirthDate=_katm_dt(datetime(birth.year, birth.month, birth.day, tzinfo=_UZ_TZ)),
            pIssueDocDate=_to_katm_date(issue),
            pExpiredDocDate=_to_katm_date(expire),
            pMale=male,
            pResident=1,
        )
    except (KATMBusinessError, KATMError, ValueError) as e:
        log.warning("KATM trusted fallback ham muvaffaqiyatsiz: %s", e)
        return None


def _to_katm_date(value: Any) -> str:
    """MyID sanasini (yyyy-MM-dd yoki ISO) KATM formatiga keltiradi."""
    s = str(value)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s[:19] if "T" in s else s[:10], fmt)
            return _katm_dt(dt.replace(tzinfo=_UZ_TZ))
        except ValueError:
            continue
    raise ValueError(f"Sana formati noma'lum: {value!r}")


async def _apply_report(
    db: AsyncSession, req: KATMRequest, rep: dict[str, Any]
) -> CreditReportOut:
    """/credit/report yoki /status javobini qayta ishlaydi (ready/pending)."""
    result = str(rep.get("result") or "")
    req.result_code = result
    req.result_message = rep.get("resultMessage")
    req.last_polled_at = datetime.now(timezone.utc)

    if result == "05050":  # tayyorlanmoqda
        req.report_token = rep.get("Token") or rep.get("token") or req.report_token
        req.status = "REPORT_PENDING"
        await db.commit()
        await db.refresh(req)
        return CreditReportOut(
            request_id=req.id,
            status="pending",
            katm_client_id=req.katm_client_id,
            token=req.report_token,
            poll_after_seconds=_POLL_MIN_SECONDS,
            result_code=result,
            result_message=req.result_message,
        )

    # 05000 — tayyor
    b64 = rep.get("reportBase64")
    fmt = req.report_format if req.report_format is not None else 1
    text, decoded = _decode_report(b64, fmt)
    req.report_base64 = b64
    req.report_decoded = decoded
    req.raw_report = _redact({k: v for k, v in rep.items() if k != "reportBase64"})
    req.status = "REPORT_READY"
    await db.commit()
    await db.refresh(req)
    return CreditReportOut(
        request_id=req.id,
        status="ready",
        katm_client_id=req.katm_client_id,
        report=decoded,
        report_base64=None if decoded else b64,
        result_code=result,
        result_message=req.result_message,
    )


async def poll_report(db: AsyncSession, request_id: int) -> CreditReportOut:
    """Pending (05050) hisobotni /credit/report/status orqali tekshiradi."""
    req = await db.get(KATMRequest, request_id)
    if req is None or req.kind != "credit_report":
        raise HTTPException(status_code=404, detail="KATM so'rovi topilmadi")

    if req.status == "REPORT_READY":
        return CreditReportOut(
            request_id=req.id,
            status="ready",
            katm_client_id=req.katm_client_id,
            report=req.report_decoded,
            report_base64=None if req.report_decoded else req.report_base64,
            result_code=req.result_code,
            result_message=req.result_message,
        )
    if req.status != "REPORT_PENDING" or not req.report_token:
        raise HTTPException(
            status_code=409, detail=f"So'rov holati poll uchun mos emas: {req.status}"
        )

    # >=60s floor (KATM rate) — server tomonida himoya
    if req.last_polled_at is not None:
        elapsed = (datetime.now(timezone.utc) - req.last_polled_at).total_seconds()
        if elapsed < _POLL_MIN_SECONDS:
            return CreditReportOut(
                request_id=req.id,
                status="pending",
                katm_client_id=req.katm_client_id,
                token=req.report_token,
                poll_after_seconds=int(_POLL_MIN_SECONDS - elapsed) + 1,
                result_code=req.result_code,
                result_message=req.result_message,
            )

    try:
        rep = await katm.get_credit_report_status(
            pToken=req.report_token,
            pClaimId=req.claim_id,
            pReportFormat=req.report_format if req.report_format is not None else 1,
        )
    except KATMBusinessError as e:
        await _mark_error(db, req, e)
        raise HTTPException(status_code=400, detail=f"KATM {e.code}: {e.message}")
    except KATMError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return await _apply_report(db, req, rep)


async def ban_check(
    db: AsyncSession, *, user_id: int | None = None, pinfl: str | None = None
) -> BanStatusOut:
    """Kreditlash taqiqi tekshiruvi — mustaqil (claim/rozilik shart emas)."""
    resolved_pinfl = pinfl
    uid = user_id
    if not resolved_pinfl and user_id is not None:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
        resolved_pinfl = user.passport
    if not resolved_pinfl or not re.fullmatch(r"\d{14}", resolved_pinfl.strip()):
        raise HTTPException(status_code=422, detail="PINFL 14 raqam bo'lishi kerak")
    resolved_pinfl = resolved_pinfl.strip()

    req = KATMRequest(user_id=uid or 0, kind="ban_check", status="CREATED")
    if uid:
        db.add(req)
        await db.flush()

    try:
        resp = await katm.check_credit_ban(pIdentifier=resolved_pinfl, pSubjectType=2)
    except KATMBusinessError as e:
        if uid:
            await _mark_error(db, req, e)
        raise HTTPException(status_code=400, detail=f"KATM {e.code}: {e.message}")
    except KATMError as e:
        raise HTTPException(status_code=502, detail=str(e))

    status_val = int(resp.get("status") or 0)
    if uid:
        req.ban_status = status_val
        req.status = "BAN_OK"
        req.result_code = str(resp.get("result") or "")
        req.raw_report = _redact(resp)
        await db.commit()
    return BanStatusOut(pinfl=resolved_pinfl, status=status_val, banned=bool(status_val))


async def my_credit_history(
    db: AsyncSession, user: User
) -> tuple[BanStatusOut, CreditReportOut | None]:
    """Mobil self-service "Limitni bilish" oqimi.

    1. MyID tasdiqlangan-yo'qligini tekshiradi (PINFL/pasport bo'lmasa 428 — frontend
       foydalanuvchini avval MyID'ga yo'naltiradi).
    2. Taqiq tekshiruvi — taqiq bo'lsa darhol qaytadi (hisobot so'ralmaydi).
    3. Rozilik (avtomatik yaratiladi) + claim + kredit tarixi.

    Limit BU YERDA hisoblanmaydi — faqat tarix qaytadi (keyingi qadam).
    """
    if not user.passport or not user.myid_passport_serial:
        raise HTTPException(
            status_code=428,  # Precondition Required
            detail="Avval MyID orqali shaxsingizni tasdiqlang",
        )

    ban = await ban_check(db, user_id=user.id)
    if ban.banned:
        return ban, None

    payload = CreditCheckIn(
        user_id=user.id,
        create_consent=True,
        consent_text="Foydalanuvchi mobil ilovada kredit tarixini tekshirishga rozilik berdi",
    )
    credit = await credit_check(db, payload)
    return ban, credit


async def poll_report_for_user(
    db: AsyncSession, request_id: int, user: User
) -> CreditReportOut:
    """poll_report — lekin so'rov current_user'ga tegishliligini tekshiradi."""
    req = await db.get(KATMRequest, request_id)
    if req is None or req.user_id != user.id:
        raise HTTPException(status_code=404, detail="So'rov topilmadi")
    return await poll_report(db, request_id)


async def _mark_error(db: AsyncSession, req: KATMRequest, err: Exception) -> None:
    req.status = "ERROR"
    if isinstance(err, KATMBusinessError):
        req.result_code = str(err.code)
        req.result_message = err.message
    else:
        req.result_message = str(err)
    try:
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()

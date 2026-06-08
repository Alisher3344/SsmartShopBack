"""KATM (Kredit-axborot tahliliy markazi) API klienti — infokredit.uz.

KATM — O'zbekiston kredit byurosi. Bu klient FAZA 1 doirasida kredit tarixi
tekshiruvini qo'llab-quvvatlaydi:
  - claim ro'yxati (KATM-SIR oladi)            POST /claim/registration[/trusted]
  - kredit hisoboti (async, poll bilan)        POST /credit/report[/status]
  - kreditlash taqiqi tekshiruvi               POST /client/credit/ban/status

Auth: Paymo'dan farqli — OAuth/token YO'Q. Har bir so'rov bodysida `security`
bloki (pLogin/pPassword) va tashkilot kodlari (pCode/pHead) yuboriladi.

Javob konvensiyasi:
  {"data": {"result": "05000", "resultMessage": "...", ...}, "code": 200}
  - result "05000" — muvaffaqiyat
  - result "05050" — hisobot async tayyorlanmoqda (XATO EMAS — poll qilish kerak)
  - boshqa result  — biznes xatosi (KATMBusinessError)

Hujjat: KATM API texnologik talab v12.4 (retail).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

# data.result kodlari
_RESULT_SUCCESS = "05000"      # muvaffaqiyat
_RESULT_IN_PROGRESS = "05050"  # hisobot tayyorlanmoqda — /credit/report/status poll


class KATMError(RuntimeError):
    """KATM API ishlamadi (tarmoq, noto'g'ri JSON, 5xx, config yo'q)."""


class KATMBusinessError(KATMError):
    """KATM biznes-mantiq xatosi (data.result success/in-progress emas)."""

    def __init__(self, code: Any, message: str | None = None):
        self.code = code
        self.message = message or ""
        super().__init__(f"KATM error {code}: {message}")


class KATMClient:
    def __init__(self) -> None:
        base = (settings.KATM_BASE_URL or "").rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=base,
            timeout=float(settings.KATM_TIMEOUT or 30),
        )

    # ===== Ichki helperlar =====

    def _security(self) -> dict[str, Any]:
        login = settings.KATM_LOGIN
        pw = settings.KATM_PASSWORD
        if not login or not pw:
            raise KATMError("KATM_LOGIN/KATM_PASSWORD .env'da yo'q")
        return {"pLogin": login, "pPassword": pw}

    def _envelope(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"security": self._security(), "data": data}

    async def _request(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """POST JSON. data['result']'ni qaytaradi — caller 05000/05050 ni tekshiradi."""
        body = self._envelope(data)
        try:
            r = await self._client.post(
                path,
                json=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as e:
            raise KATMError(f"KATM POST {path}: tarmoq xatosi ({e})") from e
        return self._parse_response(path, r)

    @staticmethod
    def _parse_response(path: str, r: httpx.Response) -> dict[str, Any]:
        if r.status_code >= 500:
            raise KATMError(f"KATM {path} {r.status_code}: {r.text!r}")
        try:
            payload = r.json()
        except ValueError:
            raise KATMError(f"KATM {path} {r.status_code}: JSON parse xatosi ({r.text!r})")
        if not isinstance(payload, dict):
            raise KATMError(f"KATM {path}: kutilmagan javob ({payload!r})")
        data = payload.get("data")
        if not isinstance(data, dict):
            # 4xx + data yo'q — errorMessage/error bo'lishi mumkin
            msg = payload.get("errorMessage") or payload.get("error") or r.text
            raise KATMError(f"KATM {path} {r.status_code}: {msg!r}")
        result = str(data.get("result") or "")
        # 05050 (in-progress) — XATO EMAS, caller poll qiladi
        if result and result not in (_RESULT_SUCCESS, _RESULT_IN_PROGRESS):
            raise KATMBusinessError(result, data.get("resultMessage"))
        return data

    # ===== Public API (Faza 1) =====

    async def register_claim(
        self,
        *,
        pClaimId: str,
        pClaimDate: str,
        pAgreementId: str,
        pAgreementDate: str,
        pPinfl: str,
        pDocSeries: str,
        pDocNumber: str,
        pDocType: int,
        pRegion: str,
        pLocalRegion: str,
        pAddress: str,
        pPhone: str,
        pCreditAmount: int,
        pCreditEndDate: str,
        pCurrency: str | None = None,
    ) -> dict[str, Any]:
        """POST /claim/registration — KATM pasportni tekshiradi, data.clientId (KATM-SIR)."""
        data = {
            "pCode": settings.KATM_CODE,
            "pClaimId": pClaimId,
            "pClaimDate": pClaimDate,
            "pAgreementId": pAgreementId,
            "pAgreementDate": pAgreementDate,
            "pPinfl": pPinfl,
            "pDocSeries": pDocSeries,
            "pDocNumber": pDocNumber,
            "pDocType": pDocType,
            "pRegion": pRegion,
            "pLocalRegion": pLocalRegion,
            "pAddress": pAddress,
            "pPhone": pPhone,
            "pCreditAmount": pCreditAmount,
            "pCurrency": pCurrency or settings.KATM_CURRENCY,
            "pCreditEndDate": pCreditEndDate,
        }
        return await self._request("/claim/registration", data)

    async def register_claim_trusted(
        self,
        *,
        pClaimId: str,
        pClaimDate: str,
        pAgreementId: str,
        pAgreementDate: str,
        pPinfl: str,
        pDocSeries: str,
        pDocNumber: str,
        pDocType: int,
        pRegion: str,
        pLocalRegion: str,
        pAddress: str,
        pPhone: str,
        pCreditAmount: int,
        pCreditEndDate: str,
        pFirstName: str,
        pLastName: str,
        pBirthDate: str,
        pIssueDocDate: str,
        pExpiredDocDate: str,
        pMale: int,
        pResident: int = 1,
        pMiddleName: str | None = None,
        pInn: str | None = None,
        pCurrency: str | None = None,
    ) -> dict[str, Any]:
        """POST /claim/registration/trusted — identifikatsiya maydonlarini o'zimiz beramiz.

        MyID ma'lumotlari to'liq bo'lmaganda yoki standart registratsiyada pasport
        tekshiruvi muvaffaqiyatsiz bo'lganda ishlatiladi.
        """
        data = {
            "pCode": settings.KATM_CODE,
            "pClaimId": pClaimId,
            "pClaimDate": pClaimDate,
            "pAgreementId": pAgreementId,
            "pAgreementDate": pAgreementDate,
            "pPinfl": pPinfl,
            "pDocSeries": pDocSeries,
            "pDocNumber": pDocNumber,
            "pDocType": pDocType,
            "pRegion": pRegion,
            "pLocalRegion": pLocalRegion,
            "pAddress": pAddress,
            "pPhone": pPhone,
            "pResident": pResident,
            "pCreditAmount": pCreditAmount,
            "pCurrency": pCurrency or settings.KATM_CURRENCY,
            "pCreditEndDate": pCreditEndDate,
            "pFirstName": pFirstName,
            "pLastName": pLastName,
            "pBirthDate": pBirthDate,
            "pIssueDocDate": pIssueDocDate,
            "pExpiredDocDate": pExpiredDocDate,
            "pMale": pMale,
        }
        if pMiddleName:
            data["pMiddleName"] = pMiddleName
        if pInn:
            data["pInn"] = pInn
        return await self._request("/claim/registration/trusted", data)

    async def get_credit_report(
        self,
        *,
        pClaimId: str,
        pReportId: int,
        pLang: str = "ru",
        pReportFormat: int = 1,
    ) -> dict[str, Any]:
        """POST /credit/report — pLegal=1 (jismoniy shaxs).

        Javob: result 05000 + reportBase64, YOKI result 05050 + Token (poll kerak).
        """
        data = {
            "pHead": settings.KATM_HEAD,
            "pCode": settings.KATM_CODE,
            "pLegal": 1,
            "pClaimId": pClaimId,
            "pReportId": pReportId,
            "pLang": pLang,
            "pReportFormat": pReportFormat,
        }
        return await self._request("/credit/report", data)

    async def get_credit_report_status(
        self,
        *,
        pToken: str,
        pClaimId: str,
        pReportFormat: int = 1,
    ) -> dict[str, Any]:
        """POST /credit/report/status — 05050 hisobotni poll qilish (>=60s interval)."""
        data = {
            "pHead": settings.KATM_HEAD,
            "pCode": settings.KATM_CODE,
            "pToken": pToken,
            "pClaimId": pClaimId,
            "pReportFormat": pReportFormat,
        }
        return await self._request("/credit/report/status", data)

    async def check_credit_ban(
        self,
        *,
        pIdentifier: str,
        pSubjectType: int = 2,
    ) -> dict[str, Any]:
        """POST /client/credit/ban/status — mustaqil. data.status 1=taqiq aktiv, 0=yo'q."""
        data = {
            "pHead": settings.KATM_HEAD,
            "pCode": settings.KATM_CODE,
            "pIdentifier": pIdentifier,
            "pSubjectType": pSubjectType,
        }
        return await self._request("/client/credit/ban/status", data)

    # === KELAJAK FAZA (hisobot tsikli) — implement qilinmagan ===
    # register_contract  -> POST /contract/registration
    # register_schedule  -> POST /contract/schedule/add
    # register_repayment -> POST /contract/repayment/add

    async def aclose(self) -> None:
        await self._client.aclose()


katm = KATMClient()

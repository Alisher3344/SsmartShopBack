# Paymo integratsiyasi qo'llanmasi

## Umumiy ko'rinish

Paymo (`https://api.paymo.uz`) — kredit skoring va rassrochka (BNPL/instalment)
API'si. SsmartShop backend bu API'ni 5 endpoint orqali ulaydi:

| Paymo endpoint | Maqsad |
|---|---|
| `POST /api/auth/login` | Auth token (klient ichida cache) |
| `POST /scoring/get-monthly` | Karta bo'yicha oylik tushum holati + qarz |
| `POST /instalment/cmn` | Yangi rassrochka yaratish |
| `GET /instalment/cmn/{store_id}/{instalment_id}` | Rassrochka holatini olish |
| `DELETE /instalment/cmn/{store_id}/{instalment_id}` | Rassrochkani bekor qilish |

Eski Atmos to'lov shlyuzi to'liq olib tashlangan (`0009` migration). Eski
`/scoring/score/by-token/{card_token}` Paymo endpoint'i ham yo'q —
`/scoring/get-monthly` bilan almashtirilgan.

---

## Sozlash (.env)

```
PAYMO_BASE_URL=https://api.paymo.uz
PAYMO_USERNAME=<login>
PAYMO_PASSWORD=<parol>
PAYMO_TIMEOUT=20
```

Token klient ichida cache qilinadi. 401 javob kelsa avtomatik qayta login bo'lib
bir marta retry qilinadi (`app/core/paymo.py`).

## Per-Store sozlash

Har bir SsmartShop magazini Paymo'da o'z store ID'iga ega bo'lishi kerak.
Hozircha admin endpoint yo'q — to'g'ridan-to'g'ri DB orqali yoziladi:

```sql
UPDATE stores SET paymo_store_id = <paymo_id> WHERE id = <ssmart_store_id>;
```

`paymo_store_id` NULL bo'lgan magazindan instalment yaratib bo'lmaydi (422 xato).

## Foydalanuvchi KYC profili

Instalment yaratishdan oldin foydalanuvchi quyidagi maydonlarni profiliga
to'ldirishi shart (`PATCH /api/users/me` orqali, `ProfileUpdate` schema):

| Maydon | Format | Izoh |
|---|---|---|
| `passport` | 14 raqam | PINFL/JSHSHIR (Paymo'da `pin` va `passport` ikkalasi uchun ishlatiladi) |
| `middlename` | matn | Otasining ismi |
| `address` | matn | Pasportdagi manzil |
| `address_payer` | matn | Haqiqiy yashash manzili |
| `work_place` | matn | Ish joyi |
| `phone` | `+998...` | Avtomatik tortiladi |
| `full_name` | "Ism Familiya" | Avtomatik split qilinadi |

---

## Lokal endpointlar

### 1. Skoring — `POST /api/scoring/get-monthly` (admin)

Karta bo'yicha 12 oylik tushum holati + mavjud kreditlar.

**Request:**
```json
{
  "card_number": "8600332914249390",
  "card_expiry": "2509",
  "amount": 1000000,
  "percent": 1
}
```

**Response:**
```json
{
  "months": {"2023.01": true, "2023.02": true, "2023.09": false},
  "debt_load": [],
  "bank": "Ипотека банк",
  "holder_name": "GADELSHIN RUSLAN",
  "raw": null
}
```

**Curl:**
```bash
curl -X POST http://localhost:8000/api/scoring/get-monthly \
  -H "Authorization: Bearer <admin_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"card_number":"8600...","card_expiry":"2509","amount":1000000,"percent":1}'
```

### 2. Rassrochka yaratish — `POST /api/instalment` (user)

Order'ga rassrochka biriktirib Paymo'da yaratadi. Avval mijoz buyurtmasini
`payment_method=instalment` bilan yaratishi va profili to'liq bo'lishi shart.

**Talablar:**
- Order: `payment_method=instalment`, `status=pending_payment`, mijoznikiga tegishli
- Magazin: `stores.paymo_store_id` NOT NULL
- User: passport, address, address_payer, work_place, phone, full_name to'liq

**Request:**
```json
{
  "order_id": 123,
  "card_number": "8600332914249390",
  "card_expiry": "2509",
  "total_amount": 1000000,
  "initial_amount": 200000,
  "period": 12,
  "start_month": "2606",
  "pay_day": 15,
  "details": "Buyurtma #123",
  "debit_initial_amount": true,
  "additional_number": "+998901234567",
  "responsible_manager": "Karl"
}
```

**Response (201):**
```json
{
  "id": 1,
  "orderId": 123,
  "userId": 42,
  "storeId": 1,
  "paymoInstalmentId": "178313",
  "paymoStoreId": 7,
  "status": "NOT_CONFIRMED",
  "cardLast4": "9390",
  "cardExpiry": "2509",
  "totalAmount": 1000000,
  "initialAmount": 200000,
  "period": 12,
  "startMonth": "2606",
  "payDay": 15,
  "holderName": "GADELSHIN RUSLAN",
  "bank": "Ипотека банк",
  "phoneNumber": "+998901234567",
  "contractFileUrl": null,
  "balance": null,
  "offer": null,
  ...
}
```

Paymo `confirm_by_sms=true` bilan chaqirilgani uchun karta egasi telefoniga
SMS yuboradi. Tasdiqlash Paymo'ning o'zida amalga oshiriladi.

### 3. Holat polling — `GET /api/instalment/{id}?sync=true` (user)

Mijoz har 5-10 sekundda chaqirib statusni kuzatadi. `sync=true` (default)
Paymo'dan oxirgi statusni oladi.

**Response:** to'liq `InstalmentOut` (yuqoridagi shaklda).

**Status o'tishlari:**
- `NOT_CONFIRMED` — yaratildi, mijoz SMS bilan tasdiqlamadi
- `CONFIRMED` / `ACTIVE` — tasdiqlandi → Order avtomatik `confirmed`, `payment_status=paid`, `transit_code` generatsiya
- `CANCELLED` / `FAILED` / `REJECTED` — Paymo rad etdi → Order `cancelled`, stock qaytarildi
- `CLOSED` — to'lab tugatildi

### 4. Bekor qilish — `DELETE /api/instalment/{id}` (user/admin)

- Mijoz: faqat `NOT_CONFIRMED` da
- Admin: har qachon (Paymo'ning rad etishini ko'rsatadi)

Muvaffaqiyatli bo'lsa: lokal `CANCELLED` + Order bekor qilinadi + stock
qaytariladi.

---

## Order ↔ Instalment lifecycle

```
1. POST /api/orders {payment_method: "instalment"}
   → order.status = pending_payment
   → order.payment_status = pending
   → transit_code yo'q (hali)

2. (mijoz profilini to'ldiradi) PATCH /api/users/me
   → passport, address, address_payer, work_place, middlename

3. POST /api/instalment {order_id, card, amount, period, ...}
   → Paymo: POST /instalment/cmn  [confirm_by_sms=true]
   → Instalment(status=NOT_CONFIRMED) saqlanadi
   → Paymo SMS yuboradi mijoz telefoniga

4. GET /api/instalment/{id}?sync=true   [har 5-10s]
   → Paymo: GET /instalment/cmn/{store}/{id}
   → status o'zgargani sezilsa:
        CONFIRMED/ACTIVE → finalize_after_payment(order)
                          → order.status=confirmed,
                             payment_status=paid,
                             transit_code yaratiladi
        CANCELLED/FAILED → restore_stock + order.status=cancelled

5. DELETE /api/instalment/{id}  (optional)
   → Paymo: DELETE /instalment/cmn/{store}/{id}
   → lokal CANCELLED + order bekor qilinadi
```

---

## Xatoliklar

| HTTP | Sabab |
|---|---|
| 400 | Paymo business error (yetarli pul yo'q, karta noto'g'ri, va h.k.) — `detail` ichida `Paymo <code>: <description>` |
| 403 | Boshqaning instalmenti |
| 404 | Order/Instalment topilmadi |
| 409 | Order uchun aktiv instalment allaqachon mavjud |
| 422 | Mijoz KYC to'liq emas, yoki magazinda paymo_store_id NULL |
| 502 | Paymo tarmoq xatosi |

---

## Test (sandbox)

1. `.env` ga `PAYMO_USERNAME`/`PAYMO_PASSWORD` yozish
2. Backend qayta yig'ish: `cd /opt/app && docker compose up -d --build back`
3. Migration `0010` avtomatik qo'llaniladi (lifespan ichida)
4. Test store uchun `paymo_store_id` o'rnatish:
   ```sql
   UPDATE stores SET paymo_store_id = <sandbox_id> WHERE is_main = true;
   ```
5. Admin sifatida skoring sinab ko'rish:
   ```bash
   curl -X POST http://localhost:8000/api/scoring/get-monthly \
     -H "Authorization: Bearer <admin>" \
     -d '{"card_number":"8600332914249390","card_expiry":"2509","amount":1000000,"percent":1}'
   ```
6. Test user profilini to'ldirish (PATCH /api/users/me)
7. Order yaratish: `payment_method=instalment`, mahsulot store'i `paymo_store_id` ga ega bo'lsin
8. `POST /api/instalment` — `NOT_CONFIRMED` qaytishi kerak, mijoz telefoniga SMS keladi
9. Polling: `GET /api/instalment/{id}` — Paymo SMS tasdiqlangach `ACTIVE` ga o'tadi va Order ham `confirmed` bo'ladi
10. Negative test: `DELETE` yangi yaratilgan `NOT_CONFIRMED` instalmentni → CANCELLED

---

## Kritik fayllar

- `app/core/paymo.py` — HTTP klient
- `app/services/scoring_service.py` — skoring servisi
- `app/services/instalment_service.py` — instalment biznes-mantiq
- `app/routers/scoring.py`, `app/routers/instalment.py` — endpointlar
- `app/models/instalment.py` — DB modeli
- `app/models/user.py` — KYC ustunlar
- `app/models/store.py` — `paymo_store_id`
- `alembic/versions/0010_instalment_paymo.py` — schema migration

## Xavfsizlik eslatmalari

- Karta raqami (PAN) **hech qaerda saqlanmaydi** — faqat `card_last4` va `card_expiry` lokalga yoziladi
- `raw_create_response` audit ichida ham `card_number` va `pin` mask qilinadi (`****<last4>`)
- `passport` (PINFL) User profilida saqlanadi — DB orqali olinadi, hech qachon javobda HTTP orqali boshqa userga ko'rsatilmaydi
- Paymo login parol .env'da (production .env'ni gitga commit qilmang!)

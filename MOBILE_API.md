# SsmartShop Mobile API (Flutter APK uchun)

Bu hujjat Flutter ilovasi uchun ajratilgan **shop-only** API'ni tasvirlaydi.
Admin / super admin / sotuv admin / punkt admin endpointlari bu yerga kirmaydi.

## Asosiy ma'lumotlar

| Maydon | Qiymat |
|---|---|
| **Base URL (production)** | `https://api-application.ssmart.uz/api/mobile` |
| **Auth sxemasi** | Bearer JWT (`Authorization: Bearer <access_token>`) |
| **Format** | JSON (`Content-Type: application/json`) |
| **Til** | UZ + RU (mahsulot/banner nomlari `{uz, ru}` JSON objektida) |
| **Sana/vaqt** | ISO-8601 UTC, masalan `"2026-05-14T10:00:00Z"` |
| **Telefon formati** | xalqaro, prefiksiz: `"998901234567"` |
| **Kod TTL** | OTP — 5 min, registration_token — 10 min, reset_token — 10 min |

OpenAPI ko'rish: `https://api-application.ssmart.uz/docs`

## Auth oqimi

### Ro'yxatdan o'tish (Register)

```
1. POST /auth/register/request   { phone }                → 204 (SMS yuborildi)
                                                          → 409 hisob mavjud
2. POST /auth/register/verify    { phone, code }          → { registration_token }
3. POST /auth/register/complete  { registration_token,
                                   password, full_name }  → { access_token, user }
```

### Kirish (Login)

```
POST /auth/login   { phone, password }   → { access_token, user }
                                          → 404 hisob yo'q
                                          → 401 parol noto'g'ri
                                          → 429 ko'p urinish (15 min lock)
```

### Parolni tiklash

```
1. POST /auth/password-reset/request   { phone }            → 204
                                                            → 404 hisob yo'q
2. POST /auth/password-reset/verify    { phone, code }      → { reset_token }
3. POST /auth/password-reset/complete  { reset_token,
                                         password }        → { access_token, user }
```

Token'ni saqlash uchun `flutter_secure_storage` tavsiya etiladi.

## Endpoint ro'yxati

### 🔐 AUTH (auth talab qilinmaydi)

| Method | Path | Body | Javob |
|---|---|---|---|
| POST | `/auth/login` | `{phone, password}` | `Token` |
| POST | `/auth/register/request` | `{phone}` | 204 |
| POST | `/auth/register/verify` | `{phone, code}` | `{registration_token, expires_in}` |
| POST | `/auth/register/complete` | `{registration_token, password, full_name}` | `Token` |
| POST | `/auth/password-reset/request` | `{phone}` | 204 |
| POST | `/auth/password-reset/verify` | `{phone, code}` | `{reset_token, expires_in}` |
| POST | `/auth/password-reset/complete` | `{reset_token, password}` | `Token` |

**Parol qoidalari:** 6–128 belgi, kamida 1 katta harf (A-Z), kamida 1 raqam (0-9).

### 👤 PROFILE (Bearer auth)

| Method | Path | Tafsilot |
|---|---|---|
| GET | `/me` | Joriy foydalanuvchi (UserOut) |
| PATCH | `/me/profile` | `{first_name?, last_name?, birth_date?, photo_url?}` |
| POST | `/me/avatar` | multipart `file=...` → `{url}` |

Rasm yuklash oqimi: avval `/me/avatar` ga fayl yuborib URL olinadi, so'ngra `/me/profile` ga `photo_url` o'sha URL bilan yuboriladi. Eski rasm avtomatik o'chiriladi.

### 🛍 CATALOG (auth talab qilinmaydi)

| Method | Path | Query | Javob |
|---|---|---|---|
| GET | `/products` | `category, subcategory, q, only_sale` | `ProductOut[]` |
| GET | `/products/{id}` | — | `ProductOut` |
| GET | `/banners` | — | `BannerOut[]` (faqat active) |
| GET | `/stores` | — | `StoreOut[]` (faqat active, asosiy birinchi) |

### 📦 ORDERS (Bearer auth)

| Method | Path | Body | Javob |
|---|---|---|---|
| POST | `/orders` | `OrderCreate` | `Order` |
| GET | `/orders/my` | — | `Order[]` |
| GET | `/orders/{id}` | — | `Order` |
| POST | `/orders/{id}/cancel` | — | `Order` |

**Cancel shartlari:** faqat `status in ('pending', 'confirmed')`.

### ⭐ REVIEWS

| Method | Auth | Path | Body | Javob |
|---|---|---|---|---|
| GET | public | `/reviews/product/{product_id}` | — | `ReviewOut[]` |
| GET | Bearer | `/reviews/my-pending` | — | `PendingReviewItem[]` |
| GET | Bearer | `/reviews/my` | — | `ReviewOut[]` |
| POST | Bearer | `/reviews` | `ReviewCreate` | `ReviewOut` |

## Schemalar (asosiylari)

### Token
```json
{
  "access_token": "eyJhbGciOiJI...",
  "token_type": "bearer",
  "user": { /* UserOut */ }
}
```

### UserOut
```json
{
  "id": 17,
  "email": null,
  "username": null,
  "full_name": "Alisher Aliqulov",
  "role": "user",
  "is_active": true,
  "telegram_id": null,
  "telegram_username": null,
  "photo_url": "/uploads/abc123.jpg",
  "phone": "998908999209",
  "birth_date": "1995-08-21",
  "pickup_point_id": null,
  "store_id": null,
  "created_at": "2026-05-14T12:34:56Z"
}
```

### ProductOut (asosiy maydonlar)
```json
{
  "id": 11,
  "name":        {"uz": "iPhone 15", "ru": "iPhone 15"},
  "description": {"uz": "...",       "ru": "..."},
  "category": "large-appliances",
  "subcategory": "phones",
  "price": 12500000,
  "oldPrice": 13500000,
  "stock": 5,
  "rating": 4.8,
  "creditMonths": 12,
  "deliveryDays": 3,
  "image": "/uploads/xxx.jpg",
  "images": ["/uploads/xxx.jpg", "/uploads/yyy.jpg"],
  "badges": ["new"],
  "onSale": true,
  "conditionNote": null,
  "specifications": [
    {"valueUz":"Ekran","valueRu":"Экран","isDual":true,"value2Uz":"6.1","value2Ru":"6.1"}
  ],
  "storeId": 1,
  "reviewsCount": 12,
  "avgRating": 4.7
}
```

### OrderCreate (so'rov)
```json
{
  "deliveryType": "pickup",         // "pickup" | "courier"
  "deliveryAddress": null,           // courier bo'lsa to'ldiriladi
  "pickupPointId": 1,                // pickup bo'lsa
  "paymentMethod": "cash",          // "cash" | "card"
  "items": [
    {"productId": 11, "qty": 1}
  ]
}
```

### Order (javob)
```json
{
  "id": 42,
  "status": "ready",
  "items": [{"productId":11,"name":{"uz":"iPhone 15"},"qty":1,"price":12500000,"image":"..."}],
  "total": 12500000,
  "deliveryType": "pickup",
  "deliveryAddress": null,
  "pickupPointId": 1,
  "pickupPointName":    {"uz":"...","ru":"..."},
  "pickupPointAddress": {"uz":"...","ru":"..."},
  "paymentMethod": "cash",
  "paymentStatus": null,
  "transitCode": null,         // foydalanuvchiga ko'rinmaydi
  "pickupCode":  "12345678",   // status=ready bo'lsa to'ldiriladi
  "receivedAt": "2026-05-14T10:00:00Z",
  "createdAt":  "2026-05-13T09:00:00Z",
  "updatedAt":  "2026-05-14T10:00:00Z"
}
```

**Status oqimi:**
`pending` → `confirmed` → `ready` (foydalanuvchi SMS oladi: 8 xonali `pickupCode`) → `delivered`
`cancelled` — istalgan vaqtda

### Telefon raqami formati
Inputga: `"+998 90 899 92 09"` yoki `"998908999209"` — backend faqat raqamlarni qoldirib, `998xxxxxxxxx` formatga keltiradi.

## Flutter integratsiyasi misoli

### `pubspec.yaml`
```yaml
dependencies:
  http: ^1.2.0
  flutter_secure_storage: ^9.0.0
  dio: ^5.4.0   # ixtiyoriy, interceptor uchun qulay
```

### `api_client.dart`
```dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiClient {
  static const _baseUrl = 'https://api-application.ssmart.uz/api/mobile';
  final _storage = const FlutterSecureStorage();

  Future<Map<String, String>> _headers({bool auth = false}) async {
    final h = {'Content-Type': 'application/json'};
    if (auth) {
      final token = await _storage.read(key: 'access_token');
      if (token != null) h['Authorization'] = 'Bearer $token';
    }
    return h;
  }

  Future<dynamic> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool auth = false,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final headers = await _headers(auth: auth);
    final bodyJson = body == null ? null : jsonEncode(body);

    final res = await switch (method) {
      'GET'    => http.get(uri, headers: headers),
      'POST'   => http.post(uri, headers: headers, body: bodyJson),
      'PATCH'  => http.patch(uri, headers: headers, body: bodyJson),
      'DELETE' => http.delete(uri, headers: headers),
      _        => throw 'Unknown method $method',
    };

    if (res.statusCode == 204) return null;
    final decoded = res.body.isEmpty ? null : jsonDecode(res.body);
    if (res.statusCode >= 400) {
      throw ApiException(res.statusCode, decoded?['detail'] ?? 'Xato');
    }
    return decoded;
  }

  // ====== AUTH ======
  Future<void> sendRegisterOtp(String phone) async {
    await _request('POST', '/auth/register/request', body: {'phone': phone});
  }

  Future<String> verifyRegisterOtp(String phone, String code) async {
    final res = await _request('POST', '/auth/register/verify',
        body: {'phone': phone, 'code': code});
    return res['registration_token'];
  }

  Future<Map<String, dynamic>> completeRegister(
      String regToken, String password, String fullName) async {
    final res = await _request('POST', '/auth/register/complete', body: {
      'registration_token': regToken,
      'password': password,
      'full_name': fullName,
    });
    await _storage.write(key: 'access_token', value: res['access_token']);
    return res['user'];
  }

  Future<Map<String, dynamic>> login(String phone, String password) async {
    final res = await _request('POST', '/auth/login',
        body: {'phone': phone, 'password': password});
    await _storage.write(key: 'access_token', value: res['access_token']);
    return res['user'];
  }

  // ====== CATALOG ======
  Future<List<dynamic>> products({String? category, String? q}) async {
    final qs = <String, String>{};
    if (category != null) qs['category'] = category;
    if (q != null) qs['q'] = q;
    final query = qs.entries.map((e) => '${e.key}=${Uri.encodeComponent(e.value)}').join('&');
    return await _request('GET', '/products${query.isEmpty ? "" : "?$query"}');
  }

  Future<List<dynamic>> banners() async => await _request('GET', '/banners');
  Future<List<dynamic>> stores()  async => await _request('GET', '/stores');

  // ====== PROFILE ======
  Future<Map<String, dynamic>> me() async => await _request('GET', '/me', auth: true);

  Future<Map<String, dynamic>> updateProfile({
    String? firstName, String? lastName, String? birthDate, String? photoUrl,
  }) async {
    final body = <String, dynamic>{};
    if (firstName != null) body['first_name'] = firstName;
    if (lastName != null)  body['last_name']  = lastName;
    if (birthDate != null) body['birth_date'] = birthDate;
    if (photoUrl != null)  body['photo_url']  = photoUrl;
    return await _request('PATCH', '/me/profile', body: body, auth: true);
  }

  Future<String> uploadAvatar(String filePath) async {
    final token = await _storage.read(key: 'access_token');
    final req = http.MultipartRequest('POST', Uri.parse('$_baseUrl/me/avatar'));
    req.headers['Authorization'] = 'Bearer $token';
    req.files.add(await http.MultipartFile.fromPath('file', filePath));
    final res = await http.Response.fromStream(await req.send());
    if (res.statusCode >= 400) throw ApiException(res.statusCode, res.body);
    return jsonDecode(res.body)['url'];
  }

  // ====== ORDERS ======
  Future<Map<String, dynamic>> createOrder(Map<String, dynamic> body) async =>
      await _request('POST', '/orders', body: body, auth: true);

  Future<List<dynamic>> myOrders() async =>
      await _request('GET', '/orders/my', auth: true);

  Future<Map<String, dynamic>> cancelOrder(int id) async =>
      await _request('POST', '/orders/$id/cancel', auth: true);
}

class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);
  @override
  String toString() => '[$status] $message';
}
```

## Rasm URL'larini ko'rsatish

Backend `photo_url`, `image`, `images[]` maydonlarini **relative** yo'l ko'rinishida qaytaradi (`/uploads/xxx.jpg`). To'liq URL'ga aylantirish:

```dart
String resolveImageUrl(String? url) {
  if (url == null || url.isEmpty) return '';
  if (url.startsWith('http')) return url;
  return 'https://api-application.ssmart.uz$url';
}
```

## Xato kodlari

| Status | Sabab |
|---|---|
| 400 | Validatsiya yoki noto'g'ri ma'lumot |
| 401 | Token yo'q yoki yaroqsiz |
| 404 | Resurs topilmadi |
| 409 | Konflikt (masalan, telefon allaqachon ro'yxatdan o'tgan) |
| 413 | Fayl juda katta (avatar 5 MB chegarasi) |
| 429 | Rate limit |
| 502 | Eskiz SMS gateway ishlamayapti |

Xato javob formati:
```json
{ "detail": "Bu raqamda hisob yaratilmagan. Ro'yxatdan o'ting." }
```

## Eskiz SMS

Foydalanuvchi quyidagi holatlarda SMS oladi:
1. **OTP** (ro'yxatdan o'tish va parolni tiklash) — `Ssmart Shop saytiga kirish uchun tasdiqlash kodi: 1234`
2. **Buyurtma topshirish punktiga keldi** — `Ssmart Shop: Mahsulotingiz keldi - <name>. Buyurtmani olish uchun shu kodni ayting: 12345678`

Flutter ilovaning sintaksis bilan aralashmagan, SMS qabul qilish OS tomonida kechadi (ilova hech narsa qilmaydi — faqat foydalanuvchi kodni qo'lda kiritadi).

## OpenAPI

Swagger UI orqali to'liq schemalarni ko'rish (test qilish ham mumkin):

```
https://api-application.ssmart.uz/docs
```

Mobile endpointlarni filterlash uchun `mobile` tag tanlang.

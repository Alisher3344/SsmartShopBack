from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    CORS_ORIGINS: str = "http://localhost:5173"
    # Eskiz SMS gateway
    ESKIZ_BASE_URL: str = "https://notify.eskiz.uz/api"
    ESKIZ_EMAIL: str = ""
    ESKIZ_PASSWORD: str = ""
    ESKIZ_SENDER_NICK: str = "4546"
    SMS_OTP_TEMPLATE: str = (
        "Ssmart Shop saytiga kirish uchun tasdiqlash kodi: {code}. "
        "Kodni hech kimga bermang!"
    )
    # Punkt mahsulotni qabul qilganda foydalanuvchiga yuboriladigan SMS shabloni.
    # Placeholder'lar: {product} — mahsulot nomi (yoki "Buyurtma"), {code} — 8 xonali pickup kodi.
    SMS_PICKUP_TEMPLATE: str = (
        "Ssmart Shop: Mahsulotingiz keldi - {product}. "
        "Buyurtmani olish uchun shu kodni ayting: {code}"
    )
    # Paymo / Atmos Partner API (scoring + instalment + transactions).
    # OAuth2 client credentials:
    #   POST {AUTH_BASE_URL}/token  Basic base64(CK:CS) grant_type=client_credentials
    # Token TTL: 3600s (har soatda yangilanadi, 401 da avto-relogin).
    PAYMO_BASE_URL: str = "https://api.paymo.uz"
    PAYMO_AUTH_BASE_URL: str = "https://partner.atmos.uz"
    PAYMO_CONSUMER_KEY: str = ""
    PAYMO_CONSUMER_SECRET: str = ""
    PAYMO_TIMEOUT: int = 20

    # MyID OAuth (Redirect + QR inplace) — devmyid.uz / myid.uz
    MYID_OAUTH_BASE_URL: str = "https://devmyid.uz"
    MYID_OAUTH_CLIENT_ID: str = ""
    MYID_OAUTH_CLIENT_SECRET: str = ""
    # Scope: vergul bilan ajratilgan ro'yxat. Asosiy: common_data (FIO, DOB, photo),
    # doc_data (passport), address, contacts (phone, email)
    MYID_OAUTH_SCOPE: str = "common_data,doc_data,address,contacts"
    # strong = yuz skani majburiy, simple = faqat birinchi marta
    MYID_OAUTH_METHOD: str = "strong"
    # MyID adminida ro'yxatdan o'tgan callback URL — bayt-baytda mos kelishi shart
    MYID_OAUTH_REDIRECT_URI: str = ""
    MYID_OAUTH_TIMEOUT: int = 15
    # Foydalanuvchini callback'dan keyin shu sahifaga qaytaramiz (tokenni hash bilan)
    MYID_FRONTEND_SUCCESS_URL: str = "https://ssmart.uz/auth/myid/success"
    MYID_FRONTEND_FAIL_URL: str = "https://ssmart.uz/auth/myid/fail"

    # MyID Backend API / Mobile SDK (api.devmyid.uz / api.myid.uz)
    MYID_SDK_BASE_URL: str = "https://api.devmyid.uz"
    MYID_SDK_CLIENT_ID: str = ""
    MYID_SDK_CLIENT_SECRET: str = ""
    MYID_SDK_CLIENT_HASH_ID: str = ""
    # RSA public key (PEM body, BEGIN/END qatorlarisiz)
    MYID_SDK_CLIENT_HASH: str = ""

    # KATM (Kredit-axborot tahliliy markazi, infokredit.uz) — kredit tarixi tekshiruvi.
    # Private tarmoq/VPN orqali kiriladi (test 10.22.50.210 / prod 10.22.50.220).
    # OAuth YO'Q: security.pLogin/pPassword + org pCode/pHead HAR so'rov bodysida ketadi.
    KATM_BASE_URL: str = "https://api.infokredit.uz/katm-api/v1"
    KATM_LOGIN: str = ""        # security.pLogin
    KATM_PASSWORD: str = ""     # security.pPassword
    KATM_CODE: str = ""         # data.pCode  (tashkilot kodi, 5 belgi)
    KATM_HEAD: str = ""         # data.pHead  (bosh tashkilot kodi, 3 belgi)
    KATM_TIMEOUT: int = 30
    # pCurrency — kredit summasi valyutasi. UZS uchun "860" (ISO 4217) yoki KATM ichki
    # spravochnik "017" bo'lishi mumkin — KATM bilan tasdiqlash kerak.
    KATM_CURRENCY: str = "860"

    # SsmartTV integration — super-admin provisions TV admin accounts via the
    # TV backend's internal endpoint (server-to-server, shared secret).
    TV_API_URL: str = "http://tv-api:8000"
    TV_INTERNAL_SECRET: str = ""
    TV_API_TIMEOUT: int = 15

    # SsmartPro integration — super-admin manages the pro.ssmart.uz home-page
    # ad carousel via the Pro backend's internal endpoint (server-to-server).
    PRO_API_URL: str = "http://master-api:8000"
    PRO_INTERNAL_SECRET: str = ""
    PRO_API_TIMEOUT: int = 15

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
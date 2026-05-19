from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    CORS_ORIGINS: str = "http://localhost:5173"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""  # startup'da getMe orqali avto-aniqlanadi
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
    # Atmos payment gateway (https://docs.atmos.uz)
    ATMOS_BASE_URL: str = "https://apigw.atmos.uz"
    ATMOS_CONSUMER_KEY: str = ""
    ATMOS_CONSUMER_SECRET: str = ""
    ATMOS_STORE_ID: str = ""
    ATMOS_TERMINAL_ID: str = ""
    ATMOS_CALLBACK_SECRET: str = ""  # HMAC-SHA256 kalit (X-SIGNATURE tekshiruvi)
    ATMOS_DEFAULT_LANG: str = "uz"
    # Paymo scoring API (karta bo'yicha 12 oylik tushum tarixi)
    PAYMO_BASE_URL: str = "https://api.paymo.uz"
    PAYMO_AUTH_TOKEN: str = ""  # statik Bearer token
    PAYMO_TIMEOUT: int = 20

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
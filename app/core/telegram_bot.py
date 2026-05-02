"""
Telegram Bot — OTP login uchun.

Asosiy ish jarayoni:
  1. Foydalanuvchi saytda "Telegram orqali" tugmasini bosadi
  2. Backend AuthSession yaratadi va `t.me/BOT?start=TOKEN` linkini qaytaradi
  3. Foydalanuvchi linkni ochib, "Start" bosadi - bot /start TOKEN qabul qiladi
  4. Bot foydalanuvchidan telefon raqamni yuborishni so'raydi (request_contact)
  5. Foydalanuvchi raqamni yuboradi - bot 6 xonali kod generatsiya qilib yuboradi
  6. Foydalanuvchi saytga qaytib, kodni kiritadi
  7. Backend kodni tekshiradi va JWT qaytaradi
"""
import asyncio
import json
import logging
from pathlib import Path

import httpx

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.services import auth_session_service

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"

logger = logging.getLogger("telegram_bot")

API_BASE = "https://api.telegram.org/bot{token}/{method}"
POLL_TIMEOUT = 25  # long-poll
HTTP_TIMEOUT = 30


class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self._offset = 0
        self._client: httpx.AsyncClient | None = None
        self._task: asyncio.Task | None = None
        self._running = False

    async def _api(self, method: str, **params) -> dict:
        url = API_BASE.format(token=self.token, method=method)
        assert self._client is not None
        resp = await self._client.post(url, json=params, timeout=HTTP_TIMEOUT + 5)
        data = resp.json()
        if not data.get("ok"):
            logger.warning("Telegram API xatosi (%s): %s", method, data.get("description"))
        return data

    async def send_message(self, chat_id: int, text: str, **extra) -> None:
        await self._api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", **extra)

    async def send_photo_file(self, chat_id: int, file_path: Path, caption: str | None = None) -> None:
        """Lokal faylni multipart bilan yuboramiz."""
        url = API_BASE.format(token=self.token, method="sendPhoto")
        assert self._client is not None
        with file_path.open("rb") as f:
            files = {"photo": (file_path.name, f.read())}
        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        resp = await self._client.post(url, data=data, files=files, timeout=HTTP_TIMEOUT + 10)
        result = resp.json()
        if not result.get("ok"):
            logger.warning("sendPhoto xatosi: %s", result.get("description"))

    async def send_media_group_files(
        self, chat_id: int, file_paths: list[Path], caption: str | None = None
    ) -> None:
        """2-10 ta rasmni bitta media-group sifatida yuboramiz. Caption faqat birinchi rasmga."""
        url = API_BASE.format(token=self.token, method="sendMediaGroup")
        assert self._client is not None
        media = []
        files = {}
        for i, fp in enumerate(file_paths[:10]):
            attach_name = f"photo{i}"
            item = {"type": "photo", "media": f"attach://{attach_name}"}
            if i == 0 and caption:
                item["caption"] = caption
                item["parse_mode"] = "HTML"
            media.append(item)
            with fp.open("rb") as f:
                files[attach_name] = (fp.name, f.read())
        data = {"chat_id": str(chat_id), "media": json.dumps(media)}
        resp = await self._client.post(url, data=data, files=files, timeout=HTTP_TIMEOUT + 15)
        result = resp.json()
        if not result.get("ok"):
            logger.warning("sendMediaGroup xatosi: %s", result.get("description"))

    async def request_phone(self, chat_id: int) -> None:
        keyboard = {
            "keyboard": [[{"text": "📱 Telefon raqamni yuborish", "request_contact": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }
        await self.send_message(
            chat_id,
            "👋 Salom! <b>Ssmart</b>'ga kirish uchun telefon raqamingizni yuboring.\n\n"
            "Pastdagi tugmani bosing.",
            reply_markup=json.dumps(keyboard),
        )

    async def remove_keyboard(self, chat_id: int, text: str) -> None:
        await self.send_message(chat_id, text, reply_markup=json.dumps({"remove_keyboard": True}))

    async def _handle_start(self, chat_id: int, payload: str) -> None:
        """`/start TOKEN` — sessiyani topib, telefon so'raymiz."""
        async with AsyncSessionLocal() as db:
            session = await auth_session_service.get_by_token(db, payload)
            if not session or not auth_session_service.is_valid(session):
                await self.send_message(
                    chat_id,
                    "❌ Login sessiyasi topilmadi yoki muddati tugagan. "
                    "Iltimos, saytdan qayta urinib ko'ring.",
                )
                return
        await self.request_phone(chat_id)

    async def _handle_contact(self, chat_id: int, sender: dict, contact: dict, last_token: str | None) -> None:
        phone = contact.get("phone_number", "")
        if not phone:
            await self.send_message(chat_id, "❌ Telefon raqam bo'sh.")
            return
        if not phone.startswith("+"):
            phone = "+" + phone

        # Eng so'nggi pending sessionni topamiz (oddiy holat: bitta ochiq sessiya)
        # Yaxshiroq variant: foydalanuvchi /start qilganda session.telegram_id ni saqlash kerak.
        # Hozircha — chat_id bo'yicha eng so'nggi sessiyani last_token bo'yicha topamiz.
        if not last_token:
            await self.send_message(
                chat_id,
                "❌ Avval saytdan login sessiyasini yarating.",
            )
            return

        async with AsyncSessionLocal() as db:
            session = await auth_session_service.get_by_token(db, last_token)
            if not session or not auth_session_service.is_valid(session):
                await self.send_message(chat_id, "❌ Sessiya topilmadi yoki muddati tugagan.")
                return
            full_name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or None
            await auth_session_service.attach_telegram_user(
                db,
                session,
                telegram_id=sender.get("id"),
                telegram_username=sender.get("username"),
                full_name=full_name,
                phone=phone,
            )
            code = session.code

        await self.remove_keyboard(
            chat_id,
            f"✅ Telefon qabul qilindi: <b>{phone}</b>\n\n"
            f"🔑 Sayt uchun kod:\n\n"
            f"<code>{code}</code>\n\n"
            f"Kodni saytdagi inputga kiriting. Kod 10 daqiqa amal qiladi.",
        )

    async def _process_update(self, update: dict, pending_tokens: dict) -> None:
        msg = update.get("message")
        if not msg:
            return
        chat_id = msg.get("chat", {}).get("id")
        sender = msg.get("from", {})
        if not chat_id:
            return

        text = msg.get("text", "")
        contact = msg.get("contact")

        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            payload = parts[1].strip() if len(parts) > 1 else ""
            if payload:
                pending_tokens[chat_id] = payload
                await self._handle_start(chat_id, payload)
            else:
                await self.send_message(
                    chat_id,
                    "Salom! Ssmart sayti orqali kirish uchun saytdagi 'Telegram orqali' tugmasini bosing.",
                )
            return

        if contact:
            last_token = pending_tokens.get(chat_id)
            await self._handle_contact(chat_id, sender, contact, last_token)
            return

    async def _poll_loop(self) -> None:
        pending_tokens: dict[int, str] = {}
        # Eski webhook'ni o'chiramiz (agar bo'lsa) - polling uchun zarur
        await self._api("deleteWebhook", drop_pending_updates=True)
        logger.info("Telegram bot polling boshlandi")

        while self._running:
            try:
                data = await self._api(
                    "getUpdates",
                    offset=self._offset,
                    timeout=POLL_TIMEOUT,
                    allowed_updates=["message"],
                )
                if not data.get("ok"):
                    await asyncio.sleep(3)
                    continue
                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    try:
                        await self._process_update(update, pending_tokens)
                    except Exception as e:
                        logger.exception("update qayta ishlashda xato: %s", e)
            except (httpx.HTTPError, asyncio.TimeoutError) as e:
                logger.warning("Polling xatosi: %s", e)
                await asyncio.sleep(3)
            except asyncio.CancelledError:
                break

    async def start(self) -> None:
        if self._running:
            return
        self._client = httpx.AsyncClient(timeout=HTTP_TIMEOUT + POLL_TIMEOUT + 5)
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
        self._client = None
        self._task = None


_bot: TelegramBot | None = None


async def start_bot() -> None:
    global _bot
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.info("TELEGRAM_BOT_TOKEN ko'rsatilmagan - bot ishga tushmadi")
        return
    _bot = TelegramBot(settings.TELEGRAM_BOT_TOKEN)
    await _bot.start()


async def stop_bot() -> None:
    if _bot:
        await _bot.stop()


async def notify_user(chat_id: int, text: str) -> bool:
    """Bot orqali foydalanuvchiga xabar yuboramiz (tashqi nuqta - order modulidan)."""
    if not _bot or not chat_id:
        return False
    try:
        await _bot.send_message(chat_id, text)
        return True
    except Exception as e:
        logger.warning("notify_user xatosi: %s", e)
        return False


def _resolve_local_image(image_url: str | None) -> Path | None:
    """`/uploads/file.jpg` -> mahalliy fayl yo'li. Tashqi URL bo'lsa None."""
    if not image_url:
        return None
    if image_url.startswith("/uploads/"):
        fname = image_url.split("/uploads/", 1)[1]
        path = UPLOAD_DIR / fname
        if path.exists() and path.is_file():
            return path
    return None


async def notify_user_with_photos(
    chat_id: int, image_urls: list[str], caption: str
) -> bool:
    """Foydalanuvchiga rasmlar bilan xabar yuboramiz.
    Rasmlar mahalliy `/uploads/` papkadan o'qiladi. Tashqi URL'lar tashlab yuboriladi.
    Agar rasm topilmasa, oddiy text xabar yuboriladi."""
    if not _bot or not chat_id:
        return False
    try:
        local_paths: list[Path] = []
        for url in image_urls:
            p = _resolve_local_image(url)
            if p:
                local_paths.append(p)

        if not local_paths:
            await _bot.send_message(chat_id, caption)
            return True

        # Telegram caption limiti — 1024 belgi (sendPhoto/sendMediaGroup uchun).
        # Uzunroq bo'lsa: avval rasmlar caption'siz, keyin alohida text.
        if len(caption) > 1000:
            if len(local_paths) == 1:
                await _bot.send_photo_file(chat_id, local_paths[0])
            else:
                await _bot.send_media_group_files(chat_id, local_paths)
            await _bot.send_message(chat_id, caption)
        else:
            if len(local_paths) == 1:
                await _bot.send_photo_file(chat_id, local_paths[0], caption)
            else:
                await _bot.send_media_group_files(chat_id, local_paths, caption)
        return True
    except Exception as e:
        logger.warning("notify_user_with_photos xatosi: %s", e)
        # Fallback — oddiy text
        try:
            await _bot.send_message(chat_id, caption)
        except Exception:
            pass
        return False


def get_bot_link(start_payload: str) -> str:
    username = settings.TELEGRAM_BOT_USERNAME
    if not username:
        return ""
    return f"https://t.me/{username}?start={start_payload}"

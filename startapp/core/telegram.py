import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)


class TelegramError(Exception):
    pass


def _call(method, payload):
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise TelegramError("Telegram bot token sozlanmagan.")
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        logger.error("Telegram %s request failed (%s).", method, type(exc).__name__)
        raise TelegramError("Telegram xizmatiga ulanib bo'lmadi.") from None
    if not isinstance(result, dict) or not result.get("ok"):
        logger.error("Telegram %s request was rejected.", method)
        raise TelegramError("Telegram xabarni qabul qilmadi.")
    return result.get("result")


def request_contact(chat_id):
    return _call("sendMessage", {
        "chat_id": chat_id,
        "text": "Hi!\n\nRentora'da ro'yxatdan o'tish uchun telefon raqamingizni yuboring.",
        "reply_markup": {
            "keyboard": [[{"text": "Telefon raqamni yuborish", "request_contact": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        },
    })


def send_message(chat_id, text):
    return _call("sendMessage", {"chat_id": chat_id, "text": text})

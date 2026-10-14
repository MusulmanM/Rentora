import json
import logging
import mimetypes
import uuid
from io import BytesIO
from urllib.parse import urljoin
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageOps


logger = logging.getLogger(__name__)

# Telegram rejects photos above 10 MB; larger files are sent as a text notice instead.
TELEGRAM_PHOTO_LIMIT = 10 * 1024 * 1024
TELEGRAM_PHOTO_SIZE = (1600, 1600)


class TelegramError(Exception):
    pass


def _send(method, request, timeout=20):
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            description = json.loads(exc.read().decode("utf-8")).get("description", "")
        except (ValueError, OSError, AttributeError):
            description = ""
        logger.error("Telegram %s request was rejected (HTTP %s): %s", method, exc.code, description)
        raise TelegramError("Telegram xabarni qabul qilmadi.") from None
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        logger.error("Telegram %s request failed (%s).", method, type(exc).__name__)
        raise TelegramError("Telegram xizmatiga ulanib bo'lmadi.") from None
    if not isinstance(result, dict) or not result.get("ok"):
        logger.error("Telegram %s request was rejected: %s", method, result.get("description", "") if isinstance(result, dict) else "")
        raise TelegramError("Telegram xabarni qabul qilmadi.")
    return result.get("result")


def _bot_url(method):
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise TelegramError("Telegram bot token sozlanmagan.")
    return f"https://api.telegram.org/bot{token}/{method}"


def _call(method, payload, timeout=20):
    request = Request(
        _bot_url(method),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _send(method, request, timeout)


def _call_multipart(method, fields, file_field, filename, content):
    """Upload a file to Telegram directly, so it never has to fetch our (possibly private) URL."""
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8") + content + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    request = Request(
        _bot_url(method),
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    return _send(method, request)


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


def handle_telegram_update(update):
    """Process one Telegram update (from the webhook or long polling): /start and contact sharing."""
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError

    from .forms import normalize_phone_number
    from .models import TelegramAccount

    message = update.get("message")
    if not isinstance(message, dict):
        return
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    telegram_user_id = sender.get("id")
    chat_id = chat.get("id")
    if not telegram_user_id or not chat_id or chat.get("type") != "private" or str(chat_id) != str(telegram_user_id):
        return

    contact = message.get("contact")
    if isinstance(contact, dict):
        if str(contact.get("user_id", "")) != str(telegram_user_id):
            return
        try:
            phone_number = normalize_phone_number(contact.get("phone_number", ""))
        except ValidationError:
            try:
                send_message(str(chat_id), "Faqat O'zbekiston telefon raqami bilan ro'yxatdan o'tish mumkin.")
            except TelegramError:
                logger.warning("Telegram could not send a contact validation message.")
            return
        try:
            telegram_username = str(sender.get("username", "")).strip().lstrip("@")[:64]
            account, _ = TelegramAccount.objects.get_or_create(
                phone_number=phone_number,
                defaults={
                    "telegram_user_id": str(telegram_user_id),
                    "chat_id": str(chat_id),
                    "telegram_username": telegram_username,
                },
            )
        except IntegrityError:
            account = TelegramAccount.objects.filter(phone_number=phone_number).first()
        if account and (
            account.telegram_user_id == str(telegram_user_id)
            and account.chat_id == str(chat_id)
        ):
            if telegram_username and account.telegram_username != telegram_username:
                account.telegram_username = telegram_username
                account.save(update_fields=["telegram_username"])
            response_text = "Telefon raqamingiz bog'landi. Endi Rentora saytida ro'yxatdan o'tishingiz mumkin."
        else:
            response_text = "Bu Telegram hisobi yoki telefon raqami boshqa akkauntga bog'langan."
        try:
            send_message(str(chat_id), response_text)
        except TelegramError:
            logger.warning("Telegram could not send the contact-link confirmation.")
        return

    if str(message.get("text", "")).split(maxsplit=1)[0:1] == ["/start"]:
        try:
            request_contact(str(chat_id))
        except TelegramError:
            logger.warning("Telegram could not send the contact request prompt.")


def _telegram_jpeg(field_file):
    """Re-encode an uploaded photo as a compact JPEG; Telegram rejects AVIF, huge or odd images."""
    try:
        with field_file.open("rb") as handle, Image.open(handle) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail(TELEGRAM_PHOTO_SIZE)
            buffer = BytesIO()
            image.save(buffer, "JPEG", quality=85, optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError):
        logger.warning("Listing photo %s could not be prepared for Telegram.", field_file.name)
        return None
    content = buffer.getvalue()
    return content if len(content) <= TELEGRAM_PHOTO_LIMIT else None


def _send_listing_photo(chat_id, listing, caption, site_url):
    """Send the listing's first photo. Returns False when there is no usable photo."""
    image = next(iter(listing.images.all()), None)
    if image is not None:
        content = _telegram_jpeg(image.image)
        if content is None:
            return False
        _call_multipart(
            "sendPhoto", {"chat_id": chat_id, "caption": caption}, "photo", "listing.jpg", content,
        )
        return True
    image_url = listing.legacy_image_url
    if image_url and site_url and image_url.startswith("/"):
        image_url = urljoin(f"{site_url}/", image_url.lstrip("/"))
    if image_url and image_url.startswith(("https://", "http://")):
        _call("sendPhoto", {"chat_id": chat_id, "photo": image_url, "caption": caption})
        return True
    return False


def send_booking_notice(chat_id, booking, event, audience, base_url=""):
    listing = booking.listing
    site_url = (getattr(settings, "PUBLIC_SITE_URL", "") or base_url).rstrip("/")
    listing_path = reverse("listing-detail", args=[listing.slug])
    listing_url = urljoin(f"{site_url}/", listing_path.lstrip("/")) if site_url else listing_path
    clicked_at = timezone.localtime(booking.requested_at).strftime("%d.%m.%Y %H:%M")
    customer = booking.user.get_full_name() or booking.user.get_username()
    common = (
        f"{listing.title}\n"
        f"Narxi: {listing.price_per_day:,.0f} so'm / kun\n"
        f"Muddati: {booking.days} kun ({booking.check_in:%d.%m.%Y} — {booking.check_out:%d.%m.%Y})\n"
        f"Jami: {booking.total_price:,.0f} so'm\n"
        f"To'lov: {booking.get_payment_method_display()}\n"
        f"Bron so'rovi: {clicked_at}\n"
        f"{listing_url}"
    )
    if audience == "provider":
        common = f"Mijoz: {customer}\n{common}"
    if event == "requested" and audience == "provider":
        text = f"Yangi bron so'rovi.\n\n{common}"
    elif event == "requested":
        text = f"Bron so'rovingiz ijaraga beruvchiga yuborildi.\n\n{common}"
    elif event == "rejected" and audience == "provider":
        text = f"Bron so'rovini rad etdingiz.\n\n{common}"
    elif event == "rejected":
        text = f"Ijaraga beruvchi bron so'rovingizni rad etdi.\n\n{common}"
    elif event == "cancelled":
        text = f"Bron bekor qilindi.\n\n{common}"
    elif event == "confirmed" and audience == "provider":
        text = f"Bronni tasdiqladingiz.\n\n{common}"
    elif event == "confirmed":
        text = f"Bron tasdiqlandi.\n\n{common}"
    elif audience == "provider":
        text = f"Mahsulot mijozga ijaraga topshirildi.\n\n{common}"
    else:
        text = f"Bugun mahsulotni olib ketishingiz mumkin.\n\n{common}"

    # A failed photo upload must never swallow the notice itself: fall back to plain text.
    try:
        if _send_listing_photo(chat_id, listing, text[:1024], site_url):
            return
    except TelegramError:
        logger.warning("Telegram photo notice failed for listing %s; sending text instead.", listing.pk)
    _call("sendMessage", {"chat_id": chat_id, "text": text})


def notify_booking_parties(booking_id, event, base_url=""):
    from .models import Booking, UserProfile

    booking = Booking.objects.select_related(
        "listing", "listing__owner", "user",
    ).prefetch_related("listing__images").filter(pk=booking_id).first()
    if booking is None:
        logger.error("Telegram booking notification skipped: booking %s not found.", booking_id)
        return

    recipients = [(booking.user_id, "customer")]
    if booking.listing.owner_id:
        recipients.append((booking.listing.owner_id, "provider"))
    profiles = UserProfile.objects.filter(user_id__in=[user_id for user_id, _ in recipients]).select_related("telegram_account")
    accounts = {profile.user_id: profile.telegram_account for profile in profiles}
    for user_id, audience in recipients:
        account = accounts.get(user_id)
        if account is None:
            logger.info("Telegram booking notification skipped: user %s has no linked Telegram.", user_id)
            continue
        try:
            send_booking_notice(account.chat_id, booking, event, audience, base_url)
        except TelegramError:
            logger.warning("Telegram booking notification failed for user %s.", user_id)

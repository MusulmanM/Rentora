import json
import logging
from urllib.parse import urljoin
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse
from django.utils import timezone


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


def send_booking_notice(chat_id, booking, event, audience, base_url=""):
    listing = booking.listing
    site_url = (getattr(settings, "PUBLIC_SITE_URL", "") or base_url).rstrip("/")
    listing_path = reverse("listing-detail", args=[listing.slug])
    listing_url = urljoin(f"{site_url}/", listing_path.lstrip("/")) if site_url else listing_path
    clicked_at = timezone.localtime(booking.requested_at).strftime("%d.%m.%Y %H:%M")
    common = (
        f"{listing.title}\n"
        f"Narxi: {listing.price_per_day:,.0f} so'm / kun\n"
        f"Muddati: {booking.days} kun ({booking.check_in:%d.%m.%Y} — {booking.check_out:%d.%m.%Y})\n"
        f"Jami: {booking.total_price:,.0f} so'm\n"
        f"Bron so'rovi: {clicked_at}\n"
        f"{listing_url}"
    )
    if event == "requested" and audience == "provider":
        text = f"Yangi bron so'rovi.\n\n{common}"
    elif event == "requested":
        text = f"Bron so'rovingiz ijaraga beruvchiga yuborildi.\n\n{common}"
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

    image_url = listing.primary_image_url
    if image_url and site_url and image_url.startswith("/"):
        image_url = urljoin(f"{site_url}/", image_url.lstrip("/"))
    if image_url and image_url.startswith(("https://", "http://")):
        _call("sendPhoto", {
            "chat_id": chat_id,
            "photo": image_url,
            "caption": text[:1024],
        })
    else:
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

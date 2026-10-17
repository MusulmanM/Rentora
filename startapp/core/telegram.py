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

from .bot_i18n import COMMANDS, LANGUAGE_BUTTONS, LANGUAGES, PAYMENT, PLAN, STATUS, label, localized_title, money, t


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


def _site():
    return (getattr(settings, "PUBLIC_SITE_URL", "") or "").rstrip("/")


def _keyboard(rows):
    return {"keyboard": [[{"text": text} for text in row] for row in rows], "resize_keyboard": True}


def _main_menu(language):
    return _keyboard([
        [t("menu_bookings", language), t("menu_site", language)],
        [t("menu_help", language), t("menu_language", language)],
    ])


def _language_menu():
    return _keyboard([[LANGUAGE_BUTTONS["uz"], LANGUAGE_BUTTONS["ru"], LANGUAGE_BUTTONS["en"]]])


def _reply(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if keyboard is not None:
        payload["reply_markup"] = keyboard
    try:
        _call("sendMessage", payload)
    except TelegramError:
        logger.warning("Telegram bot reply could not be sent.")


def request_contact(chat_id, language="uz"):
    return _call("sendMessage", {
        "chat_id": chat_id,
        "text": t("welcome_need_phone", language),
        "reply_markup": {
            "keyboard": [[{"text": t("share_phone", language), "request_contact": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        },
    })


def send_message(chat_id, text):
    return _call("sendMessage", {"chat_id": chat_id, "text": text})


def send_localized(chat_id, key, **values):
    """Send a bot text in the language this chat chose."""
    from .models import chat_language

    return send_message(chat_id, t(key, chat_language(chat_id), **values))


def set_bot_commands():
    """The "/" menu of the bot in every language (Telegram picks it by the user's app language)."""
    for language, commands in COMMANDS.items():
        payload = {"commands": [{"command": name, "description": text} for name, text in commands]}
        if language != "uz":
            payload["language_code"] = language
        _call("setMyCommands", payload)


def _menu_matches(text, key):
    return text in {t(key, language) for language in LANGUAGES}


def _bookings_text(chat_id, language):
    from .models import Booking, UserProfile

    profile = UserProfile.objects.filter(telegram_account__chat_id=str(chat_id)).select_related("user").first()
    if profile is None:
        return t("bookings_not_linked", language, site=_site())
    bookings = list(Booking.objects.filter(user=profile.user).select_related("listing").order_by("-created_at")[:5])
    if not bookings:
        return t("bookings_none", language)
    lines = [t("bookings_header", language), ""]
    for booking in bookings:
        lines.append(f"#{booking.pk} {localized_title(booking.listing, language)}")
        lines.append(
            f"{booking.check_in:%d.%m.%Y} — {booking.check_out:%d.%m.%Y} · {label(STATUS, booking.status, language)}"
        )
        lines.append(t("total", language, total=money(booking.total_price)))
        if booking.is_overdue:
            lines.append(t("event_overdue_customer", language, days=booking.late_days(),
                           rate=money(booking.daily_rate), debt=money(booking.current_debt())).split("\n")[0])
        lines.append("")
    lines.append(t("bookings_footer", language, site=_site()))
    return "\n".join(lines)


def handle_telegram_update(update):
    """One Telegram update (webhook or long polling): language, phone linking, menu and bookings."""
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError

    from .forms import normalize_phone_number
    from .models import TelegramAccount, TelegramChatLanguage, chat_language

    message = update.get("message")
    if not isinstance(message, dict):
        return
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    telegram_user_id = sender.get("id")
    chat_id = chat.get("id")
    if not telegram_user_id or not chat_id or chat.get("type") != "private" or str(chat_id) != str(telegram_user_id):
        return
    chat_id = str(chat_id)
    language = chat_language(chat_id)
    linked = TelegramAccount.objects.filter(chat_id=chat_id).exists()

    contact = message.get("contact")
    if isinstance(contact, dict):
        if str(contact.get("user_id", "")) != str(telegram_user_id):
            return
        try:
            phone_number = normalize_phone_number(contact.get("phone_number", ""))
        except ValidationError:
            _reply(chat_id, t("only_uz_phone", language))
            return
        try:
            telegram_username = str(sender.get("username", "")).strip().lstrip("@")[:64]
            account, _ = TelegramAccount.objects.get_or_create(
                phone_number=phone_number,
                defaults={
                    "telegram_user_id": str(telegram_user_id),
                    "chat_id": chat_id,
                    "telegram_username": telegram_username,
                },
            )
        except IntegrityError:
            account = TelegramAccount.objects.filter(phone_number=phone_number).first()
        if account and account.telegram_user_id == str(telegram_user_id) and account.chat_id == chat_id:
            if telegram_username and account.telegram_username != telegram_username:
                account.telegram_username = telegram_username
                account.save(update_fields=["telegram_username"])
            _reply(chat_id, t("phone_linked", language, site=_site()), _main_menu(language))
        else:
            _reply(chat_id, t("phone_taken", language))
        return

    text = str(message.get("text", "")).strip()
    command = text.split(maxsplit=1)[0].split("@")[0].lower() if text.startswith("/") else ""

    chosen = next((code for code, button in LANGUAGE_BUTTONS.items() if text == button), None)
    if chosen:
        TelegramChatLanguage.objects.update_or_create(chat_id=chat_id, defaults={"language": chosen})
        if linked:
            _reply(chat_id, t("language_set", chosen), _main_menu(chosen))
        else:
            _reply(chat_id, t("language_set", chosen))
            try:
                request_contact(chat_id, chosen)
            except TelegramError:
                logger.warning("Telegram could not send the contact request prompt.")
        return
    if command in ("/start", "/language") or _menu_matches(text, "menu_language"):
        _reply(chat_id, "\n".join(t("choose_language", code) for code in LANGUAGES), _language_menu())
        return
    if not linked:
        try:
            request_contact(chat_id, language)
        except TelegramError:
            logger.warning("Telegram could not send the contact request prompt.")
        return
    if command == "/bookings" or _menu_matches(text, "menu_bookings"):
        _reply(chat_id, _bookings_text(chat_id, language), _main_menu(language))
    elif command == "/help" or _menu_matches(text, "menu_help"):
        _reply(chat_id, t("help", language, site=_site()), _main_menu(language))
    elif _menu_matches(text, "menu_site"):
        _reply(chat_id, t("open_site", language, site=_site()), _main_menu(language))
    else:
        _reply(chat_id, t("unknown", language), _main_menu(language))


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
    from .models import chat_language

    language = chat_language(chat_id)
    listing = booking.listing
    site_url = (getattr(settings, "PUBLIC_SITE_URL", "") or base_url).rstrip("/")
    listing_path = reverse("listing-detail", args=[listing.slug])
    listing_url = urljoin(f"{site_url}/", listing_path.lstrip("/")) if site_url else listing_path
    clicked_at = timezone.localtime(booking.requested_at).strftime("%d.%m.%Y %H:%M")
    customer = booking.user.get_full_name() or booking.user.get_username()
    common = "\n".join([
        localized_title(listing, language),
        t("price", language, price=money(listing.price_per_day)),
        t("period", language, days=booking.days, start=f"{booking.check_in:%d.%m.%Y}", end=f"{booking.check_out:%d.%m.%Y}"),
        *([t("months_line", language, months=booking.months, price=money(listing.price_per_month or 0))] if booking.is_monthly else []),
        t("total", language, total=money(booking.total_price)),
        t("payment", language, method=label(PAYMENT, booking.payment_method, language)),
        *([t("plan_line", language, plan=label(PLAN, booking.payment_plan, language),
             count=booking.installments.count(), first=money(booking.installments.first().amount))]
          if booking.has_installments and booking.installments.exists() else []),
        t("requested_at", language, time=clicked_at),
        listing_url,
    ])
    if audience == "provider":
        common = f"{t('customer', language)}: {customer}\n{common}"
    side = "provider" if audience == "provider" else "customer"
    values = {
        "rate": money(booking.daily_rate), "days": booking.late_days(), "debt": money(booking.current_debt()),
    }
    if event in ("cancelled", "returned"):
        headline = t(f"event_{event}", language)
        if event == "returned" and booking.debt_amount:
            headline += "\n" + t("returned_debt", language, debt=money(booking.debt_amount), days=booking.overdue_days)
    elif event in ("requested", "rejected", "confirmed", "handed_over", "ending", "overdue"):
        headline = t(f"event_{event}_{side}", language, **values)
    else:
        headline = t(f"event_handed_over_{side}", language)
    text = f"{headline}\n\n{common}"

    # A failed photo upload must never swallow the notice itself: fall back to plain text.
    try:
        if _send_listing_photo(chat_id, listing, text[:1024], site_url):
            return
    except TelegramError:
        logger.warning("Telegram photo notice failed for listing %s; sending text instead.", listing.pk)
    _call("sendMessage", {"chat_id": chat_id, "text": text})


def _chat_of(user_id):
    from .models import UserProfile

    profile = UserProfile.objects.filter(user_id=user_id, telegram_account__isnull=False).select_related("telegram_account").first()
    return profile.telegram_account.chat_id if profile else None


def notify_installment(installment_id, event, base_url=""):
    """Instalment news for both sides: "paid", "due" (tomorrow / today) or "overdue"."""
    from .installments import paid_summary
    from .models import Installment, chat_language

    installment = Installment.objects.select_related("booking", "booking__listing", "booking__user").filter(pk=installment_id).first()
    if installment is None:
        return
    booking = installment.booking
    site = (getattr(settings, "PUBLIC_SITE_URL", "") or base_url).rstrip("/")
    summary = paid_summary(booking)
    customer = booking.user.get_full_name() or booking.user.get_username()
    late = max((timezone.localdate() - installment.due_date).days, 0)
    for user_id, side in ((booking.user_id, "customer"), (booking.listing.owner_id, "provider")):
        chat_id = _chat_of(user_id) if user_id else None
        if not chat_id:
            continue
        language = chat_language(chat_id)
        text = t(
            f"installment_{event}_{side}", language,
            number=installment.number, amount=money(installment.amount), date=f"{installment.due_date:%d.%m.%Y}",
            days=late, customer=customer, title=localized_title(booking.listing, language),
            left=money(summary["left_total"]), left_count=summary["count"] - summary["paid_count"],
            url=f"{site}{reverse('my-bookings')}",
        )
        try:
            _call("sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
        except TelegramError:
            logger.warning("Instalment notice %s could not reach user %s.", event, user_id)


def notify_installment_paid(installment_id, base_url=""):
    notify_installment(installment_id, "paid", base_url)


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

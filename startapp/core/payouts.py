"""Provider payouts and customer refunds for bookings paid online.

The customer pays Rentora's Click / Payme merchant. The money is *held* until the provider hands the
item over; then the provider's share (minus RENTORA_COMMISSION_PERCENT) becomes *ready* to be sent to
their card. A booking cancelled before the hand-over becomes a *refund* to the customer.

Sending money to a card needs a payout API from a licensed provider (not connected yet), so ready
payouts are sent by the head admin and marked "paid" in the admin. Click refunds use the Click
Merchant API (reversal) when CLICK_MERCHANT_USER_ID is set; otherwise the admin refunds by hand.
"""
import hashlib
import json
import logging
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Payout, PaymentTransaction, ProviderPaymentAccount

logger = logging.getLogger(__name__)

CLICK_API = "https://api.click.uz/v2/merchant"


def commission_percent():
    try:
        value = Decimal(str(getattr(settings, "RENTORA_COMMISSION_PERCENT", "5")))
    except InvalidOperation:
        value = Decimal("5")
    return min(max(value, Decimal("0")), Decimal("50"))


def split_amount(gross):
    """Rentora's commission and the provider's share, in whole so'm."""
    percent = commission_percent()
    commission = (gross * percent / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return percent, commission, gross - commission


def create_payout(booking, payment=None, amount=None, installment=None, status=None):
    """Called once an online payment went through: the whole rent, or one part of an instalment plan."""
    gross = booking.total_price if amount is None else amount
    percent, commission, net = split_amount(gross)
    account = ProviderPaymentAccount.objects.filter(user_id=booking.listing.owner_id).first()
    lookup = {"payment": payment} if payment is not None else {"booking": booking, "installment": installment}
    payout, _ = Payout.objects.get_or_create(**lookup, defaults={
        "booking": booking,
        "installment": installment,
        "provider_id": booking.listing.owner_id,
        "payment": payment,
        "gross_amount": gross,
        "commission_percent": percent,
        "commission_amount": commission,
        "net_amount": net,
        "card_last4": account.card_last4 if account else "",
        "status": status or Payout.Status.HELD,
        "ready_at": timezone.now() if status == Payout.Status.READY else None,
    })
    return payout


def release_payout(booking):
    """The item was handed over: every held share of this booking can now go to the provider's card."""
    released = []
    with transaction.atomic():
        for payout in Payout.objects.select_for_update().filter(booking=booking, status=Payout.Status.HELD):
            account = ProviderPaymentAccount.objects.filter(user_id=payout.provider_id).first()
            payout.status = Payout.Status.READY
            payout.ready_at = timezone.now()
            if account and account.card_last4:
                payout.card_last4 = account.card_last4
            payout.save(update_fields=["status", "ready_at", "card_last4"])
            released.append(payout)
    for payout in released:
        logger.info("Payout %s for booking %s is ready (%s so'm).", payout.pk, booking.pk, payout.net_amount)
    return released[0] if released else None


def refund_for_cancelled(booking):
    """Cancelled before the hand-over: give the customer back every part they paid online."""
    with transaction.atomic():
        payouts = list(Payout.objects.select_for_update().filter(booking=booking, status=Payout.Status.HELD))
        for payout in payouts:
            payout.status = Payout.Status.REFUND
            payout.save(update_fields=["status"])
    for payout in payouts:
        _try_click_reversal(payout)
    return payouts[0] if payouts else None


def pending_cards():
    """Payout cards the head admin still has to check."""
    return ProviderPaymentAccount.objects.filter(approved=False).exclude(card_last4="").select_related(
        "user", "user__host_profile",
    ).order_by("updated_at")


def _telegram_chat(user_id):
    from .models import UserProfile

    profile = UserProfile.objects.filter(user_id=user_id, telegram_account__isnull=False).select_related("telegram_account").first()
    return profile.telegram_account.chat_id if profile else None


def notify_card_review(account):
    """Tell every head admin with a linked Telegram that a card waits for approval."""
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    from .telegram import TelegramError, send_localized

    host = getattr(account.user, "host_profile", None)
    site = (getattr(settings, "PUBLIC_SITE_URL", "") or "").rstrip("/")
    sent = 0
    for admin_id in get_user_model().objects.filter(is_superuser=True, is_active=True).values_list("pk", flat=True):
        chat_id = _telegram_chat(admin_id)
        if not chat_id:
            continue
        try:
            send_localized(
                chat_id, "card_review_admin",
                provider=host.display_name if host else account.user.get_username(),
                brand=account.get_card_brand_display(), card=account.masked_card, holder=account.card_holder,
                url=site + reverse("helper-cards"),
            )
            sent += 1
        except TelegramError:
            logger.warning("Card review notice could not reach admin %s.", admin_id)
    return sent


def notify_card_result(account, approved):
    from .telegram import TelegramError, send_localized

    chat_id = _telegram_chat(account.user_id)
    if not chat_id:
        return
    try:
        send_localized(chat_id, "card_approved" if approved else "card_rejected", card=account.masked_card)
    except TelegramError:
        logger.warning("Card review result could not reach provider %s.", account.user_id)


def mark_payout_paid(payout, reference=""):
    if payout.status != Payout.Status.READY:
        return False
    payout.status = Payout.Status.PAID
    payout.reference = reference[:120]
    payout.completed_at = timezone.now()
    payout.save(update_fields=["status", "reference", "completed_at"])
    return True


def mark_refunded(payout, reference=""):
    if payout.status != Payout.Status.REFUND:
        return False
    payout.status = Payout.Status.REFUNDED
    payout.reference = reference[:120]
    payout.completed_at = timezone.now()
    payout.save(update_fields=["status", "reference", "completed_at"])
    return True


def _click_auth():
    timestamp = str(int(time.time()))
    digest = hashlib.sha1((timestamp + settings.CLICK_SECRET_KEY).encode("utf-8")).hexdigest()
    return f"{settings.CLICK_MERCHANT_USER_ID}:{digest}:{timestamp}"


def _try_click_reversal(payout):
    """Refund a Click payment through the Merchant API. Leaves the refund to the admin if it fails."""
    payment = payout.payment
    if not (
        payment and payment.provider == PaymentTransaction.Provider.CLICK and payment.state == 2
        and settings.CLICK_MERCHANT_USER_ID and settings.CLICK_SECRET_KEY and settings.CLICK_SERVICE_ID
    ):
        return False
    request = Request(
        f"{CLICK_API}/payment/reversal/{settings.CLICK_SERVICE_ID}/{payment.provider_transaction_id}",
        headers={"Accept": "application/json", "Content-Type": "application/json", "Auth": _click_auth()},
        method="DELETE",
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        logger.warning("Click reversal for payout %s failed: %s", payout.pk, type(exc).__name__)
        return False
    if result.get("error_code") != 0:
        logger.warning("Click refused reversal for payout %s: %s", payout.pk, result.get("error_note"))
        return False
    PaymentTransaction.objects.filter(pk=payment.pk).update(state=-2, cancelled_at=timezone.now())
    mark_refunded(payout, f"Click reversal {result.get('payment_id', '')}")
    logger.info("Click payment for payout %s was refunded automatically.", payout.pk)
    return True

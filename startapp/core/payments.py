"""Click and Payme payments into Rentora's single merchant account.

Click calls /payments/click/callback/ (SHOP API Prepare / Complete, MD5 signature) and Payme calls
/payments/payme/callback/ (Merchant API, Basic auth). A payment is for a BookingOrder (the whole rent,
or the first part of an instalment plan) or for a later Installment; both have a UUID reference that
is sent as the order id. Amounts always come from the database, never from the browser. The
provider's share is held (core.payouts) until the item is handed over, then paid to their card.
"""
import base64
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Booking, BookingOrder, Installment, PaymentTransaction, Payout, ProviderPaymentAccount, RentalListing
from .payouts import create_payout

logger = logging.getLogger(__name__)

ONLINE_METHODS = (Booking.PaymentMethod.CLICK, Booking.PaymentMethod.PAYME)


def click_enabled():
    return bool(settings.CLICK_SERVICE_ID and settings.CLICK_MERCHANT_ID and settings.CLICK_SECRET_KEY)


def payme_enabled():
    return bool(settings.PAYME_MERCHANT_ID and settings.PAYME_MERCHANT_KEY)


def provider_can_be_paid(listing):
    """Online payment needs somewhere to send the provider's share: an approved card."""
    if not listing.owner_id:
        return False
    account = ProviderPaymentAccount.objects.filter(user_id=listing.owner_id).first()
    return bool(account and account.can_receive_payouts)


def available_payment_methods(listing):
    """Cash always; Click / Payme when Rentora's merchant is set up and the provider has an approved card."""
    methods = [Booking.PaymentMethod.CASH]
    if provider_can_be_paid(listing):
        if click_enabled():
            methods.append(Booking.PaymentMethod.CLICK)
        if payme_enabled():
            methods.append(Booking.PaymentMethod.PAYME)
    return methods


def checkout_url(method, reference, amount, request):
    return_url = request.build_absolute_uri(reverse("my-bookings"))
    if method == Booking.PaymentMethod.CLICK:
        if not click_enabled():
            raise ValueError("Click orqali to'lov hozircha yoqilmagan.")
        query = urlencode({
            "service_id": settings.CLICK_SERVICE_ID,
            "merchant_id": settings.CLICK_MERCHANT_ID,
            "amount": f"{amount:.2f}",
            "transaction_param": reference,
            "return_url": return_url,
        })
        return f"{settings.CLICK_CHECKOUT_BASE_URL}?{query}"
    if method == Booking.PaymentMethod.PAYME:
        if not payme_enabled():
            raise ValueError("Payme orqali to'lov hozircha yoqilmagan.")
        checkout_data = f"m={settings.PAYME_MERCHANT_ID};ac.order_id={reference};a={_tiyin(amount)};c={return_url}"
        encoded = base64.b64encode(checkout_data.encode("utf-8")).decode("ascii")
        return f"{settings.PAYME_CHECKOUT_BASE_URL}/{encoded}"
    raise ValueError("Bu buyurtma uchun onlayn to'lov yo'q.")


def payment_url(order, request):
    return checkout_url(order.payment_method, order.reference, order.payable_amount, request)


def installment_payment_url(installment, request):
    return checkout_url(installment.booking.payment_method, installment.reference, installment.amount, request)


def _tiyin(amount):
    return int(amount * 100)


def _ms(moment):
    return int(moment.timestamp() * 1000) if moment else 0


class _Payable:
    """What a Click / Payme order id points to: a booking order or a later instalment."""

    def __init__(self, order=None, installment=None):
        self.order, self.installment = order, installment

    @property
    def amount(self):
        return self.order.payable_amount if self.order else self.installment.amount

    @property
    def is_paid(self):
        if self.order:
            return self.order.status == BookingOrder.Status.PAID
        return self.installment.status == Installment.Status.PAID

    @property
    def is_open(self):
        if self.order:
            return self.order.status == BookingOrder.Status.AWAITING_PAYMENT
        return (
            self.installment.status == Installment.Status.PENDING
            and self.installment.booking.status not in (Booking.Status.CANCELLED, Booking.Status.RETURNED)
        )

    @property
    def link(self):
        return {"booking_order": self.order} if self.order else {"installment": self.installment}

    def __str__(self):
        return f"order {self.order.pk}" if self.order else f"installment {self.installment.pk}"


def _find_payable(reference, method):
    try:
        reference = uuid.UUID(str(reference))
    except (ValueError, TypeError, AttributeError):
        return None
    order = BookingOrder.objects.select_for_update().filter(reference=reference, payment_method=method).first()
    if order:
        return _Payable(order=order)
    installment = Installment.objects.select_for_update().select_related("booking").filter(
        reference=reference, booking__payment_method=method,
    ).first()
    return _Payable(installment=installment) if installment else None


def _payment_reference(payment):
    return payment.booking_order.reference if payment.booking_order_id else payment.installment.reference


def _complete(payment):
    """The money arrived: create the booking (first payment) or mark the instalment paid."""
    if payment.booking_order_id:
        _create_booking_from_paid_order(payment.booking_order, payment)
    else:
        from .installments import mark_installment_paid
        mark_installment_paid(payment.installment, payment.provider, payment)


def _create_booking_from_paid_order(order, payment=None):
    from .installments import create_installments, mark_installment_paid

    with transaction.atomic():
        order = BookingOrder.objects.select_for_update().select_related("listing", "user").get(pk=order.pk)
        if order.status == BookingOrder.Status.PAID and order.booking_id:
            return order.booking
        if order.status != BookingOrder.Status.AWAITING_PAYMENT:
            raise ValueError("Order is not awaiting payment.")
        RentalListing.objects.select_for_update().get(pk=order.listing_id)

        order.status = BookingOrder.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at"])
        booking = Booking(
            user=order.user,
            listing=order.listing,
            check_in=order.check_in,
            check_out=order.check_out,
            guests=order.guests,
            payment_method=order.payment_method,
            rental_unit=order.rental_unit,
            months=order.months,
            payment_plan=order.payment_plan,
            total_price=order.total_price,
            status=Booking.Status.PENDING,
            requested_at=order.created_at,
        )
        booking.full_clean()
        booking.save()
        order.booking = booking
        order.save(update_fields=["booking"])
        if booking.has_installments:
            first = create_installments(booking)[0]
            mark_installment_paid(first, order.payment_method, payment)
        else:
            create_payout(booking, payment)
        from .telegram import notify_booking_parties
        transaction.on_commit(lambda: notify_booking_parties(booking.pk, "requested"))
        return booking


# --- Click (SHOP API: Prepare action=0, Complete action=1) ----------------------------------------

def _click_signature_is_valid(data, secret):
    required = ("click_trans_id", "service_id", "merchant_trans_id", "amount", "action", "sign_time", "sign_string")
    if not secret or any(data.get(field) in (None, "") for field in required):
        return False
    # Complete requests also sign merchant_prepare_id (Click SHOP API).
    prepare_id = data.get("merchant_prepare_id", "") if data.get("action") == "1" else ""
    signature = (
        f"{data['click_trans_id']}{data['service_id']}{secret}"
        f"{data['merchant_trans_id']}{prepare_id}{data['amount']}{data['action']}{data['sign_time']}"
    )
    expected = hashlib.md5(signature.encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected.lower(), str(data["sign_string"]).lower())


def _click_result(data, error, note, prepare_id=None):
    result = {
        "click_trans_id": data.get("click_trans_id", 0),
        "merchant_trans_id": data.get("merchant_trans_id", ""),
        "error": error,
        "error_note": note,
    }
    if prepare_id is not None:
        result["merchant_prepare_id"] = prepare_id
        if data.get("action") == "1":
            result["merchant_confirm_id"] = prepare_id
    return JsonResponse(result)


@csrf_exempt
@require_POST
def click_callback(request):
    data = request.POST
    if not click_enabled() or not _click_signature_is_valid(data, settings.CLICK_SECRET_KEY):
        logger.warning("Click callback with a bad signature.")
        return _click_result(data, -1, "SIGN CHECK FAILED")
    if str(data.get("service_id")) != str(settings.CLICK_SERVICE_ID):
        return _click_result(data, -1, "SERVICE ID MISMATCH")

    action = data.get("action")
    try:
        amount = Decimal(data["amount"])
    except InvalidOperation:
        return _click_result(data, -2, "Incorrect parameter amount")

    if action == "0":
        with transaction.atomic():
            payable = _find_payable(data["merchant_trans_id"], Booking.PaymentMethod.CLICK)
            if payable is None:
                return _click_result(data, -5, "Order not found")
            if payable.is_paid:
                return _click_result(data, -4, "Already paid")
            if not payable.is_open:
                return _click_result(data, -9, "Order cancelled")
            if amount != payable.amount:
                return _click_result(data, -2, "Incorrect parameter amount")
            other_payments = PaymentTransaction.objects.filter(
                provider=PaymentTransaction.Provider.CLICK, **payable.link,
            ).exclude(provider_transaction_id=data["click_trans_id"])
            if other_payments.filter(state__in=[1, 2]).exists():
                return _click_result(data, -4, "A payment is already in progress or completed")
            payment, created = PaymentTransaction.objects.get_or_create(
                provider=PaymentTransaction.Provider.CLICK,
                provider_transaction_id=data["click_trans_id"],
                defaults={**payable.link, "amount": amount, "state": 1},
            )
            if not created and (_payment_reference(payment) != _payment_reference_of(payable) or payment.amount != amount):
                return _click_result(data, -8, "Transaction mismatch")
            logger.info("Click prepare: %s.", payable)
            return _click_result(data, 0, "Success", payment.pk)

    if action == "1":
        with transaction.atomic():
            payment = PaymentTransaction.objects.select_for_update().filter(
                provider=PaymentTransaction.Provider.CLICK,
                provider_transaction_id=data["click_trans_id"],
            ).select_related("booking_order", "installment").first()
            if payment is None or str(data.get("merchant_prepare_id", "")) != str(payment.pk):
                return _click_result(data, -6, "Transaction does not exist")
            if str(data.get("merchant_trans_id", "")) != str(_payment_reference(payment)):
                return _click_result(data, -8, "Order reference mismatch")
            if payment.state == 2:
                return _click_result(data, -4, "Already paid", payment.pk)
            if payment.state < 0:
                return _click_result(data, -9, "Transaction cancelled", payment.pk)
            if payment.amount != amount:
                return _click_result(data, -2, "Incorrect parameter amount", payment.pk)
            try:
                click_error = int(data.get("error", "0"))
            except ValueError:
                return _click_result(data, -8, "Error in request from click", payment.pk)
            if click_error < 0:
                # Click could not take the money (e.g. not enough funds): cancel our side too.
                payment.state = -1
                payment.cancelled_at = timezone.now()
                payment.save(update_fields=["state", "cancelled_at"])
                return _click_result(data, -9, "Transaction cancelled", payment.pk)
            try:
                _complete(payment)
            except (ValueError, ValidationError):
                return _click_result(data, -7, "Failed to update order", payment.pk)
            payment.state = 2
            payment.performed_at = timezone.now()
            payment.save(update_fields=["state", "performed_at"])
            logger.info("Click complete: payment %s.", payment.pk)
            return _click_result(data, 0, "Success", payment.pk)

    return _click_result(data, -3, "Action not found")


def _payment_reference_of(payable):
    return payable.order.reference if payable.order else payable.installment.reference


# --- Payme (Merchant API, JSON-RPC) ----------------------------------------------------------------

def _payme_error(request_id, code, message, data=None):
    error = {"code": code, "message": {"uz": message, "ru": message, "en": message}}
    if data is not None:
        error["data"] = data
    return JsonResponse({"jsonrpc": "2.0", "id": request_id, "error": error})


def _payme_result(request_id, result):
    return JsonResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _payme_authorized(request):
    key = settings.PAYME_MERCHANT_KEY
    if not key:
        return False
    expected = "Basic " + base64.b64encode(f"Paycom:{key}".encode("utf-8")).decode("ascii")
    return hmac.compare_digest(request.headers.get("Authorization", ""), expected)


def _payme_timed_out(payment):
    limit = timedelta(milliseconds=settings.PAYME_TRANSACTION_TIMEOUT_MS)
    return payment.state == 1 and timezone.now() - payment.created_at > limit


def _payme_cancel_timed_out(payment):
    payment.state = -1
    payment.cancel_reason = 4  # Payme reason 4: transaction cancelled by timeout
    payment.cancelled_at = timezone.now()
    payment.save(update_fields=["state", "cancel_reason", "cancelled_at"])


def _payme_transaction_info(payment):
    return {
        "create_time": _ms(payment.created_at),
        "perform_time": _ms(payment.performed_at),
        "cancel_time": _ms(payment.cancelled_at),
        "transaction": str(payment.pk),
        "state": payment.state,
        "reason": payment.cancel_reason,
    }


def _payme_cancel_performed(payment):
    """Payme refunded a performed payment. Returns False when the service was already provided."""
    payouts = Payout.objects.filter(payment=payment)
    if payouts.filter(status__in=[Payout.Status.READY, Payout.Status.PAID]).exists():
        return False
    if payment.booking_order_id:
        order = payment.booking_order
        booking = order.booking
        if booking and booking.status in (Booking.Status.HANDED_OVER, Booking.Status.RETURNED):
            return False
        order.status = BookingOrder.Status.CANCELLED
        order.save(update_fields=["status"])
        if booking:
            booking.status = Booking.Status.CANCELLED
            booking.save(update_fields=["status", "updated_at"])
            Payout.objects.filter(booking=booking, status__in=[Payout.Status.HELD, Payout.Status.REFUND]).update(
                status=Payout.Status.REFUNDED, completed_at=timezone.now(), reference="Payme CancelTransaction",
            )
    else:
        installment = payment.installment
        Installment.objects.filter(pk=installment.pk).update(status=Installment.Status.PENDING, paid_at=None, method="")
        payouts.filter(status__in=[Payout.Status.HELD, Payout.Status.REFUND]).update(
            status=Payout.Status.REFUNDED, completed_at=timezone.now(), reference="Payme CancelTransaction",
        )
    return True


@csrf_exempt
@require_POST
def payme_callback(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _payme_error(None, -32700, "Parse error")
    if not isinstance(payload, dict):
        return _payme_error(None, -32600, "Invalid request")
    request_id = payload.get("id")
    if not _payme_authorized(request):
        return _payme_error(request_id, -32504, "Unauthorized")

    method = payload.get("method")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        return _payme_error(request_id, -32602, "Invalid params")
    payments = PaymentTransaction.objects.filter(provider=PaymentTransaction.Provider.PAYME)

    if method in ("CheckPerformTransaction", "CreateTransaction"):
        with transaction.atomic():
            payme_id = str(params.get("id") or "")
            if method == "CreateTransaction":
                if not payme_id:
                    return _payme_error(request_id, -31008, "Transaction id is required")
                existing = payments.select_for_update().filter(provider_transaction_id=payme_id).first()
                if existing:
                    if existing.state != 1:
                        return _payme_error(request_id, -31008, "Transaction cannot be performed")
                    if _payme_timed_out(existing):
                        _payme_cancel_timed_out(existing)
                        return _payme_error(request_id, -31008, "Transaction timed out")
                    return _payme_result(request_id, {
                        "create_time": _ms(existing.created_at), "transaction": str(existing.pk), "state": 1,
                    })
            account_params = params.get("account") if isinstance(params.get("account"), dict) else {}
            payable = _find_payable(account_params.get("order_id"), Booking.PaymentMethod.PAYME)
            if payable is None:
                return _payme_error(request_id, -31050, "Order not found", "order_id")
            if not payable.is_open:
                return _payme_error(request_id, -31051, "Order is not awaiting payment", "order_id")
            if params.get("amount") != _tiyin(payable.amount):
                return _payme_error(request_id, -31001, "Incorrect amount")
            if method == "CheckPerformTransaction":
                return _payme_result(request_id, {"allow": True})
            waiting = payments.select_for_update().filter(state=1, **payable.link).first()
            if waiting and _payme_timed_out(waiting):
                _payme_cancel_timed_out(waiting)
                waiting = None
            if waiting:
                return _payme_error(request_id, -31052, "Another payment for this order is in progress", "order_id")
            if PaymentTransaction.objects.filter(provider_transaction_id=payme_id).exists():
                return _payme_error(request_id, -31008, "Transaction mismatch")
            payment = PaymentTransaction.objects.create(
                provider=PaymentTransaction.Provider.PAYME, provider_transaction_id=payme_id,
                amount=payable.amount, state=1, **payable.link,
            )
            logger.info("Payme create: %s.", payable)
            return _payme_result(request_id, {
                "create_time": _ms(payment.created_at), "transaction": str(payment.pk), "state": 1,
            })

    if method in ("PerformTransaction", "CancelTransaction", "CheckTransaction"):
        with transaction.atomic():
            payment = payments.select_for_update().filter(
                provider_transaction_id=str(params.get("id") or ""),
            ).select_related("booking_order", "booking_order__booking", "installment").first()
            if payment is None:
                return _payme_error(request_id, -31003, "Transaction not found")

            if method == "CheckTransaction":
                return _payme_result(request_id, _payme_transaction_info(payment))

            if method == "PerformTransaction":
                if payment.state == 2:
                    return _payme_result(request_id, {
                        "transaction": str(payment.pk), "perform_time": _ms(payment.performed_at), "state": 2,
                    })
                if payment.state != 1:
                    return _payme_error(request_id, -31008, "Transaction cannot be performed")
                if _payme_timed_out(payment):
                    _payme_cancel_timed_out(payment)
                    return _payme_error(request_id, -31008, "Transaction timed out")
                try:
                    _complete(payment)
                except (ValueError, ValidationError):
                    return _payme_error(request_id, -31008, "Booking cannot be confirmed")
                payment.state = 2
                payment.performed_at = timezone.now()
                payment.save(update_fields=["state", "performed_at"])
                logger.info("Payme perform: payment %s.", payment.pk)
                return _payme_result(request_id, {
                    "transaction": str(payment.pk), "perform_time": _ms(payment.performed_at), "state": 2,
                })

            # CancelTransaction
            if payment.state in (1, 2):
                was_performed = payment.state == 2
                if was_performed and not _payme_cancel_performed(payment):
                    return _payme_error(request_id, -31007, "The service was already provided")
                payment.state = -2 if was_performed else -1
                payment.cancel_reason = params.get("reason") if isinstance(params.get("reason"), int) else None
                payment.cancelled_at = timezone.now()
                payment.save(update_fields=["state", "cancel_reason", "cancelled_at"])
                logger.info("Payme cancel: payment %s, state %s.", payment.pk, payment.state)
            return _payme_result(request_id, {
                "transaction": str(payment.pk), "cancel_time": _ms(payment.cancelled_at), "state": payment.state,
            })

    if method == "GetStatement":
        start, end = params.get("from"), params.get("to")
        if not isinstance(start, int) or not isinstance(end, int) or start > end:
            return _payme_error(request_id, -32602, "Invalid params")
        statement = payments.filter(
            created_at__gte=datetime.fromtimestamp(start / 1000, tz=dt_timezone.utc),
            created_at__lte=datetime.fromtimestamp(end / 1000, tz=dt_timezone.utc),
        ).select_related("booking_order", "installment").order_by("created_at")
        return _payme_result(request_id, {"transactions": [
            {
                "id": payment.provider_transaction_id,
                "time": _ms(payment.created_at),
                "amount": _tiyin(payment.amount),
                "account": {"order_id": str(_payment_reference(payment))},
                **_payme_transaction_info(payment),
            }
            for payment in statement
        ]})

    return _payme_error(request_id, -32601, "Method not found")

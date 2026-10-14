import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone as dt_timezone
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

from .models import Booking, BookingOrder, PaymentTransaction, RentalListing


def payment_url(order, request):
    amount_tiyin = int(order.total_price * 100)
    if order.payment_method in (Booking.PaymentMethod.CARD, Booking.PaymentMethod.CLICK):
        service_id = getattr(settings, "CLICK_SERVICE_ID", "")
        merchant_id = getattr(settings, "CLICK_MERCHANT_ID", "")
        if not service_id or not merchant_id or not getattr(settings, "CLICK_SECRET_KEY", ""):
            raise ValueError("Click to'lovini yoqish uchun CLICK_SERVICE_ID, CLICK_MERCHANT_ID va CLICK_SECRET_KEY sozlang.")
        query = urlencode({
            "service_id": service_id,
            "merchant_id": merchant_id,
            "amount": order.total_price,
            "transaction_param": order.reference,
            "return_url": request.build_absolute_uri(reverse("my-bookings")),
        })
        return f"{settings.CLICK_CHECKOUT_BASE_URL}?{query}"

    merchant_id = getattr(settings, "PAYME_MERCHANT_ID", "")
    if not merchant_id or not getattr(settings, "PAYME_MERCHANT_KEY", ""):
        raise ValueError("Payme to'lovini yoqish uchun PAYME_MERCHANT_ID va PAYME_MERCHANT_KEY sozlang.")
    checkout_data = (
        f"m={merchant_id};ac.order_id={order.reference};a={amount_tiyin};"
        f"c={request.build_absolute_uri(reverse('my-bookings'))}"
    )
    encoded = base64.b64encode(checkout_data.encode("utf-8")).decode("ascii")
    return f"{settings.PAYME_CHECKOUT_BASE_URL}/{encoded}"


def _create_booking_from_paid_order(order):
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
            total_price=order.total_price,
            status=Booking.Status.PENDING,
            requested_at=order.created_at,
        )
        booking.full_clean()
        booking.save()
        order.booking = booking
        order.save(update_fields=["booking"])
        from .telegram import notify_booking_parties
        transaction.on_commit(lambda: notify_booking_parties(booking.pk, "requested"))
        return booking


def _click_signature_is_valid(data):
    required = ("click_trans_id", "service_id", "merchant_trans_id", "amount", "action", "sign_time", "sign_string")
    if any(data.get(field) in (None, "") for field in required):
        return False
    secret = getattr(settings, "CLICK_SECRET_KEY", "")
    if not secret or not getattr(settings, "CLICK_SERVICE_ID", ""):
        return False
    signature = (
        f"{data['click_trans_id']}{data['service_id']}{secret}"
        f"{data['merchant_trans_id']}{data['amount']}{data['action']}{data['sign_time']}"
    )
    expected = hashlib.md5(signature.encode()).hexdigest()
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
    return JsonResponse(result)


@csrf_exempt
@require_POST
def click_callback(request):
    data = request.POST
    if not _click_signature_is_valid(data):
        return _click_result(data, -1, "SIGN CHECK FAILED")
    if str(data.get("service_id")) != str(getattr(settings, "CLICK_SERVICE_ID", "")):
        return _click_result(data, -1, "SERVICE ID MISMATCH")

    action = data.get("action")
    try:
        amount = Decimal(data["amount"])
    except InvalidOperation:
        return _click_result(data, -2, "Incorrect amount")

    if action == "0":
        with transaction.atomic():
            try:
                order = BookingOrder.objects.select_for_update().get(
                    reference=data["merchant_trans_id"],
                    status=BookingOrder.Status.AWAITING_PAYMENT,
                    payment_method__in=[Booking.PaymentMethod.CARD, Booking.PaymentMethod.CLICK],
                )
            except (BookingOrder.DoesNotExist, ValueError, ValidationError):
                return _click_result(data, -5, "Order not found")
            if amount != order.total_price:
                return _click_result(data, -2, "Incorrect amount")
            other_payments = PaymentTransaction.objects.filter(
                booking_order=order,
                provider=PaymentTransaction.Provider.CLICK,
            ).exclude(provider_transaction_id=data["click_trans_id"])
            if other_payments.filter(state__in=[1, 2]).exists():
                return _click_result(data, -4, "A payment is already in progress or completed")
            payment, created = PaymentTransaction.objects.get_or_create(
                provider=PaymentTransaction.Provider.CLICK,
                provider_transaction_id=data["click_trans_id"],
                defaults={"booking_order": order, "amount": amount, "state": 1},
            )
            if not created and (payment.booking_order_id != order.pk or payment.amount != amount):
                return _click_result(data, -1, "Transaction mismatch")
            return _click_result(data, 0, "Success", payment.pk)

    if action == "1":
        with transaction.atomic():
            payment = PaymentTransaction.objects.select_for_update().filter(
                provider=PaymentTransaction.Provider.CLICK,
                provider_transaction_id=data["click_trans_id"],
            ).select_related("booking_order").first()
            if payment is None:
                return _click_result(data, -6, "Transaction not found")
            if str(data.get("merchant_prepare_id", "")) != str(payment.pk):
                return _click_result(data, -6, "Prepare transaction not found")
            if str(data.get("merchant_trans_id", "")) != str(payment.booking_order.reference):
                return _click_result(data, -1, "Order reference mismatch")
            if payment.state == 2:
                return _click_result(data, 0, "Already paid", payment.pk)
            if payment.state != 1 or payment.amount != amount:
                return _click_result(data, -2, "Transaction amount or state mismatch", payment.pk)
            try:
                payment_error = int(data.get("error", "0"))
            except ValueError:
                return _click_result(data, -8, "Invalid payment result", payment.pk)
            if payment_error != 0:
                payment.state = -1
                payment.cancelled_at = timezone.now()
                payment.save(update_fields=["state", "cancelled_at"])
                return _click_result(data, 0, "Payment cancelled", payment.pk)
            try:
                _create_booking_from_paid_order(payment.booking_order)
            except (ValueError, ValidationError):
                return _click_result(data, -7, "Could not finalize the booking", payment.pk)
            payment.state = 2
            payment.performed_at = timezone.now()
            payment.save(update_fields=["state", "performed_at"])
            return _click_result(data, 0, "Success", payment.pk)

    return _click_result(data, -3, "Action not found")


def _payme_error(request_id, code, message, data=None):
    error = {"code": code, "message": {"uz": message, "ru": message, "en": message}}
    if data is not None:
        error["data"] = data
    return JsonResponse({"jsonrpc": "2.0", "id": request_id, "error": error})


def _payme_result(request_id, result):
    return JsonResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _payme_authorized(request):
    expected = getattr(settings, "PAYME_MERCHANT_AUTHORIZATION", "")
    actual = request.headers.get("Authorization", "")
    return bool(expected) and hmac.compare_digest(actual, expected)


def _payme_order(params):
    account = params.get("account") or {}
    try:
        return BookingOrder.objects.select_for_update().get(
            reference=account.get("order_id"),
            status=BookingOrder.Status.AWAITING_PAYMENT,
            payment_method=Booking.PaymentMethod.PAYME,
        )
    except (BookingOrder.DoesNotExist, ValueError, ValidationError):
        return None


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
    if method == "CreateTransaction":
        if not params.get("id"):
            return _payme_error(request_id, -31008, "Transaction id is required")
        existing = PaymentTransaction.objects.filter(
            provider=PaymentTransaction.Provider.PAYME,
            provider_transaction_id=str(params.get("id", "")),
        ).select_related("booking_order").first()
        if existing:
            if existing.amount * 100 != params.get("amount"):
                return _payme_error(request_id, -31001, "Incorrect amount")
            return _payme_result(request_id, {
                "create_time": int(existing.created_at.timestamp() * 1000),
                "transaction": str(existing.pk),
                "state": existing.state,
            })

    if method in ("CheckPerformTransaction", "CreateTransaction"):
        with transaction.atomic():
            order = _payme_order(params)
            if order is None:
                return _payme_error(request_id, -31050, "Order not found", "order_id")
            expected_amount = int(order.total_price * 100)
            if params.get("amount") != expected_amount:
                return _payme_error(request_id, -31001, "Incorrect amount")
            if method == "CheckPerformTransaction":
                return _payme_result(request_id, {"allow": True})
            payme_id = str(params.get("id", ""))
            if PaymentTransaction.objects.filter(
                booking_order=order,
                provider=PaymentTransaction.Provider.PAYME,
                state=1,
            ).exists():
                return _payme_error(request_id, -31008, "Another payment is in progress")
            payment, created = PaymentTransaction.objects.get_or_create(
                provider=PaymentTransaction.Provider.PAYME,
                provider_transaction_id=payme_id,
                defaults={
                    "booking_order": order,
                    "amount": order.total_price,
                    "state": 1,
                },
            )
            if not created and (payment.booking_order_id != order.pk or payment.amount != order.total_price):
                return _payme_error(request_id, -31008, "Transaction mismatch")
            create_time = int(payment.created_at.timestamp() * 1000)
            return _payme_result(request_id, {
                "create_time": create_time,
                "transaction": str(payment.pk),
                "state": payment.state,
            })

    payme_id = str(params.get("id", ""))
    with transaction.atomic():
        payment = PaymentTransaction.objects.select_for_update().filter(
            provider=PaymentTransaction.Provider.PAYME,
            provider_transaction_id=payme_id,
        ).select_related("booking_order").first()
        if method == "PerformTransaction":
            if payment is None:
                return _payme_error(request_id, -31003, "Transaction not found")
            if payment.state == 2:
                return _payme_result(request_id, {
                    "transaction": str(payment.pk),
                    "perform_time": int(payment.performed_at.timestamp() * 1000),
                    "state": 2,
                })
            if payment.state != 1:
                return _payme_error(request_id, -31008, "Transaction cannot be performed")
            try:
                _create_booking_from_paid_order(payment.booking_order)
            except (ValueError, ValidationError):
                return _payme_error(request_id, -31008, "Booking cannot be confirmed")
            payment.state = 2
            payment.performed_at = timezone.now()
            payment.save(update_fields=["state", "performed_at"])
            return _payme_result(request_id, {
                "transaction": str(payment.pk),
                "perform_time": int(payment.performed_at.timestamp() * 1000),
                "state": 2,
            })

        if method == "CancelTransaction":
            if payment is None:
                return _payme_error(request_id, -31003, "Transaction not found")
            if payment.state in (-1, -2):
                cancelled_at = payment.cancelled_at or timezone.now()
            else:
                payment.state = -2 if payment.state == 2 else -1
                payment.cancelled_at = timezone.now()
                payment.save(update_fields=["state", "cancelled_at"])
                cancelled_at = payment.cancelled_at
                if payment.state == -2 and payment.booking_order.booking_id:
                    booking = payment.booking_order.booking
                    booking.status = Booking.Status.CANCELLED
                    booking.save(update_fields=["status", "updated_at"])
                    payment.booking_order.status = BookingOrder.Status.CANCELLED
                    payment.booking_order.save(update_fields=["status"])
            return _payme_result(request_id, {
                "transaction": str(payment.pk),
                "cancel_time": int(cancelled_at.timestamp() * 1000),
                "state": payment.state,
            })

        if method == "CheckTransaction":
            if payment is None:
                return _payme_error(request_id, -31003, "Transaction not found")
            return _payme_result(request_id, {
                "create_time": int(payment.created_at.timestamp() * 1000),
                "perform_time": int(payment.performed_at.timestamp() * 1000) if payment.performed_at else 0,
                "cancel_time": int(payment.cancelled_at.timestamp() * 1000) if payment.cancelled_at else 0,
                "transaction": str(payment.pk),
                "state": payment.state,
                "reason": None,
            })

        if method == "GetStatement":
            start = params.get("from")
            end = params.get("to")
            payments = PaymentTransaction.objects.filter(
                provider=PaymentTransaction.Provider.PAYME,
                created_at__gte=datetime.fromtimestamp(start / 1000, tz=dt_timezone.utc),
                created_at__lte=datetime.fromtimestamp(end / 1000, tz=dt_timezone.utc),
            ).order_by("created_at")
            return _payme_result(request_id, {"transactions": [
                {
                    "id": payment.provider_transaction_id,
                    "time": int(payment.created_at.timestamp() * 1000),
                    "amount": int(payment.amount * 100),
                    "account": {"order_id": str(payment.booking_order.reference)},
                    "create_time": int(payment.created_at.timestamp() * 1000),
                    "perform_time": int(payment.performed_at.timestamp() * 1000) if payment.performed_at else 0,
                    "cancel_time": int(payment.cancelled_at.timestamp() * 1000) if payment.cancelled_at else 0,
                    "transaction": str(payment.pk),
                    "state": payment.state,
                    "reason": None,
                }
                for payment in payments
            ]})

    return _payme_error(request_id, -32601, "Method not found")

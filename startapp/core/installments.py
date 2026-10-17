"""Monthly rentals and instalment plans.

A home can be rented by the month at the provider's monthly price. The rent is paid in full, every
month, or every 15 days; each part is an Installment with its own due date. Cash parts are marked as
received by the provider; online parts are paid with Click / Payme (Installment.reference is the
order id), and each online part becomes its own provider payout.
"""
import math
from calendar import monthrange
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import transaction
from django.utils import timezone

MAX_MONTHS = 12
BIWEEKLY_DAYS = 15


def add_months(day, months):
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return day.replace(year=year, month=month, day=min(day.day, monthrange(year, month)[1]))


def rental_total(listing, check_in, check_out, rental_unit="day", months=None):
    from .models import Booking

    if rental_unit == Booking.RentalUnit.MONTH and months and listing.price_per_month:
        return listing.price_per_month * months
    return listing.price_per_day * max((check_out - check_in).days, 0)


def allowed_plans(rental_unit, months):
    """Instalments only for monthly rentals: every month needs 2+ months, every 15 days any length."""
    from .models import Booking

    plans = [Booking.PaymentPlan.FULL]
    if rental_unit == Booking.RentalUnit.MONTH and months:
        if months >= 2:
            plans.append(Booking.PaymentPlan.MONTHLY)
        plans.append(Booking.PaymentPlan.BIWEEKLY)
    return plans


def schedule(total, check_in, check_out, plan, months=None):
    """[(due_date, amount), ...] in whole so'm; the last part takes the rounding remainder."""
    from .models import Booking

    total = Decimal(total)
    if plan == Booking.PaymentPlan.MONTHLY and months and months >= 2:
        dates = [add_months(check_in, k) for k in range(months)]
    elif plan == Booking.PaymentPlan.BIWEEKLY:
        parts = max(1, math.ceil((check_out - check_in).days / BIWEEKLY_DAYS))
        dates = [check_in + timedelta(days=BIWEEKLY_DAYS * k) for k in range(parts)]
    else:
        return [(check_in, total)]
    base = (total / len(dates)).quantize(Decimal("1"), rounding=ROUND_DOWN)
    amounts = [base] * (len(dates) - 1) + [total - base * (len(dates) - 1)]
    return list(zip(dates, amounts))


def create_installments(booking):
    """The payment schedule of a booking with an instalment plan (idempotent)."""
    from .models import Installment

    if not booking.has_installments or booking.installments.exists():
        return list(booking.installments.all())
    parts = schedule(booking.total_price, booking.check_in, booking.check_out, booking.payment_plan, booking.months)
    return Installment.objects.bulk_create([
        Installment(booking=booking, number=number, due_date=due, amount=amount)
        for number, (due, amount) in enumerate(parts, start=1)
    ])


def mark_installment_paid(installment, method, payment=None):
    """Record a paid part. Online parts become a provider payout (ready at once after the hand-over)."""
    from .models import Booking, Installment, Payout
    from .payouts import create_payout

    with transaction.atomic():
        installment = Installment.objects.select_for_update().select_related("booking", "booking__listing").get(pk=installment.pk)
        if installment.status == Installment.Status.PAID:
            return installment
        installment.status = Installment.Status.PAID
        installment.method = method
        installment.paid_at = timezone.now()
        installment.save(update_fields=["status", "method", "paid_at"])
        if payment is not None:
            from .telegram import notify_installment_paid

            transaction.on_commit(lambda: notify_installment_paid(installment.pk))
            booking = installment.booking
            delivered = booking.status in (Booking.Status.HANDED_OVER, Booking.Status.RETURNED)
            create_payout(
                booking, payment, amount=installment.amount, installment=installment,
                status=Payout.Status.READY if delivered else Payout.Status.HELD,
            )
    return installment


def next_unpaid(booking):
    return booking.installments.filter(status="pending").order_by("number").first()


def paid_summary(booking):
    parts = list(booking.installments.all())
    paid = [part for part in parts if part.status == "paid"]
    return {
        "count": len(parts), "paid_count": len(paid),
        "paid_total": sum((part.amount for part in paid), Decimal("0")),
        "left_total": sum((part.amount for part in parts if part.status != "paid"), Decimal("0")),
    }

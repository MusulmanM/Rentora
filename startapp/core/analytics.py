"""Provider income by month and by year.

Income is the agreed rent of every booking the provider accepted (confirmed, handed over or
returned) plus late-return debt that was collected. A booking counts in the month it starts.
"""
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear
from django.utils import timezone

from .models import Booking

EARNING_STATUSES = (Booking.Status.CONFIRMED, Booking.Status.HANDED_OVER, Booking.Status.RETURNED)
MONTH_LABELS = ("Yan", "Fev", "Mar", "Apr", "May", "Iyun", "Iyul", "Avg", "Sen", "Okt", "Noy", "Dek")
_ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=16, decimal_places=2))
_INCOME = Coalesce(Sum(F("total_price") + F("debt_amount"), output_field=DecimalField(max_digits=16, decimal_places=2)), _ZERO)


def provider_income(user, year=None):
    today = timezone.localdate()
    rentals = Booking.objects.filter(listing__owner=user, status__in=EARNING_STATUSES)
    by_year = {
        row["year"]: row
        for row in rentals.annotate(year=ExtractYear("check_in")).values("year").annotate(total=_INCOME, count=Count("id"))
    }
    years = sorted(set(by_year) | {today.year}, reverse=True)
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = today.year
    if year not in years:
        year = today.year

    by_month = {
        row["month"]: row
        for row in rentals.filter(check_in__year=year).annotate(month=ExtractMonth("check_in"))
        .values("month").annotate(total=_INCOME, count=Count("id"))
    }
    peak = max([row["total"] for row in by_month.values()] or [Decimal("0")])
    months = []
    for number, label in enumerate(MONTH_LABELS, start=1):
        row = by_month.get(number, {"total": Decimal("0"), "count": 0})
        months.append({
            "number": number, "label": label, "total": row["total"], "count": row["count"],
            "height": int(row["total"] * 100 / peak) if peak else 0,
            "is_current": year == today.year and number == today.month,
        })

    year_row = by_year.get(year, {"total": Decimal("0"), "count": 0})
    previous = by_year.get(year - 1, {"total": Decimal("0")})["total"]
    change = None
    if previous:
        change = round((year_row["total"] - previous) * 100 / previous)
    return {
        "year": year,
        "years": years,
        "year_total": year_row["total"],
        "year_count": year_row["count"],
        "previous_year_total": previous,
        "year_change": change,
        "month_total": by_month.get(today.month, {"total": Decimal("0")})["total"] if year == today.year else None,
        "average": (year_row["total"] / year_row["count"]).quantize(Decimal("1")) if year_row["count"] else Decimal("0"),
        "months": months,
        "yearly": [{"year": y, "total": by_year.get(y, {"total": Decimal("0")})["total"]} for y in years],
    }

import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .availability import listings_visible_to
from .gemini import chat_completion
from .models import Booking, BookingOrder, RentalListing

logger = logging.getLogger(__name__)

_SCHEMA = {
    "type": "object",
    "properties": {
        "task": {"type": "string", "enum": ["search", "calculate", "search_and_calculate", "support", "out_of_scope"]},
        "kind": {"type": ["string", "null"], "enum": ["home", "car", None]},
        "city": {"type": ["string", "null"]},
        "guests": {"type": ["integer", "null"]},
        "bedrooms": {"type": ["integer", "null"]},
        "min_price": {"type": ["number", "null"]},
        "max_price": {"type": ["number", "null"]},
        "listing_search": {"type": ["string", "null"]},
        "sort_by": {"type": "string", "enum": ["recommended", "price_low", "price_high", "newest"]},
        "rental_days": {"type": ["integer", "null"]},
        "check_in": {"type": ["string", "null"]},
        "check_out": {"type": ["string", "null"]},
        "support_answer": {"type": "string"},
        "escalate": {"type": "boolean"},
    },
    "required": [
        "task", "kind", "city", "guests", "bedrooms", "min_price", "max_price",
        "listing_search", "sort_by", "rental_days", "check_in", "check_out",
        "support_answer", "escalate",
    ],
    "additionalProperties": False,
}


class RentalAssistantError(Exception):
    def __init__(self, message, status_code=502):
        self.status_code = status_code
        super().__init__(message)


def _interpret_request(message, language="uz"):
    if not getattr(settings, "GEMINI_API_KEY", ""):
        raise RentalAssistantError("AI qidiruv uchun GEMINI_API_KEY sozlanmagan.", status_code=503)

    today = timezone.localdate()
    payload = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Rentora's rental search and customer-support assistant. "
                    "Classify each message as rental search/calculation, Rentora support, or out_of_scope. "
                    "For support, answer only with these confirmed facts: users can browse homes and cars, "
                    "filter listings, submit bookings, pay cash or use configured online checkout, and contact "
                    "the provider from an owned listing. Providers review booking requests and mark handover. "
                    "For account-specific, payment disputes, safety, legal, or unknown questions set escalate=true "
                    "and do not invent an answer. Do not claim a human was contacted; the app will create an admin ticket. "
                    "Never ask for passwords, OTP codes, or payment credentials. Do not answer unrelated questions; "
                    "set task=out_of_scope. Return only the schema fields. Prices are Uzbek som per day. "
                    "Convert relative dates using today's date, which is " + today.isoformat() + ". "
                    "Set rental_days only when the user requests a rental duration or provides a valid date range. "
                    "Do not invent a city, budget, guests, bedrooms, listing, or dates. "
                    f"Write any user-facing support_answer in this language: {language} "
                    "(uz=Uzbek, ru=Russian, en=English). Keep task, filters, dates, and all schema values unchanged."
                ),
            },
            {"role": "user", "content": message},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "rental_request", "strict": True, "schema": _SCHEMA},
        },
    }
    try:
        result = chat_completion(payload, timeout=20)
    except HTTPError as exc:
        logger.warning("Gemini rental assistant returned HTTP %s", exc.code)
        messages = {
            400: "Gemini so'rovni rad etdi. GEMINI_MODEL qiymatini va model imkoniyatlarini tekshiring.",
            401: "GEMINI_API_KEY noto'g'ri yoki bekor qilingan. Kalitni server sozlamalarida tekshiring.",
            403: "Gemini ushbu modelga kirishga ruxsat bermadi. Hisob va model ruxsatlarini tekshiring.",
            404: "GEMINI_MODEL topilmadi. Model nomini server sozlamalarida tekshiring.",
            429: "AI yordamchining limiti vaqtincha tugagan. Birozdan keyin qayta urinib ko'ring.",
        }
        raise RentalAssistantError(
            messages.get(exc.code, "Gemini xizmati so'rovni qabul qilmadi. Birozdan keyin qayta urinib ko'ring."),
            status_code=503 if exc.code in {401, 403, 404, 429} else 502,
        ) from exc
    except URLError as exc:
        logger.warning("Gemini rental assistant connection failed: %s", exc.reason)
        raise RentalAssistantError("AI xizmatiga ulanib bo'lmadi. Birozdan keyin qayta urinib ko'ring.") from exc
    except TimeoutError as exc:
        logger.warning("Gemini rental assistant request timed out")
        raise RentalAssistantError("AI xizmatiga ulanib bo'lmadi. Birozdan keyin qayta urinib ko'ring.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.exception("Gemini rental assistant returned invalid JSON")
        raise RentalAssistantError("AI xizmatidan noto'g'ri javob olindi.") from exc

    try:
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        logger.exception("Gemini rental assistant response did not match the expected schema")
        raise RentalAssistantError("AI xizmatidan noto'g'ri javob olindi.") from exc
    if not isinstance(parsed, dict):
        raise RentalAssistantError("AI xizmatidan noto'g'ri javob olindi.")
    return parsed


def _validated_criteria(criteria):
    if criteria.get("task") == "out_of_scope":
        return None
    if criteria.get("task") == "support":
        answer = criteria.get("support_answer", "")
        escalate = criteria.get("escalate", False)
        if not isinstance(answer, str) or len(answer) > 1500 or not isinstance(escalate, bool):
            raise RentalAssistantError("AI yordam javobi noto'g'ri formatda.")
        return {"task": "support", "support_answer": answer.strip(), "escalate": escalate}
    if criteria.get("task") not in {"search", "calculate", "search_and_calculate"}:
        raise RentalAssistantError("AI qidiruv mezonlarini aniqlay olmadi.")

    kind = criteria.get("kind")
    if kind not in (None, RentalListing.Kind.HOME, RentalListing.Kind.CAR):
        raise RentalAssistantError("Ijara turi noto'g'ri aniqlandi.")
    city = criteria.get("city")
    listing_search = criteria.get("listing_search")
    if city is not None and (not isinstance(city, str) or len(city) > 80):
        raise RentalAssistantError("Shahar filtri noto'g'ri aniqlandi.")
    if listing_search is not None and (not isinstance(listing_search, str) or len(listing_search) > 100):
        raise RentalAssistantError("E'lon filtri noto'g'ri aniqlandi.")

    validated = {
        "task": criteria["task"],
        "kind": kind,
        "city": city.strip() if city else None,
        "listing_search": listing_search.strip() if listing_search else None,
        "sort_by": criteria.get("sort_by", "recommended"),
    }
    if validated["sort_by"] not in {"recommended", "price_low", "price_high", "newest"}:
        raise RentalAssistantError("Saralash turi noto'g'ri aniqlandi.")

    for field in ("guests", "bedrooms"):
        value = criteria.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20):
            raise RentalAssistantError("Mehmonlar yoki xonalar soni noto'g'ri aniqlandi.")
        validated[field] = value
    for field in ("min_price", "max_price"):
        value = criteria.get(field)
        if value is None:
            validated[field] = None
            continue
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise RentalAssistantError("Narx filtri noto'g'ri aniqlandi.") from exc
        if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000000"):
            raise RentalAssistantError("Narx filtri noto'g'ri aniqlandi.")
        validated[field] = amount

    days = criteria.get("rental_days")
    if days is not None and (isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365):
        raise RentalAssistantError("Ijara muddati 1–365 kun oralig'ida bo'lishi kerak.")
    check_in, check_out = criteria.get("check_in"), criteria.get("check_out")
    if check_in is not None or check_out is not None:
        try:
            start, end = date.fromisoformat(check_in), date.fromisoformat(check_out)
        except (TypeError, ValueError) as exc:
            raise RentalAssistantError("Ijara sanalari noto'g'ri aniqlandi.") from exc
        if start < timezone.localdate() or end <= start or (end - start).days > 365:
            raise RentalAssistantError("Ijara sanalari yaroqsiz.")
        days = (end - start).days
        validated["check_in"] = start
        validated["check_out"] = end
    else:
        validated["check_in"] = None
        validated["check_out"] = None
    validated["rental_days"] = days
    return validated


def find_rentals(message, user=None, language="uz"):
    criteria = _validated_criteria(_interpret_request(message, language=language))
    if criteria is None:
        return {
            "message": "Men faqat ijara e'lonlarini filtrlash, narx bo'yicha saralash va ijara summasini hisoblashda yordam beraman.",
            "results": [],
        }
    if criteria["task"] == "support":
        if criteria["escalate"]:
            from .models import ContactMessage

            authenticated = bool(getattr(user, "is_authenticated", False))
            if authenticated:
                # Signed-in users get the answer in their admin chat, where admins reply.
                from .chat import post_message, support_conversation_for

                conversation = support_conversation_for(user)
                post_message(conversation, user, text=message[:5000])
                chat_url = reverse("chat-room", args=[conversation.pk])
            else:
                ContactMessage.objects.create(
                    name="Sayt foydalanuvchisi", subject="AI yordam so'rovi", message=message,
                )
                chat_url = reverse("guest-support")
            answer = criteria["support_answer"] or "Savolingiz adminlarga yuborildi."
            answer += " Savolingiz administratorlar navbatiga yuborildi."
            return {"message": answer, "results": [], "escalated": True, "chat_url": chat_url}
        answer = criteria["support_answer"] or "Rentora bo'yicha yordam so'rovingizni aniqlay olmadim."
        return {"message": answer, "results": [], "escalated": False}

    listings = listings_visible_to(
        user,
        RentalListing.objects.select_related("region", "district").prefetch_related("images"),
    )
    if criteria["kind"]:
        listings = listings.filter(kind=criteria["kind"])
    if criteria["city"]:
        listings = listings.filter(
            Q(city__icontains=criteria["city"])
            | Q(district__name_uz__icontains=criteria["city"])
            | Q(region__name_uz__icontains=criteria["city"])
            | Q(region__name_en__icontains=criteria["city"])
        )
    if criteria["guests"]:
        listings = listings.filter(capacity__gte=criteria["guests"])
    if criteria["bedrooms"]:
        listings = listings.filter(kind=RentalListing.Kind.HOME, bedrooms__gte=criteria["bedrooms"])
    if criteria["min_price"] is not None:
        listings = listings.filter(price_per_day__gte=criteria["min_price"])
    if criteria["max_price"] is not None:
        listings = listings.filter(price_per_day__lte=criteria["max_price"])
    if criteria["listing_search"]:
        term = criteria["listing_search"]
        listings = listings.filter(
            Q(title__icontains=term)
            | Q(title_ru__icontains=term)
            | Q(title_en__icontains=term)
            | Q(description__icontains=term)
            | Q(description_ru__icontains=term)
            | Q(description_en__icontains=term)
            | Q(city__icontains=term)
            | Q(brand__icontains=term)
        )
    if criteria["check_in"] and criteria["check_out"]:
        unavailable_ids = Booking.objects.filter(
            status__in=[
                Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.HANDED_OVER,
            ],
            check_in__lt=criteria["check_out"],
            check_out__gt=criteria["check_in"],
        ).values_list("listing_id", flat=True)
        unavailable_order_ids = BookingOrder.objects.filter(
            status__in=[BookingOrder.Status.PENDING, BookingOrder.Status.AWAITING_PAYMENT],
            check_in__lt=criteria["check_out"],
            check_out__gt=criteria["check_in"],
        ).values_list("listing_id", flat=True)
        listings = listings.exclude(pk__in=unavailable_ids).exclude(pk__in=unavailable_order_ids)

    sort_order = {
        "price_low": ("price_per_day", "-created_at"),
        "price_high": ("-price_per_day", "-created_at"),
        "newest": ("-created_at",),
        "recommended": ("-is_featured", "-created_at"),
    }[criteria["sort_by"]]
    listings = listings.order_by(*sort_order)[:12]

    results = []
    for listing in listings:
        result = {
            "title": listing.title,
            "title_ru": listing.title_ru,
            "title_en": listing.title_en,
            "city": listing.city,
            "region": listing.region.name_uz if listing.region_id else "",
            "kind": listing.get_kind_display(),
            "price_per_day": str(listing.price_per_day),
            "image_url": listing.primary_image_url,
            "url": reverse("listing-detail", args=[listing.slug]),
        }
        if criteria["rental_days"]:
            result["rental_days"] = criteria["rental_days"]
            result["total_price"] = str(listing.price_per_day * criteria["rental_days"])
        results.append(result)

    if results:
        message_text = f"{len(results)} ta mos ijara varianti topildi."
        if criteria["rental_days"]:
            message_text += f" Jami narx {criteria['rental_days']} kun uchun hisoblandi."
    else:
        message_text = "Bu mezonlarga mos ijara varianti topilmadi. Filtrlarni o'zgartirib ko'ring."
    return {"message": message_text, "results": results}

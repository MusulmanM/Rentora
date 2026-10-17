from decimal import Decimal, InvalidOperation
from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def money(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{number:,.0f}".replace(",", " ")


def _localized_span(uz, ru, en):
    # i18n.js swaps the text for the selected language; missing translations fall back to Uzbek.
    return format_html(
        '<span data-localized-text data-uz="{}" data-ru="{}" data-en="{}">{}</span>',
        uz, ru or uz, en or uz, uz,
    )


@register.simple_tag
def localized_title(listing):
    return _localized_span(listing.title, listing.title_ru, listing.title_en)


@register.simple_tag
def place_name(place):
    """A region or district name in the selected language."""
    if place is None:
        return ""
    return _localized_span(place.name_uz, place.name_ru, place.name_en)


@register.simple_tag
def place_attrs(place):
    """data-* attributes for an <option> that shows a region or district name."""
    return format_html(
        'data-localized-text data-uz="{}" data-ru="{}" data-en="{}"',
        place.name_uz, place.name_ru or place.name_uz, place.name_en or place.name_uz,
    )


@register.simple_tag
def listing_location(listing):
    """"District, Region" for a listing, falling back to the free-text city."""
    if listing.district_id:
        location = place_name(listing.district)
    else:
        location = listing.city  # Free text; the static dictionary translates common city names.
    if listing.region_id:
        return format_html('<span class="place">{}, {}</span>', location, place_name(listing.region))
    return format_html('<span class="place">{}</span>', location)


@register.simple_tag
def user_avatar(user, css_class="user-avatar"):
    """The user's photo, or the first letter of their name on a coloured circle."""
    account = getattr(user, "account", None)
    if account is not None and account.avatar:
        return format_html('<img class="{}" src="{}" alt="">', css_class, account.avatar.url)
    initial = (user.first_name or user.get_username() or "?")[:1].upper()
    return format_html('<span class="{} user-avatar-initial" aria-hidden="true">{}</span>', css_class, initial)


@register.filter
def stars(value):
    """4.3 -> "★★★★☆" (rounded to whole stars)."""
    try:
        filled = max(0, min(5, round(float(value))))
    except (TypeError, ValueError):
        filled = 0
    return "★" * filled + "☆" * (5 - filled)


@register.simple_tag(takes_context=True)
def absolute_url(context, url):
    """A full https:// address for links shared outside the site (Open Graph, canonical)."""
    if not url:
        return ""
    url = str(url)
    if url.startswith(("https://", "http://")):
        return url
    from django.conf import settings

    request = context.get("request")
    base = getattr(settings, "PUBLIC_SITE_URL", "") or (request.build_absolute_uri("/") if request else "")
    return base.rstrip("/") + "/" + url.lstrip("/")


@register.simple_tag(takes_context=True)
def listing_jsonld(context, listing, review_average=None, review_count=0):
    """schema.org Product data for search results (name, photo, daily price, rating)."""
    import json

    from django.utils.safestring import mark_safe

    image = absolute_url(context, listing.primary_image_url)
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": listing.title,
        "description": (listing.description or "")[:500],
        "url": absolute_url(context, context["request"].path),
        "brand": {"@type": "Brand", "name": "Rentora"},
        "category": "Car rental" if listing.kind == "car" else "Home rental",
        "offers": {
            "@type": "Offer",
            "price": f"{listing.price_per_day:.0f}",
            "priceCurrency": "UZS",
            "availability": "https://schema.org/InStock",
            "priceSpecification": {
                "@type": "UnitPriceSpecification", "price": f"{listing.price_per_day:.0f}",
                "priceCurrency": "UZS", "unitCode": "DAY",
            },
        },
    }
    if image:
        data["image"] = [image]
    if review_count and review_average:
        data["aggregateRating"] = {
            "@type": "AggregateRating", "ratingValue": f"{float(review_average):.1f}", "reviewCount": int(review_count),
        }
    # "</" cannot appear inside the JSON, so the script block can never be closed early.
    return mark_safe(json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


@register.simple_tag
def next_installment(booking):
    """The first unpaid part of a booking's instalment plan (only that one can be paid online)."""
    for part in booking.installments.all():
        if part.status == "pending":
            return part
    return None


@register.simple_tag
def installment_summary(booking):
    from ..installments import paid_summary

    return paid_summary(booking)

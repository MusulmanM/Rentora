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
        return format_html("{}, {}", location, place_name(listing.region))
    return location

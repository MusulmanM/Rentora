from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


@register.filter
def money(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{number:,.0f}".replace(",", " ")

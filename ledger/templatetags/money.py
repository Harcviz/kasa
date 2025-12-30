from django import template

register = template.Library()


@register.filter
def money(value):
    """
    Formats a Decimal/number with thousands separator and 2 decimals using Turkish-style comma/point.
    Example: 12345.6 -> 12.345,60
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    formatted = f"{num:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")

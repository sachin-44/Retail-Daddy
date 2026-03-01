from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Get a value from a dict by key.
    Tries int key first, then string key — handles Django session JSON
    which converts integer dict keys to strings on serialization.
    """
    if not isinstance(dictionary, dict):
        return None
    # Try as-is
    if key in dictionary:
        return dictionary[key]
    # Try int version
    try:
        int_key = int(key)
        if int_key in dictionary:
            return dictionary[int_key]
    except (ValueError, TypeError):
        pass
    # Try string version
    str_key = str(key)
    if str_key in dictionary:
        return dictionary[str_key]
    return None


@register.filter
def score_bar_width(value):
    """Convert 0-1 score to CSS percentage width."""
    try:
        pct = float(value) * 100
        return f"{min(max(pct, 2), 100):.1f}%"
    except (ValueError, TypeError):
        return "2%"


@register.filter
def as_percent(value):
    """Convert 0-1 float to percentage string."""
    try:
        return f"{float(value) * 100:.1f}%"
    except (ValueError, TypeError):
        return "0.0%"


@register.filter
def mul100(value):
    """Multiply a 0-1 float by 100 and return as rounded integer string."""
    try:
        return f"{float(value) * 100:.0f}"
    except (ValueError, TypeError):
        return "0"


@register.filter
def zip_with(a, b):
    return zip(a, b)

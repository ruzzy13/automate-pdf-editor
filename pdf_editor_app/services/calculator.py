def _to_float(value, field_name):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f' "{field_name}"\'s value is not valid: {value!r} is not a number.')


def calculate_and_print_price(price_before, first_percent, second_percent):
    n = _to_float(price_before, "price_before")
    a = _to_float(first_percent, "first_percent")
    b = _to_float(second_percent, "second_percent")

    if b == 0:
        raise ZeroDivisionError('Percent value can\'t be 0.')

    return (n * (a / 100)) / (b / 100)
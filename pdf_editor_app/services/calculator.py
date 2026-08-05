def _to_float(value, field_name):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f'Nilai "{field_name}" tidak valid: {value!r} bukan angka.')


def calculate_and_print_price(price_before, first_percent, second_percent):
    n = _to_float(price_before, "price_before")
    a = _to_float(first_percent, "first_percent")
    b = _to_float(second_percent, "second_percent")

    if b == 0:
        raise ZeroDivisionError('Nilai "second_percent" tidak boleh 0.')

    return (n * (a / 100)) / (b / 100)
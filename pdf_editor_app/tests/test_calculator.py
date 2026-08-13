import unittest

from pdf_editor_app.services.calculator import calculate_and_print_price, _to_float


class ToFloatTests(unittest.TestCase):

    def test_accepts_int(self):
        self.assertEqual(_to_float(10, "field"), 10.0)

    def test_accepts_float(self):
        self.assertEqual(_to_float(10.5, "field"), 10.5)

    def test_accepts_numeric_string(self):
        self.assertEqual(_to_float("10.5", "field"), 10.5)

    def test_rejects_non_numeric_string(self):
        with self.assertRaises(ValueError) as ctx:
            _to_float("abc", "first_percent")
        self.assertIn("first_percent", str(ctx.exception))

    def test_rejects_none(self):
        with self.assertRaises(ValueError):
            _to_float(None, "field")


class CalculateAndPrintPriceTests(unittest.TestCase):

    def test_basic_calculation(self):
        result = calculate_and_print_price(1000, 11, 12)
        self.assertAlmostEqual(result, 916.6666666666667)

    def test_equal_percentages_returns_original_price(self):
        result = calculate_and_print_price(2650282004.00, 11, 11)
        self.assertAlmostEqual(result, 2650282004.00)

    def test_accepts_numeric_strings(self):
        result = calculate_and_print_price("1000", "11", "12")
        self.assertAlmostEqual(result, 916.6666666666667)

    def test_zero_first_percent_returns_zero(self):
        result = calculate_and_print_price(1000, 0, 12)
        self.assertEqual(result, 0.0)

    def test_zero_second_percent_raises_zero_division(self):
        with self.assertRaises(ZeroDivisionError):
            calculate_and_print_price(1000, 11, 0)

    def test_negative_price_is_allowed(self):
        result = calculate_and_print_price(-1000, 11, 12)
        self.assertAlmostEqual(result, -916.6666666666667)

    def test_invalid_price_raises_value_error(self):
        with self.assertRaises(ValueError):
            calculate_and_print_price("not-a-number", 11, 12)

    def test_invalid_first_percent_raises_value_error(self):
        with self.assertRaises(ValueError):
            calculate_and_print_price(1000, "not-a-number", 12)

    def test_invalid_second_percent_raises_value_error(self):
        with self.assertRaises(ValueError):
            calculate_and_print_price(1000, 11, "not-a-number")


if __name__ == "__main__":
    unittest.main()
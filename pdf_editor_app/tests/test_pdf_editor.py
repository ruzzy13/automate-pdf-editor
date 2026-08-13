import os
import shutil
import tempfile
import unittest

import fitz

from pdf_editor_app.services import pdf_editor as pe


class ColorAndFontHelperTests(unittest.TestCase):

    def test_get_color_tuple_none_defaults_to_black(self):
        self.assertEqual(pe._get_color_tuple(None), (0, 0, 0))

    def test_get_color_tuple_white(self):
        self.assertEqual(pe._get_color_tuple(0xFFFFFF), (1.0, 1.0, 1.0))

    def test_get_color_tuple_red(self):
        r, g, b = pe._get_color_tuple(0xFF0000)
        self.assertAlmostEqual(r, 1.0)
        self.assertAlmostEqual(g, 0.0)
        self.assertAlmostEqual(b, 0.0)

    def test_pick_font_plain_defaults_to_helvetica(self):
        self.assertEqual(pe._pick_font("Arial"), "Helvetica")

    def test_pick_font_bold(self):
        self.assertEqual(pe._pick_font("Arial-Bold"), "Helvetica-Bold")

    def test_pick_font_times_italic(self):
        self.assertEqual(pe._pick_font("Times New Roman Italic"), "Times-Italic")

    def test_pick_font_courier_bold_italic(self):
        self.assertEqual(pe._pick_font("Courier-BoldOblique"), "Courier-BoldOblique")

    def test_pick_font_none_defaults_to_helvetica(self):
        self.assertEqual(pe._pick_font(None), "Helvetica")


class NumberFormatTests(unittest.TestCase):

    def test_detect_format_dot_thousands_comma_decimal(self):
        fmt = pe._detect_number_format("2.650.282.004,00")
        self.assertEqual(fmt["thousands_sep"], ".")
        self.assertEqual(fmt["decimal_sep"], ",")
        self.assertEqual(fmt["decimals"], 2)

    def test_detect_format_comma_thousands_dot_decimal(self):
        fmt = pe._detect_number_format("2,650,282,004.00")
        self.assertEqual(fmt["thousands_sep"], ",")
        self.assertEqual(fmt["decimal_sep"], ".")
        self.assertEqual(fmt["decimals"], 2)

    def test_detect_format_dot_as_thousands_only(self):
        fmt = pe._detect_number_format("5.000")
        self.assertEqual(fmt["thousands_sep"], ".")
        self.assertIsNone(fmt["decimal_sep"])

    def test_detect_format_plain_integer(self):
        fmt = pe._detect_number_format("1234")
        self.assertIsNone(fmt["thousands_sep"])
        self.assertIsNone(fmt["decimal_sep"])

    def test_parse_number_string_comma_thousands(self):
        self.assertAlmostEqual(pe._parse_number_string("2,650,282,004.00"), 2650282004.00)

    def test_parse_number_string_dot_thousands_comma_decimal(self):
        self.assertAlmostEqual(pe._parse_number_string("2.650.282.004,00"), 2650282004.00)

    def test_parse_number_string_invalid_returns_none(self):
        self.assertIsNone(pe._parse_number_string("not-a-number"))

    def test_format_number_like_preserves_comma_thousands_style(self):
        result = pe._format_number_like("2,650,282,004.00", 291531020.4)
        self.assertEqual(result, "291,531,020.40")

    def test_format_number_like_preserves_dot_thousands_comma_decimal_style(self):
        result = pe._format_number_like("2.650.282.004,00", 291531020.4)
        self.assertEqual(result, "291.531.020,40")

    def test_format_number_like_plain_integer_style(self):
        result = pe._format_number_like("5000", 1234.0)
        self.assertEqual(result, "1234")


class PdfFixtureTestCase(unittest.TestCase):
    """Base class that builds a scratch dir + helper for making test PDFs."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _path(self, name):
        return os.path.join(self.tmpdir, name)

    def _make_pdf(self, path, lines):
        """lines: list of (x, y, text, fontsize) tuples, one insert_text call each."""
        doc = fitz.open()
        page = doc.new_page()
        for x, y, text, fontsize in lines:
            page.insert_text((x, y), text, fontsize=fontsize)
        doc.save(path)
        doc.close()
        return path


class SearchFlexibleTests(PdfFixtureTestCase):

    def test_exact_match(self):
        path = self._make_pdf(self._path("in.pdf"), [(50, 100, "Hello World", 11)])
        doc = fitz.open(path)
        rects, variant = pe._search_flexible(doc[0], "Hello World")
        doc.close()
        self.assertEqual(len(rects), 1)
        self.assertEqual(variant, "Hello World")

    def test_no_match_returns_empty(self):
        path = self._make_pdf(self._path("in.pdf"), [(50, 100, "Hello World", 11)])
        doc = fitz.open(path)
        rects, variant = pe._search_flexible(doc[0], "Not Present")
        doc.close()
        self.assertEqual(rects, [])
        self.assertIsNone(variant)


class ReplaceTextInPdfTests(PdfFixtureTestCase):

    def test_replaces_single_occurrence(self):
        in_path = self._make_pdf(self._path("in.pdf"), [(50, 100, "Jakarta, January 1, 2026", 11)])
        out_path = self._path("out.pdf")

        pe.replace_text_in_pdf(in_path, out_path, "January 1, 2026", "August 4, 2026")

        doc = fitz.open(out_path)
        text = doc[0].get_text()
        doc.close()
        self.assertIn("August 4, 2026", text)
        self.assertNotIn("January 1, 2026", text)

    def test_replaces_all_occurrences_by_default(self):
        in_path = self._make_pdf(self._path("in.pdf"), [
            (50, 100, "Hello", 11),
            (50, 130, "Hello", 11),
        ])
        out_path = self._path("out.pdf")

        _, count = pe.replace_text_in_pdf(in_path, out_path, "Hello", "Hi")
        self.assertEqual(count, 2)

        doc = fitz.open(out_path)
        text = doc[0].get_text()
        doc.close()
        self.assertEqual(text.count("Hi"), 2)
        self.assertNotIn("Hello", text)

    def test_replaces_only_selected_occurrence_indices(self):
        in_path = self._make_pdf(self._path("in.pdf"), [
            (50, 100, "Hello", 11),
            (50, 130, "Hello", 11),
            (50, 160, "Hello", 11),
        ])
        out_path = self._path("out.pdf")

        _, count = pe.replace_text_in_pdf(in_path, out_path, "Hello", "Hi", occurrence_indices={2})
        self.assertEqual(count, 1)

        doc = fitz.open(out_path)
        text = doc[0].get_text()
        doc.close()
        self.assertEqual(text.count("Hi"), 1)
        self.assertEqual(text.count("Hello"), 2)


class ListOccurrencesTests(PdfFixtureTestCase):

    def test_counts_and_locates_each_occurrence(self):
        in_path = self._make_pdf(self._path("in.pdf"), [
            (50, 100, "Hello", 11),
            (50, 130, "Hello", 11),
        ])

        occurrences, variant = pe._list_occurrences(in_path, "Hello")

        self.assertEqual(len(occurrences), 2)
        self.assertEqual([o["index"] for o in occurrences], [1, 2])
        self.assertTrue(all(o["page"] == 1 for o in occurrences))
        self.assertEqual(variant, "Hello")

    def test_no_occurrences_returns_empty_list(self):
        in_path = self._make_pdf(self._path("in.pdf"), [(50, 100, "Hello", 11)])
        occurrences, variant = pe._list_occurrences(in_path, "Not Present")
        self.assertEqual(occurrences, [])
        self.assertIsNone(variant)


class FindNumberBetweenWordsTests(PdfFixtureTestCase):

    def test_finds_number_when_perfectly_aligned(self):
        path = self._make_pdf(self._path("in.pdf"), [
            (50, 100, "Sub Total", 11),
            (400, 100, "2,650,282,004.00", 11),
            (520, 100, "IDR", 11),
        ])

        result = pe.find_number_between_words(path, before_word="Total", stop_symbol="IDR")

        self.assertIsNotNone(result)
        self.assertEqual(result["raw_text"], "2,650,282,004.00")

    def test_finds_number_with_slight_baseline_offset(self):
        path = self._make_pdf(self._path("in.pdf"), [
            (50, 100, "Sub Total", 11),
            (400, 104, "2,650,282,004.00", 9),
            (520, 104, "IDR", 9),
        ])

        result = pe.find_number_between_words(path, before_word="Total", stop_symbol="IDR")

        self.assertIsNotNone(result)
        self.assertEqual(result["raw_text"], "2,650,282,004.00")

    def test_returns_none_when_keyword_missing(self):
        path = self._make_pdf(self._path("in.pdf"), [
            (50, 100, "Sub Total", 11),
            (400, 100, "2,650,282,004.00", 11),
            (520, 100, "IDR", 11),
        ])

        result = pe.find_number_between_words(path, before_word="Discount", stop_symbol="IDR")
        self.assertIsNone(result)

    def test_returns_none_when_symbol_missing_after_number(self):
        path = self._make_pdf(self._path("in.pdf"), [
            (50, 100, "Total", 11),
            (400, 100, "2,650,282,004.00", 11),
        ])

        result = pe.find_number_between_words(path, before_word="Total", stop_symbol="IDR")
        self.assertIsNone(result)

    def test_ignores_number_on_a_different_line(self):
        path = self._make_pdf(self._path("in.pdf"), [
            (50, 100, "Total", 11),
            (400, 100, "IDR", 11),          
            (400, 300, "999", 11),          
        ])

        result = pe.find_number_between_words(path, before_word="Total", stop_symbol="IDR")
        self.assertIsNone(result)


class SavePdfSafelyTests(PdfFixtureTestCase):

    def test_saves_to_requested_path(self):
        doc = fitz.open()
        doc.new_page()
        out_path = self._path("out.pdf")

        final_path = pe._save_pdf_safely(doc, out_path)
        doc.close()

        self.assertEqual(final_path, out_path)
        self.assertTrue(os.path.exists(out_path))


if __name__ == "__main__":
    unittest.main()
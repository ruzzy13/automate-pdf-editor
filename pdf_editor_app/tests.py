import io

import fitz
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from pdf_editor_app import views


def make_pdf_bytes(lines):
    """lines: list of (x, y, text, fontsize) tuples -> returns raw PDF bytes."""
    doc = fitz.open()
    page = doc.new_page()
    for x, y, text, fontsize in lines:
        page.insert_text((x, y), text, fontsize=fontsize)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_uploaded_pdf(name, lines):
    return SimpleUploadedFile(name, make_pdf_bytes(lines), content_type="application/pdf")


class FakeUploadedFile:
    """Minimal stand-in for Django's UploadedFile: only needs .name and .chunks()."""

    def __init__(self, name, content):
        self.name = name
        self._content = content

    def chunks(self):
        yield self._content


class ParseOccurrenceIndicesTests(TestCase):

    def test_none_returns_none(self):
        self.assertIsNone(views._parse_occurrence_indices(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(views._parse_occurrence_indices(""))

    def test_parses_comma_separated_ints(self):
        self.assertEqual(views._parse_occurrence_indices("1,3,5"), {1, 3, 5})

    def test_ignores_whitespace_and_invalid_parts(self):
        self.assertEqual(views._parse_occurrence_indices(" 1 , x, 3 ,,"), {1, 3})

    def test_all_invalid_returns_none(self):
        self.assertIsNone(views._parse_occurrence_indices("a,b,c"))


# ---------------------------------------------------------------------------
# _prepare_auto_replacement
# ---------------------------------------------------------------------------

class PrepareAutoReplacementTests(TestCase):

    def setUp(self):
        self.pdf_path = "/tmp/_test_auto_replacement.pdf"
        with open(self.pdf_path, "wb") as f:
            f.write(make_pdf_bytes([
                (50, 100, "Total", 11),
                (200, 100, "2,650,282,004.00", 11),
                (400, 100, "IDR", 11),
            ]))

    def test_computes_replacement_when_number_found(self):
        result = views._prepare_auto_replacement(self.pdf_path, "Total", "IDR", 11, 12)
        self.assertIsNotNone(result)
        self.assertEqual(result["target_str"], "2,650,282,004.00")
        self.assertEqual(result["replacement_str"], "2,429,425,170.33")

    def test_returns_none_when_keyword_not_found(self):
        result = views._prepare_auto_replacement(self.pdf_path, "Discount", "IDR", 11, 12)
        self.assertIsNone(result)

    def test_returns_none_when_percent_calculation_fails(self):
        result = views._prepare_auto_replacement(self.pdf_path, "Total", "IDR", 11, 0)
        self.assertIsNone(result)


class ProcessPdfTests(TestCase):

    def test_manual_replace_only(self):
        uploaded = FakeUploadedFile(
            "invoice.pdf",
            make_pdf_bytes([(50, 100, "Jakarta, January 1, 2026", 11)]),
        )
        cleaned_data = {
            "old_text": "January 1, 2026",
            "new_text": "August 4, 2026",
            "before_word": "",
            "stop_symbol": "%",
            "first_percent": None,
            "second_percent": None,
            "has_manual": True,
            "has_auto": False,
        }

        pdf_bytes, download_name = views._process_pdf(cleaned_data, uploaded)

        self.assertEqual(download_name, "invoice_edited.pdf")
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = doc[0].get_text()
        doc.close()
        self.assertIn("August 4, 2026", text)
        self.assertNotIn("January 1, 2026", text)

    def test_automatic_replace_only(self):
        uploaded = FakeUploadedFile(
            "invoice.pdf",
            make_pdf_bytes([
                (50, 100, "Total", 11),
                (200, 100, "2,650,282,004.00", 11),
                (400, 100, "IDR", 11),
            ]),
        )
        cleaned_data = {
            "old_text": "",
            "new_text": "",
            "before_word": "Total",
            "stop_symbol": "IDR",
            "first_percent": 11,
            "second_percent": 12,
            "has_manual": False,
            "has_auto": True,
        }

        pdf_bytes, _ = views._process_pdf(cleaned_data, uploaded)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = doc[0].get_text()
        doc.close()
        self.assertIn("2,429,425,170.33", text)
        self.assertNotIn("2,650,282,004.00", text)

    def test_automatic_replace_with_no_number_found_raises(self):
        uploaded = FakeUploadedFile(
            "invoice.pdf",
            make_pdf_bytes([(50, 100, "Nothing relevant here", 11)]),
        )
        cleaned_data = {
            "old_text": "",
            "new_text": "",
            "before_word": "Total",
            "stop_symbol": "IDR",
            "first_percent": 11,
            "second_percent": 12,
            "has_manual": False,
            "has_auto": True,
        }

        with self.assertRaises(ValueError):
            views._process_pdf(cleaned_data, uploaded)

    def test_manual_and_automatic_combined(self):
        uploaded = FakeUploadedFile(
            "invoice.pdf",
            make_pdf_bytes([
                (50, 100, "Jakarta, January 1, 2026", 11),
                (50, 130, "Total", 11),
                (200, 130, "2,650,282,004.00", 11),
                (400, 130, "IDR", 11),
            ]),
        )
        cleaned_data = {
            "old_text": "January 1, 2026",
            "new_text": "August 4, 2026",
            "before_word": "Total",
            "stop_symbol": "IDR",
            "first_percent": 11,
            "second_percent": 12,
            "has_manual": True,
            "has_auto": True,
        }

        pdf_bytes, _ = views._process_pdf(cleaned_data, uploaded)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = doc[0].get_text()
        doc.close()
        self.assertIn("August 4, 2026", text)
        self.assertIn("2,429,425,170.33", text)

    def test_no_operation_raises_value_error(self):
        uploaded = FakeUploadedFile("invoice.pdf", make_pdf_bytes([(50, 100, "Hello", 11)]))
        cleaned_data = {
            "old_text": "",
            "new_text": "",
            "before_word": "",
            "stop_symbol": "%",
            "first_percent": None,
            "second_percent": None,
            "has_manual": False,
            "has_auto": False,
        }

        with self.assertRaises(ValueError):
            views._process_pdf(cleaned_data, uploaded)

    def test_download_name_strips_existing_edited_suffix(self):
        uploaded = FakeUploadedFile(
            "invoice_edited.pdf",
            make_pdf_bytes([(50, 100, "Hello", 11)]),
        )
        cleaned_data = {
            "old_text": "Hello",
            "new_text": "Hi",
            "before_word": "",
            "stop_symbol": "%",
            "first_percent": None,
            "second_percent": None,
            "has_manual": True,
            "has_auto": False,
        }

        _, download_name = views._process_pdf(cleaned_data, uploaded)
        self.assertEqual(download_name, "invoice_edited.pdf")

    def test_only_selected_occurrences_are_replaced(self):
        uploaded = FakeUploadedFile(
            "invoice.pdf",
            make_pdf_bytes([
                (50, 100, "Hello", 11),
                (50, 130, "Hello", 11),
            ]),
        )
        cleaned_data = {
            "old_text": "Hello",
            "new_text": "Hi",
            "before_word": "",
            "stop_symbol": "%",
            "first_percent": None,
            "second_percent": None,
            "has_manual": True,
            "has_auto": False,
        }

        pdf_bytes, _ = views._process_pdf(cleaned_data, uploaded, occurrence_indices_raw="1")

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = doc[0].get_text()
        doc.close()
        self.assertEqual(text.count("Hi"), 1)
        self.assertEqual(text.count("Hello"), 1)


class UploadPdfApiTests(TestCase):

    def test_valid_pdf_returns_metadata(self):
        upload = make_uploaded_pdf("doc.pdf", [(50, 100, "Hello", 11)])
        resp = self.client.post(reverse("pdf_editor_app:upload_pdf_api"), {"pdf_file": upload})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["page_count"], 1)
        self.assertEqual(data["filename"], "doc.pdf")

    def test_non_pdf_file_is_rejected(self):
        upload = SimpleUploadedFile("doc.pdf", b"not a real pdf", content_type="application/pdf")
        resp = self.client.post(reverse("pdf_editor_app:upload_pdf_api"), {"pdf_file": upload})

        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])

    def test_missing_file_returns_400(self):
        resp = self.client.post(reverse("pdf_editor_app:upload_pdf_api"), {})
        self.assertEqual(resp.status_code, 400)

    def test_get_not_allowed(self):
        resp = self.client.get(reverse("pdf_editor_app:upload_pdf_api"))
        self.assertEqual(resp.status_code, 405)


class ListOccurrencesApiTests(TestCase):

    def test_finds_multiple_occurrences(self):
        upload = make_uploaded_pdf("doc.pdf", [
            (50, 100, "Hello", 11),
            (50, 130, "Hello", 11),
        ])
        resp = self.client.post(
            reverse("pdf_editor_app:list_occurrences_api"),
            {"pdf_file": upload, "old_text": "Hello"},
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["occurrences"]), 2)

    def test_empty_old_text_returns_empty_list_without_error(self):
        upload = make_uploaded_pdf("doc.pdf", [(50, 100, "Hello", 11)])
        resp = self.client.post(
            reverse("pdf_editor_app:list_occurrences_api"),
            {"pdf_file": upload, "old_text": ""},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["occurrences"], [])

    def test_missing_file_returns_400(self):
        resp = self.client.post(
            reverse("pdf_editor_app:list_occurrences_api"), {"old_text": "Hello"}
        )
        self.assertEqual(resp.status_code, 400)


class ReplacePdfApiTests(TestCase):

    def test_successful_manual_replace_returns_pdf(self):
        upload = make_uploaded_pdf("doc.pdf", [(50, 100, "Hello", 11)])
        resp = self.client.post(reverse("pdf_editor_app:replace_pdf_api"), {
            "pdf_file": upload,
            "old_text": "Hello",
            "new_text": "Hi",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertEqual(resp["X-Filename"], "doc_edited.pdf")

        doc = fitz.open(stream=resp.content, filetype="pdf")
        text = doc[0].get_text()
        doc.close()
        self.assertIn("Hi", text)

    def test_invalid_form_returns_400(self):
        resp = self.client.post(reverse("pdf_editor_app:replace_pdf_api"), {
            "old_text": "Hello",
            "new_text": "Hi",
        })
        self.assertEqual(resp.status_code, 400)

    def test_no_matching_text_returns_422(self):
        upload = make_uploaded_pdf("doc.pdf", [(50, 100, "Hello", 11)])
        resp = self.client.post(reverse("pdf_editor_app:replace_pdf_api"), {
            "pdf_file": upload,
            "before_word": "Total",
            "stop_symbol": "IDR",
            "first_percent": 11,
            "second_percent": 12,
        })
        self.assertEqual(resp.status_code, 422)
        self.assertFalse(resp.json()["ok"])

    def test_get_not_allowed(self):
        resp = self.client.get(reverse("pdf_editor_app:replace_pdf_api"))
        self.assertEqual(resp.status_code, 405)


class PageViewTests(TestCase):

    def test_editor_page_loads(self):
        resp = self.client.get(reverse("pdf_editor_app:editor"))
        self.assertEqual(resp.status_code, 200)

    def test_home_page_loads_on_get(self):
        resp = self.client.get(reverse("pdf_editor_app:home"))
        self.assertEqual(resp.status_code, 200)

    def test_home_page_post_returns_pdf(self):
        upload = make_uploaded_pdf("doc.pdf", [(50, 100, "Hello", 11)])
        resp = self.client.post(reverse("pdf_editor_app:home"), {
            "pdf_file": upload,
            "old_text": "Hello",
            "new_text": "Hi",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
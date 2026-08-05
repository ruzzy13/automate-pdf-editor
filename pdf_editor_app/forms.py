import os

from django import forms

MAX_UPLOAD_SIZE_BYTES = 15 * 1024 * 1024


class PDFProcessForm(forms.Form):
    pdf_file = forms.FileField(
        label="File PDF",
        help_text="Maksimal 15MB, format .pdf",
    )

    old_text = forms.CharField(
        label="Teks lama",
        required=False,
        max_length=500,
        widget=forms.TextInput(attrs={"placeholder": 'mis. "Jakarta, 1 Januari 2026"'}),
    )
    new_text = forms.CharField(
        label="Teks baru",
        required=False,
        max_length=500,
        widget=forms.TextInput(attrs={"placeholder": 'mis. "Jakarta, 4 Agustus 2026"'}),
    )

    before_word = forms.CharField(
        label="Kata kunci sebelum angka",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": 'mis. "VAT" atau "TOTAL"'}),
    )
    stop_symbol = forms.CharField(
        label="Simbol penutup",
        required=False,
        max_length=10,
        initial="%",
        widget=forms.TextInput(attrs={"placeholder": 'mis. "%" atau "$"'}),
    )
    first_percent = forms.FloatField(
        label="Persentase pertama",
        required=False,
        widget=forms.NumberInput(attrs={"step": "any", "placeholder": "mis. 11"}),
    )
    second_percent = forms.FloatField(
        label="Persentase kedua",
        required=False,
        widget=forms.NumberInput(attrs={"step": "any", "placeholder": "mis. 12"}),
    )

    def clean_pdf_file(self):
        f = self.cleaned_data["pdf_file"]
        if not f.name.lower().endswith(".pdf"):
            raise forms.ValidationError("File harus berformat .pdf.")
        if f.size > MAX_UPLOAD_SIZE_BYTES:
            raise forms.ValidationError("Ukuran file melebihi batas 15MB.")
        return f

    def clean(self):
        cleaned = super().clean()

        old_text = (cleaned.get("old_text") or "").strip()
        new_text = (cleaned.get("new_text") or "").strip()
        before_word = (cleaned.get("before_word") or "").strip()
        first_percent = cleaned.get("first_percent")
        second_percent = cleaned.get("second_percent")

        has_manual = bool(old_text and new_text)
        has_auto = bool(before_word) and first_percent is not None and second_percent is not None

        if bool(old_text) != bool(new_text):
            raise forms.ValidationError(
                "Untuk mode manual, isi kedua field: teks lama DAN teks baru."
            )
        if before_word and (first_percent is None or second_percent is None):
            raise forms.ValidationError(
                "Untuk mode otomatis, isi kata kunci, persentase pertama, DAN persentase kedua."
            )

        if not has_manual and not has_auto:
            raise forms.ValidationError(
                "Isi minimal salah satu mode: Find & Replace manual (teks lama & baru) "
                "atau Kalkulasi otomatis (kata kunci & kedua persentase)."
            )

        if second_percent is not None and second_percent == 0:
            self.add_error("second_percent", "Persentase kedua tidak boleh 0.")

        cleaned["stop_symbol"] = (cleaned.get("stop_symbol") or "%").strip() or "%"
        cleaned["has_manual"] = has_manual
        cleaned["has_auto"] = has_auto
        return cleaned
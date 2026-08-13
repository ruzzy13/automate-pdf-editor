import os

from django import forms

MAX_UPLOAD_SIZE_BYTES = 15 * 1024 * 1024

def validate_pdf_upload(f):
    if not f.name.lower().endswith(".pdf"):
        raise forms.ValidationError("File should be a PDF file.")
    if f.size > MAX_UPLOAD_SIZE_BYTES:
        raise forms.ValidationError("The file size exceeds the 15MB limit.")
    return f


class PDFUploadForm(forms.Form):
    pdf_file = forms.FileField(label="File PDF")

    def clean_pdf_file(self):
        return validate_pdf_upload(self.cleaned_data["pdf_file"])


class PDFProcessForm(forms.Form):
    pdf_file = forms.FileField(
        label="File PDF",
        help_text="Maximal 15MB, file must be PDF file",
    )

    old_text = forms.CharField(
        label="Previous Text",
        required=False,
        max_length=500,
        widget=forms.TextInput(attrs={"placeholder": 'example: "Hello World"'}),
    )
    new_text = forms.CharField(
        label="New Text",
        required=False,
        max_length=500,
        widget=forms.TextInput(attrs={"placeholder": 'example: "World Hello"'}),
    )

    before_word = forms.CharField(
        label="Keyword",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": 'example: "TOTAL"'}),
    )
    stop_symbol = forms.CharField(
        label="Boundary Sign",
        required=False,
        max_length=10,
        initial="%",
        widget=forms.TextInput(attrs={"placeholder": 'example: "$"'}),
    )
    first_percent = forms.FloatField(
        label="Previous Percentage",
        required=False,
        widget=forms.NumberInput(attrs={"step": "any", "placeholder": "example: 10"}),
    )
    second_percent = forms.FloatField(
        label="New Percentage",
        required=False,
        widget=forms.NumberInput(attrs={"step": "any", "placeholder": "example: 5"}),
    )

    def clean_pdf_file(self):
         return validate_pdf_upload(self.cleaned_data["pdf_file"])

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
                "For Find and Replace mode, fill these fields: Previous Text and New Text"
            )
        if before_word and (first_percent is None or second_percent is None):
            raise forms.ValidationError(
                "For Find and Automatic Replace mode, fill these fields: Keywords, Previous Text and New Text"
            )

        if not has_manual and not has_auto:
            raise forms.ValidationError(
                "Please choose one of these features : manual or automatic"
            )

        if first_percent is not None and first_percent == 0:
                    self.add_error("first_percent", "Any percentage can't be 0")

        if second_percent is not None and second_percent == 0:
            self.add_error("second_percent", "Any percentage can't be 0")

        cleaned["stop_symbol"] = (cleaned.get("stop_symbol") or "%").strip() or "%"
        cleaned["has_manual"] = has_manual
        cleaned["has_auto"] = has_auto
        return cleaned
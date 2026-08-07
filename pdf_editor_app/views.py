import os
import shutil
import uuid

import fitz
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .forms import PDFProcessForm, PDFUploadForm
from .services.calculator import calculate_and_print_price
from .services import pdf_editor as pe


def _prepare_auto_replacement(pdf_path, before_word, stop_symbol, first_percent, second_percent):
    auto_hit = pe.find_number_between_words(pdf_path, before_word=before_word, stop_symbol=stop_symbol)
    if auto_hit is None:
        return None

    price_raw_str = auto_hit["raw_text"]
    price_net = pe._parse_number_string(price_raw_str)
    if price_net is None:
        return None

    try:
        new_price = calculate_and_print_price(price_net, first_percent, second_percent)
    except (ValueError, ZeroDivisionError):
        return None

    return {
        "target_str": price_raw_str,
        "replacement_str": pe._format_number_like(price_raw_str, new_price),
        "page_index": auto_hit["page_index"],
        "rect": auto_hit["rect"],
    }


def _process_pdf(cleaned_data, uploaded_file):
    unique = uuid.uuid4().hex
    tmp_dir = settings.TMP_DIR

    input_path = os.path.join(tmp_dir, f"{unique}_input.pdf")
    manual_path = os.path.join(tmp_dir, f"{unique}_manual.pdf")
    output_path = os.path.join(tmp_dir, f"{unique}_output.pdf")
    temp_files = [input_path, manual_path, output_path]

    old_text = (cleaned_data.get("old_text") or "").strip()
    new_text = (cleaned_data.get("new_text") or "").strip()
    before_word = (cleaned_data.get("before_word") or "").strip()
    stop_symbol = cleaned_data.get("stop_symbol") or "%"
    first_percent = cleaned_data.get("first_percent")
    second_percent = cleaned_data.get("second_percent")

    has_manual = cleaned_data.get("has_manual", False)
    has_auto = cleaned_data.get("has_auto", False)

    try:
        with open(input_path, "wb") as dest:
            for chunk in uploaded_file.chunks():
                dest.write(chunk)

        auto_result = None
        if has_auto:
            auto_result = _prepare_auto_replacement(
                input_path, before_word, stop_symbol, first_percent, second_percent
            )
            if auto_result is None and not has_manual:
                raise ValueError(
                    f'No number was found between "{before_word}" and "{stop_symbol}", '
                    f"or that value could not be calculated."
                )

        if has_manual and auto_result:
            pe.replace_text_in_pdf(input_path, manual_path, old_text, new_text)

            auto_hit_after_manual = pe.find_number_between_words(
                manual_path, before_word=before_word, stop_symbol=stop_symbol
            )
            if auto_hit_after_manual is not None:
                pe.replace_at_position(
                    manual_path, output_path,
                    auto_hit_after_manual["page_index"], auto_hit_after_manual["rect"],
                    auto_result["replacement_str"],
                )
            else:
                # The automatic-mode number is no longer found after the manual replace -> keep the manual-only result.
                shutil.copyfile(manual_path, output_path)

        elif has_manual:
            pe.replace_text_in_pdf(input_path, output_path, old_text, new_text)

        elif auto_result:
            pe.replace_at_position(
                input_path, output_path,
                auto_result["page_index"], auto_result["rect"], auto_result["replacement_str"],
            )
        else:
            raise ValueError("No operation could be run with the input provided.")

        with open(output_path, "rb") as f:
            pdf_bytes = f.read()

        base_name = os.path.splitext(os.path.basename(uploaded_file.name))[0]
        download_name = f"{base_name}_edited.pdf"
        return pdf_bytes, download_name

    finally:
        for path in temp_files:
            if os.path.exists(path):
                os.remove(path)


def index(request):
    if request.method == "POST":
        form = PDFProcessForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                pdf_bytes, download_name = _process_pdf(form.cleaned_data, request.FILES["pdf_file"])
            except Exception as exc:  
                form.add_error(None, f"Failed to process PDF: {exc}")
            else:
                response = HttpResponse(pdf_bytes, content_type="application/pdf")
                response["Content-Disposition"] = f'attachment; filename="{download_name}"'
                response["Content-Length"] = str(len(pdf_bytes))
                return response
    else:
        form = PDFProcessForm()

    return render(request, "pdf_editor_app/index.html", {"form": form})

def editor(request):
    return render(request, "editor.html")


@require_POST
def upload_pdf_api(request):
    form = PDFUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)

    uploaded = form.cleaned_data["pdf_file"]
    tmp_path = os.path.join(settings.TMP_DIR, f"{uuid.uuid4().hex}_validate.pdf")

    try:
        with open(tmp_path, "wb") as dest:
            for chunk in uploaded.chunks():
                dest.write(chunk)
        try:
            doc = fitz.open(tmp_path)
            page_count = doc.page_count
            doc.close()
        except Exception:
            return JsonResponse(
                {"ok": False, "errors": {"pdf_file": ["Could not open the file as a PDF (it may be corrupted)."]}},
                status=400,
            )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return JsonResponse({
        "ok": True,
        "filename": uploaded.name,
        "page_count": page_count,
        "size": uploaded.size,
    })


@require_POST
def replace_pdf_api(request):
    form = PDFProcessForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)

    try:
        pdf_bytes, download_name = _process_pdf(form.cleaned_data, request.FILES["pdf_file"])
    except Exception as exc: 
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=422)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{download_name}"'
    response["X-Filename"] = download_name
    response["Access-Control-Expose-Headers"] = "X-Filename"
    response["Content-Length"] = str(len(pdf_bytes))
    return response
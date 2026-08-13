import os
import re
import fitz  # PyMuPDF


def _get_color_tuple(color_int):
    if color_int is None:
        return (0, 0, 0)
    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >> 8) & 0xFF) / 255.0
    b = (color_int & 0xFF) / 255.0
    return (r, g, b)


def _pick_font(span_font_name):
    name = (span_font_name or "").lower()
    bold = "bold" in name
    italic = "italic" in name or "oblique" in name

    if "times" in name or "serif" in name:
        if bold and italic:
            return "Times-BoldItalic"
        if bold:
            return "Times-Bold"
        if italic:
            return "Times-Italic"
        return "Times-Roman"
    elif "courier" in name or "mono" in name:
        if bold and italic:
            return "Courier-BoldOblique"
        if bold:
            return "Courier-Bold"
        if italic:
            return "Courier-Oblique"
        return "Courier"
    else:
        if bold and italic:
            return "Helvetica-BoldOblique"
        if bold:
            return "Helvetica-Bold"
        if italic:
            return "Helvetica-Oblique"
        return "Helvetica"


def _get_style_for_rect(rect, span_info_list):
    best_span = None
    best_overlap = 0
    for span in span_info_list:
        span_rect = fitz.Rect(span["bbox"])
        overlap_rect = span_rect & rect
        overlap_area = overlap_rect.get_area() if overlap_rect else 0
        if overlap_area > best_overlap:
            best_overlap = overlap_area
            best_span = span

    if best_span:
        font_size = best_span.get("size", 11)
        color_int = best_span.get("color", 0)
        font_name = best_span.get("font", "helv")
    else:
        font_size = rect.height * 0.75
        color_int = 0
        font_name = "helv"

    return font_size, _get_color_tuple(color_int), _pick_font(font_name)


def _replace_rects_on_page(page, rects, new_text, shrink_to_fit=True):
    if not rects:
        return 0

    text_dict = page.get_text("dict")
    span_info_list = []
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                span_info_list.append(span)

    styles = {}
    for i, rect in enumerate(rects):
        styles[i] = _get_style_for_rect(rect, span_info_list)

        height_diff = rect.height * 0.2
        rect.y0 += (height_diff / 2)
        rect.y1 -= (height_diff / 2)

        page.add_redact_annot(rect, fill=(1, 1, 1))

    page.apply_redactions()

    for i, rect in enumerate(rects):
        font_size, color_rgb, mapped_font = styles[i]

        final_size = font_size
        if shrink_to_fit:
            try:
                text_width = fitz.get_text_length(
                    new_text, fontname=mapped_font, fontsize=final_size
                )
            except Exception:
                text_width = len(new_text) * final_size * 0.5

            box_width = rect.width
            if text_width > box_width and box_width > 0:
                scale = box_width / text_width
                final_size = max(final_size * scale, 5)

        insert_point = fitz.Point(rect.x0, rect.y1 - (rect.height * 0.2))

        page.insert_text(
            insert_point,
            new_text,
            fontsize=final_size,
            fontname=mapped_font,
            color=color_rgb,
            render_mode=0,
        )

    return len(rects)


def _search_flexible(page, target_text):
    candidates = []
    seen = set()

    def add(v):
        if v and v not in seen:
            seen.add(v)
            candidates.append(v)

    add(target_text)
    add(target_text.strip())
    add(target_text.replace(" ", ""))
    add(target_text.replace(" ", "\u00a0"))
    add(target_text.replace("\u00a0", " "))

    m = re.match(r"^(.*?\d)(\s*)([%°$€£¥#@&])(.*)$", target_text)
    if m:
        before, _, symbol, after = m.groups()
        add(f"{before} {symbol}{after}")
        add(f"{before}\u00a0{symbol}{after}")

    for candidate in candidates:
        rects = page.search_for(candidate)
        if rects:
            return rects, candidate

    return [], None

def _diagnose_not_found(input_pdf, target_text):
    doc = fitz.open(input_pdf)
    print("\nSearching string")

    tokens = re.findall(r"\d+|\D+", target_text)
    tokens = [t for t in tokens if t.strip()]

    any_partial_found = False
    for token in tokens:
        found_on = []
        for i, page in enumerate(doc):
            if page.search_for(token):
                found_on.append(i + 1)
        if found_on:
            any_partial_found = True
            print(f'"{token}" were found on {found_on}')
        else:
            print(f'"{token}" wasn\'t found')

    doc.close()

    if any_partial_found:
        print("Text are found partially")
    else:
        print("No partial text are found.")


def replace_text_in_pdf(input_path, output_path, old_text, new_text,
                         case_sensitive=True, shrink_to_fit=True, occurrence_indices=None):
    doc = fitz.open(input_path)
    total_replaced = 0
    global_idx = 0

    for page in doc:
        rects, matched_variant = _search_flexible(page, old_text)
        if not rects:
            continue

        selected_rects = []
        for rect in rects:
            global_idx += 1
            if occurrence_indices is None or global_idx in occurrence_indices:
                selected_rects.append(rect)

        total_replaced += _replace_rects_on_page(page, selected_rects, new_text, shrink_to_fit)

    final_output_path = _save_pdf_safely(doc, output_path)
    doc.close()

    print("Done.")
    print("File Saved")

    return final_output_path, total_replaced


def replace_at_position(input_path, output_path, page_index, rect, new_text, shrink_to_fit=True):
    doc = fitz.open(input_path)
    page = doc[page_index]
    count = _replace_rects_on_page(page, [fitz.Rect(rect)], new_text, shrink_to_fit)

    final_output_path = _save_pdf_safely(doc, output_path)
    doc.close()

    print("Done.")
    print("File Saved")

    return final_output_path, count

def _list_occurrences(pdf_path, target_text):
    doc = fitz.open(pdf_path)
    occurrences = []
    idx = 0
    matched_variant = None
    for page_index, page in enumerate(doc):
        rects, variant = _search_flexible(page, target_text)
        if rects:
            matched_variant = variant
            for rect in rects:
                idx += 1
                occurrences.append({"index": idx, "page": page_index + 1, "rect": rect})
    doc.close()
    return occurrences, matched_variant


_NUMBER_TOKEN_RE = re.compile(r"^[\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?$|^\d+(?:[.,]\d+)?$")


def find_number_between_words(pdf_path, before_word, stop_symbol="%", y_tolerance=3):
    doc = fitz.open(pdf_path)
    result = None

    try:
        for page_index, page in enumerate(doc):
            words = page.get_text("words")

            before_candidates = [w for w in words if w[4].strip().lower() == before_word.strip().lower()]
            for tolerance in (y_tolerance, y_tolerance * 2, y_tolerance * 4, max(y_tolerance * 6, 20)):
                for bw in before_candidates:
                    bx1 = bw[2]
                    y_center = (bw[1] + bw[3]) / 2

                    same_line = [
                        w for w in words
                        if w is not bw
                        and abs(((w[1] + w[3]) / 2) - y_center) <= tolerance
                        and w[0] >= bx1 - 1
                    ]
                    same_line.sort(key=lambda w: w[0])

                    candidate = None
                    found_symbol_after = False
                    for w in same_line:
                        text = w[4].strip()
                        if candidate is None:
                            if _NUMBER_TOKEN_RE.match(text):
                                candidate = w
                            continue
                        if stop_symbol in text:
                            found_symbol_after = True
                            break

                    if candidate and found_symbol_after:
                        rect = fitz.Rect(candidate[0], candidate[1], candidate[2], candidate[3])
                        result = {
                            "page_index": page_index,
                            "rect": rect,
                            "raw_text": candidate[4].strip(),
                        }
                        break

                if result:
                    break

            if result:
                break
    finally:
        doc.close()

    return result


def extract_number_by_label(pdf_path, label, value_type=float, occurrence="first", page_number=None, return_raw=False):
    doc = fitz.open(pdf_path)
    pattern = re.compile(
        re.escape(label) + r"\s*:?\s*([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)",
        re.IGNORECASE,
    )

    results = []
    pages = doc if page_number is None else [doc[page_number]]

    for page in pages:
        text = page.get_text()
        for match in pattern.finditer(text):
            raw_str = match.group(1)
            parsed = _parse_number_string(raw_str, value_type)
            if parsed is not None:
                results.append((raw_str, parsed) if return_raw else parsed)

    doc.close()

    if not results:
        return [] if occurrence == "all" else None
    if occurrence == "all":
        return results
    if occurrence == "last":
        return results[-1]
    return results[0]


def get_number_data(file_name, label):
    return extract_number_by_label(file_name, label, value_type=float)


def get_number_data_raw(file_name, label):
    return extract_number_by_label(file_name, label, value_type=float, return_raw=True)


def _detect_number_format(raw):
    raw = raw.strip()
    has_dot = "." in raw
    has_comma = "," in raw

    if has_dot and has_comma:
        last_dot = raw.rfind(".")
        last_comma = raw.rfind(",")
        if last_dot > last_comma:
            thousands_sep, decimal_sep = ",", "."
        else:
            thousands_sep, decimal_sep = ".", ","
    elif has_comma:
        comma_count = raw.count(",")
        after_last = raw.split(",")[-1]
        if comma_count > 1 or len(after_last) == 3:
            thousands_sep, decimal_sep = ",", None
        else:
            thousands_sep, decimal_sep = None, ","
    elif has_dot:
        dot_count = raw.count(".")
        after_last = raw.split(".")[-1]
        if dot_count > 1 or len(after_last) == 3:
            thousands_sep, decimal_sep = ".", None
        else:
            thousands_sep, decimal_sep = None, "."
    else:
        thousands_sep, decimal_sep = None, None

    decimals = len(raw.split(decimal_sep)[-1]) if decimal_sep and decimal_sep in raw else 0

    return {
        "thousands_sep": thousands_sep,
        "decimal_sep": decimal_sep,
        "decimals": decimals,
    }


def _parse_number_string(raw, value_type=float):
    raw = raw.strip()
    fmt = _detect_number_format(raw)

    cleaned = raw
    if fmt["thousands_sep"]:
        cleaned = cleaned.replace(fmt["thousands_sep"], "")
    if fmt["decimal_sep"] and fmt["decimal_sep"] != ".":
        cleaned = cleaned.replace(fmt["decimal_sep"], ".")

    try:
        value = float(cleaned)
    except ValueError:
        return None

    if value_type is int:
        return int(round(value))
    return value


def _format_number_like(raw_original, new_value):
    fmt = _detect_number_format(raw_original)
    base = f"{new_value:,.{fmt['decimals']}f}"

    if fmt["thousands_sep"] == "." and fmt["decimal_sep"] == ",":
        base = base.replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
    elif fmt["thousands_sep"] is None:
        base = base.replace(",", "")

    return base


def _save_pdf_safely(doc, output_path):
    try:
        doc.save(output_path, garbage=4, deflate=True)
        return output_path
    except Exception as e:
        print("\nFailed to save file")

        base, ext = os.path.splitext(output_path)
        for i in range(1, 6):
            alt_path = f"{base}_{i}{ext}"
            try:
                doc.save(alt_path, garbage=4, deflate=True)
                print("\nFile successfully saved")
                return alt_path
            except Exception:
                continue

        raise
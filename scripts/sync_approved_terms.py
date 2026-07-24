#!/usr/bin/env python3
"""
Fetch the live SEA-PHAGES FUNCTIONAL ASSIGNMENTS sheet and turn it into a
normalized, one-row-per-approved-term table.

The published sheet gives us two things by plain HTTP GET, no auth required:
  - a CSV export: cell values for all six columns (USE, Notes, Example gene,
    Publications, Case studies, Do NOT use)
  - a PDF export: the same content, but with font/size/color preserved, which
    is the only way to tell "SEA category header" / "sub-category header" /
    "instructional note" / "approved term" apart. The CSV alone can't do this
    because everything is flattened to plain rows.

Column A in the PDF uses a small, consistent set of styles:
  - bold, size ~3.6, blue   -> top-level SEA category
  - bold, size ~2.6, orange -> sub-category that further narrows a category,
                               applicable regardless of phage morphotype
                               ("Replication Initiation and Elongation")
  - bold, size ~3.1, blue   -> sub-category that's morphotype-specific;
                               a student should pick terms from only the ONE
                               matching their phage's morphotype
                               ("Siphovirus/Myovirus/Podovirus Tail Structures")
  - italic                  -> instructional note, not an approved term
  - plain weight            -> an actual approved term

The sheet is hand-edited by non-programmers and its formatting conventions
could drift at any time. Rather than guess when a style doesn't match one of
the patterns above, this script raises FormatDriftError so a human notices
and updates the parser, instead of silently mis-filing something.
"""
import argparse
import csv
import re
import sys
import urllib.request
from pathlib import Path

import fitz  # PyMuPDF

PUBLISH_BASE = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vToasuRfxx_yfLa9ECFN4_6okwNI_5AJGWZ3NCy53Gz0QfoNrhAQ48HnBuSD1hsrY0zUTTn6EP3MGK_"
)
GID = "0"

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
OUT_PATH = REPO_ROOT / "data" / "approved_terms.csv"

COL_A_X0 = 51.0  # left edge (points) of column A in the PDF export layout
X0_TOLERANCE = 3.0

SHEET_HEADER_LABELS = {"Function Name", "USE"}

ROW_CATEGORY = "category"
ROW_SUBCATEGORY_REFINEMENT = "subcategory_refinement"
ROW_SUBCATEGORY_MORPHOTYPE = "subcategory_morphotype"
ROW_INSTRUCTION = "instruction"
ROW_TERM = "term"
ROW_SHEET_HEADER = "sheet_header"

OUTPUT_FIELDS = [
    "sea_category",
    "sea_category_notes",
    "sea_subcategory",
    "sea_subcategory_kind",
    "sea_subcategory_notes",
    "preceding_instruction",
    "term",
    "notes",
    "example_gene",
    "publications",
    "case_studies",
    "deprecated_synonyms",
    "source_row",
]


class FormatDriftError(RuntimeError):
    """The sheet's formatting no longer matches the conventions this parser understands."""


def fetch_source(refresh=False):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RAW_DIR / "sheet1.csv"
    pdf_path = RAW_DIR / "sheet1.pdf"
    if refresh or not csv_path.exists():
        urllib.request.urlretrieve(f"{PUBLISH_BASE}/pub?gid={GID}&single=true&output=csv", csv_path)
    if refresh or not pdf_path.exists():
        urllib.request.urlretrieve(f"{PUBLISH_BASE}/pub?gid={GID}&single=true&output=pdf", pdf_path)
    return csv_path, pdf_path


def classify_hue(color_int):
    r, g, b = (color_int >> 16) & 255, (color_int >> 8) & 255, color_int & 255
    if b > 150 and (b - r) > 80:
        return "blue"
    if r > 150 and (r - b) > 80:
        return "orange"
    return "neutral"


def classify_span(font, size, color_int, text):
    if text in SHEET_HEADER_LABELS:
        # The sheet's own column-header cells are always discarded regardless of
        # style, so recognize them by their fixed literal text before applying
        # the stricter style rules below (which are about actual data rows).
        return ROW_SHEET_HEADER

    is_bold = "Bold" in font
    is_italic = "Italic" in font
    hue = classify_hue(color_int)
    size_r = round(size, 1)

    if is_bold and is_italic:
        raise FormatDriftError(f"Column A text is both bold and italic (unrecognized style): {text!r}")

    if is_bold:
        if hue == "blue" and abs(size_r - 3.6) <= 0.3:
            return ROW_CATEGORY
        if hue == "blue" and abs(size_r - 3.1) <= 0.3:
            return ROW_SUBCATEGORY_MORPHOTYPE
        if hue == "orange" and abs(size_r - 2.6) <= 0.3:
            return ROW_SUBCATEGORY_REFINEMENT
        raise FormatDriftError(
            "Bold column A text doesn't match any known header style "
            f"(size={size_r}, color_hue={hue}, font={font!r}): {text!r}"
        )

    if is_italic:
        return ROW_INSTRUCTION

    return ROW_TERM


def extract_pdf_rows(pdf_path):
    """Return an ordered list of (row_type, text) for every non-blank column-A cell."""
    doc = fitz.open(str(pdf_path))
    rows = []
    for page in doc:
        page_spans = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if abs(span["bbox"][0] - COL_A_X0) > X0_TOLERANCE:
                        continue
                    text = span["text"].strip()
                    if not text:
                        continue
                    page_spans.append((span["bbox"][1], span, text))
        page_spans.sort(key=lambda t: t[0])
        for _, span, text in page_spans:
            row_type = classify_span(span["font"], span["size"], span["color"], text)
            if row_type == ROW_SHEET_HEADER:
                continue
            rows.append((row_type, text))
    return rows


def normalize(s):
    return re.sub(r"\s+", " ", s or "").strip()


def load_csv_rows(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = list(csv.reader(f))
    # line 1: "Function Name,<timestamp>,(auto-updated),,," -> sheet metadata, not data
    # line 2: "USE,Notes,Example gene...,Do NOT use"         -> column header, not data
    return reader[2:]


MAX_WRAP_LINES = 5  # bound on how many consecutive PDF spans can be one wrapped cell


def align(pdf_rows, csv_rows, truncation_notes=None):
    """Match each classified PDF column-A entry to its CSV row, in document order.

    Two PDF export quirks complicate a naive 1:1 zip:
      - Google's PDF export clips (rather than wraps) column-A cells that are
        too long to fit the printable column width, so a PDF span can be a
        truncated prefix of the real CSV cell value.
      - Very long cells can also wrap onto a second (or third...) line, which
        PyMuPDF reports as separate spans. Those are re-joined here by
        greedily pulling in the next span(s) only while doing so keeps the
        accumulated text a valid prefix of the current CSV cell -- i.e. the
        merge is justified by matching known ground truth, not by guessing
        from geometry (font sizes/coordinates vary page to page).
    Any accumulation that still doesn't resolve to a prefix match within
    MAX_WRAP_LINES spans is a hard error, not a silent guess.
    """
    results = []
    csv_i = 0
    pdf_i = 0
    while pdf_i < len(pdf_rows):
        row_type, first_text = pdf_rows[pdf_i]
        while csv_i < len(csv_rows) and normalize(csv_rows[csv_i][0]) == "":
            csv_i += 1
        if csv_i >= len(csv_rows):
            raise FormatDriftError(
                f"Ran out of CSV rows while looking for column-A text {first_text!r} "
                f"(row_type={row_type}). The CSV and PDF exports may be out of sync."
            )
        csv_text = normalize(csv_rows[csv_i][0])

        accumulated = normalize(first_text)
        consumed = 1
        while (
            accumulated != csv_text
            and csv_text.startswith(accumulated)
            and consumed < MAX_WRAP_LINES
            and (pdf_i + consumed) < len(pdf_rows)
        ):
            _, next_text = pdf_rows[pdf_i + consumed]
            candidate = normalize(accumulated + " " + next_text)
            if csv_text.startswith(candidate):
                accumulated = candidate
                consumed += 1
            else:
                break

        if accumulated == csv_text:
            pass
        elif csv_text.startswith(accumulated):
            if truncation_notes is not None:
                truncation_notes.append((csv_i + 3, accumulated, csv_text))
        else:
            raise FormatDriftError(
                f"Misalignment at CSV row {csv_i + 3}: PDF says {first_text!r} ({row_type}), "
                f"CSV says {csv_text!r}. The sheet structure may have changed."
            )

        results.append((row_type, csv_rows[csv_i], csv_i + 3))  # +3: 1-indexed, 2 header lines skipped
        csv_i += 1
        pdf_i += consumed

    leftover = [i for i in range(csv_i, len(csv_rows)) if normalize(csv_rows[i][0]) != ""]
    if leftover:
        first = csv_rows[leftover[0]][0]
        raise FormatDriftError(
            f"{len(leftover)} non-blank CSV row(s) were never matched to a PDF column-A entry "
            f"(first at CSV row {leftover[0] + 3}: {first!r})."
        )
    return results


def build_terms_table(aligned_rows):
    terms = []
    ctx_category = None
    ctx_category_notes = ""
    ctx_subcategory = ""
    ctx_subcategory_kind = ""
    ctx_subcategory_notes = ""
    ctx_instruction = ""

    for row_type, csv_row, source_row in aligned_rows:
        col_notes = csv_row[1].strip() if len(csv_row) > 1 else ""

        if row_type == ROW_CATEGORY:
            ctx_category = normalize(csv_row[0])
            ctx_category_notes = col_notes
            ctx_subcategory = ""
            ctx_subcategory_kind = ""
            ctx_subcategory_notes = ""
            ctx_instruction = ""
            continue

        if row_type in (ROW_SUBCATEGORY_REFINEMENT, ROW_SUBCATEGORY_MORPHOTYPE):
            ctx_subcategory = normalize(csv_row[0])
            ctx_subcategory_kind = "refinement" if row_type == ROW_SUBCATEGORY_REFINEMENT else "morphotype"
            ctx_subcategory_notes = col_notes
            ctx_instruction = ""
            continue

        if row_type == ROW_INSTRUCTION:
            ctx_instruction = normalize(csv_row[0])
            continue

        # ROW_TERM
        if ctx_category is None:
            raise FormatDriftError(
                f"Term row at CSV row {source_row} ({csv_row[0]!r}) appears before any category header."
            )
        do_not_use_raw = csv_row[5] if len(csv_row) > 5 else ""
        synonyms = [normalize(s) for s in do_not_use_raw.split(",") if normalize(s)]
        terms.append({
            "sea_category": ctx_category,
            "sea_category_notes": ctx_category_notes,
            "sea_subcategory": ctx_subcategory,
            "sea_subcategory_kind": ctx_subcategory_kind,
            "sea_subcategory_notes": ctx_subcategory_notes,
            "preceding_instruction": ctx_instruction,
            "term": normalize(csv_row[0]),
            "notes": col_notes,
            "example_gene": csv_row[2].strip() if len(csv_row) > 2 else "",
            "publications": csv_row[3].strip() if len(csv_row) > 3 else "",
            "case_studies": csv_row[4].strip() if len(csv_row) > 4 else "",
            "deprecated_synonyms": "|".join(synonyms),
            "source_row": source_row,
        })
    return terms


def write_terms_table(terms, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(terms)


def print_summary(pdf_rows, terms, truncation_notes):
    counts = {}
    for row_type, _ in pdf_rows:
        counts[row_type] = counts.get(row_type, 0) + 1
    print("Row classification counts:")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    print(f"Approved term rows written: {len(terms)}")

    if truncation_notes:
        print(
            f"\nNOTE: {len(truncation_notes)} column-A cell(s) were clipped in the PDF export "
            "(too long for the printable column width). The full text from the CSV was used "
            "in the output; this is just visibility into the mismatch, not an error:"
        )
        for row_num, pdf_text, csv_text in truncation_notes:
            print(f"  - CSV row {row_num}: PDF had {pdf_text!r} -> used {csv_text!r}")

    suspicious = [t for t in terms if len(t["term"].split()) > 8]
    if suspicious:
        print(
            f"\nWARNING: {len(suspicious)} term(s) look unusually long/sentence-like "
            "(possible instructional text that wasn't styled italic, so it wasn't "
            "caught as an instruction row). Please review:"
        )
        for t in suspicious:
            print(f"  - CSV row {t['source_row']}: {t['term']!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh", action="store_true",
        help="Re-download the sheet even if a cached copy exists in data/raw/",
    )
    args = parser.parse_args()

    csv_path, pdf_path = fetch_source(refresh=args.refresh)
    truncation_notes = []

    try:
        pdf_rows = extract_pdf_rows(pdf_path)
        csv_rows = load_csv_rows(csv_path)
        aligned = align(pdf_rows, csv_rows, truncation_notes=truncation_notes)
        terms = build_terms_table(aligned)
    except FormatDriftError as e:
        print(f"FORMAT DRIFT DETECTED — refusing to guess: {e}", file=sys.stderr)
        sys.exit(1)

    write_terms_table(terms, OUT_PATH)
    print(f"Wrote {OUT_PATH}")
    print_summary(pdf_rows, terms, truncation_notes)


if __name__ == "__main__":
    main()

import pytest

import nuqta as nq

# Isolated presentation-form glyphs, as PDF producers emit them.
ALEF, BEH, TEH, REH, GHAIN, QAF, LAM, MEEM = (
    "ﺍ", "ﺏ", "ﺕ", "ﺭ", "ﻍ", "ﻕ", "ﻝ", "ﻡ",
)
LAM_ALEF = "ﻻ"


# ── digits / invisible / keys ──────────────────────────────────────────────────

def test_normalize_digits():
    assert nq.normalize_digits("INV-١٢٣٤") == "INV-1234"
    assert nq.normalize_digits("INV-۱۲۳۴") == "INV-1234"
    assert nq.normalize_digits("١٢٣4٥") == "12345"


def test_strip_invisible_excel_header():
    assert nq.strip_invisible("‏رقم‏") == "رقم"
    assert nq.strip_invisible("﻿foo​") == "foo"


def test_normalize_key_hidden_chars_tatweel_nbsp():
    raw = "‏​رقمـ‍  الفاتورة‏"
    assert nq.normalize_key(raw) == "رقم الفاتورة"


def test_normalize_key_null_markers():
    for v in (None, "", "  ", "NaN", "nat", "None", "null"):
        assert nq.normalize_key(v) == ""


def test_normalize_key_idempotent_and_matches_ascii():
    raw = "  INV-‏١٢٣​ "
    once = nq.normalize_key(raw)
    assert once == nq.normalize_key(once) == "INV-123"
    assert nq.normalize_key("INV-١٢٣") == nq.normalize_key("INV-123")


def test_normalize_key_folds_presentation_forms():
    assert nq.normalize_key(MEEM + QAF + REH) == "مقر"


# ── numbers / booleans ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("١٬٢٥٠٫٥٠", 1250.5),
    ("1,250.50", 1250.5),
    ("(1,250.00)", -1250.0),
    ("-12", -12.0),
    ("1e3", 1000.0),
    (" ١٢٣ ", 123.0),
    (7, 7.0),
])
def test_to_number(raw, expected):
    assert nq.to_number(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "abc", "12a", "1.2.3", True, "()"])
def test_to_number_rejects(raw):
    assert nq.to_number(raw) is None


def test_parse_bool():
    assert nq.parse_bool("نعم") is True
    assert nq.parse_bool("لا") is False
    assert nq.parse_bool(" YES ") is True
    assert nq.parse_bool("maybe") is None


# ── dates / direction ──────────────────────────────────────────────────────────

def test_looks_hijri():
    assert nq.looks_hijri("15/09/1445")
    assert nq.looks_hijri("1445-09-15")
    assert nq.looks_hijri("١٥/٠٩/١٤٤٥")
    assert not nq.looks_hijri("15/09/2024")
    assert not nq.looks_hijri("INV-14450")


def test_text_direction():
    assert nq.text_direction("المبلغ 1250") == "rtl"
    assert nq.text_direction("1250 Total المبلغ") == "ltr"
    assert nq.text_direction("123 ...") == "ltr"


# ── presentation forms ─────────────────────────────────────────────────────────

def test_repair_keeps_digits_in_order():
    # Regression: reversing the whole line turned 1250 into 0521.
    visual = "1250 " + GHAIN + LAM + BEH + MEEM + LAM + ALEF
    assert nq.repair_presentation_forms(visual) == "المبلغ 1250"


def test_repair_keeps_latin_runs_in_order():
    visual = MEEM + TEH + " INV-77 " + MEEM + QAF + REH
    assert nq.repair_presentation_forms(visual) == "رقم INV-77 تم"


def test_repair_lam_alef_ligature_reordered_before_nfkc():
    assert nq.repair_presentation_forms("5 " + LAM_ALEF) == "لا 5"


def test_repair_mirrors_brackets():
    visual = "(1250) " + GHAIN + LAM + BEH + MEEM + LAM + ALEF
    assert nq.repair_presentation_forms(visual) == "المبلغ (1250)"


def test_repair_ltr_line_with_embedded_arabic():
    visual = "Reference: " + MEEM + QAF + REH
    assert nq.repair_presentation_forms(visual) == "Reference: رقم"


def test_repair_base_override_for_mostly_latin_rtl_line():
    visual = "Total Due " + GHAIN + LAM + BEH + MEEM + LAM + ALEF
    assert nq.repair_presentation_forms(visual, base="rtl") == "المبلغ Total Due"


def test_repair_leaves_clean_text_alone():
    text = "المبلغ 1250\nplain line"
    assert nq.repair_presentation_forms(text) == text


def test_repair_multiline_and_bad_base():
    visual = "1 " + MEEM + QAF + REH + "\nok"
    assert nq.repair_presentation_forms(visual) == "رقم 1\nok"
    with pytest.raises(ValueError):
        nq.repair_presentation_forms("x", base="up")


# ── encodings ──────────────────────────────────────────────────────────────────

def test_sniff_encoding():
    arabic = "التاريخ,المبلغ\n2024-01-01,1250\n"
    assert nq.sniff_encoding(arabic.encode("utf-8")) == "utf-8"
    assert nq.sniff_encoding(arabic.encode("utf-8-sig")) == "utf-8-sig"
    assert nq.sniff_encoding(arabic.encode("utf-16")) == "utf-16"
    assert nq.sniff_encoding(arabic.encode("cp1256")) == "cp1256"
    assert nq.sniff_encoding("café,crème\n".encode("cp1252")) == "cp1252"
    # A sample cut mid-character is still UTF-8.
    assert nq.sniff_encoding(arabic.encode("utf-8")[:7]) == "utf-8"

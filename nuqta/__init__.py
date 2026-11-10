"""nuqta — small, dependency-free helpers for Arabic text in real-world data.

Arabic text coming out of spreadsheets, CSV exports and PDFs is rarely clean:
Eastern Arabic digits, invisible bidi marks injected by Excel, legacy
Windows-1256 files, and PDFs that store shaped glyphs in visual order.
Every function here fixes one of those problems and nothing else.
"""
from __future__ import annotations

import re
import unicodedata

__all__ = [
    "normalize_digits",
    "strip_invisible",
    "canonical_spaces",
    "normalize_key",
    "to_number",
    "parse_bool",
    "looks_hijri",
    "text_direction",
    "has_presentation_forms",
    "repair_presentation_forms",
    "sniff_encoding",
]

# ── digits ─────────────────────────────────────────────────────────────────────

_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩"   # Arabic-Indic
    "۰۱۲۳۴۵۶۷۸۹",  # Extended (Persian/Urdu)
    "01234567890123456789",
)


def normalize_digits(text: str) -> str:
    """Map Arabic-Indic and Extended Arabic-Indic digits to ASCII 0-9."""
    return text.translate(_DIGITS)


# ── invisible characters & spaces ──────────────────────────────────────────────

# Zero-width chars, bidi marks/embeddings/isolates, Arabic letter mark, BOM.
_INVISIBLE_RE = re.compile("[؜​-‏‪-‮⁦-⁩﻿]")
_SPACES_RE = re.compile("[   ]")
_TATWEEL = "ـ"


def strip_invisible(text: str) -> str:
    """Remove zero-width and bidi-control characters (RLM, LRM, ALM, ZWSP, BOM...).

    Excel routinely wraps RTL cell values and headers in these, so a header that
    *looks* like "رقم" doesn't equal "رقم".
    """
    return _INVISIBLE_RE.sub("", text)


def canonical_spaces(text: str) -> str:
    """Turn non-breaking / figure / narrow spaces into regular spaces."""
    return _SPACES_RE.sub(" ", text)


_NULL_MARKERS = {"", "nan", "none", "nat", "null"}


def normalize_key(value: object) -> str:
    """Canonical form of a value for joining, matching and de-duplicating.

    NFKC (folds PDF presentation forms back to base letters), ASCII digits,
    no invisible chars, no tatweel, single spaces, trimmed. Null-ish markers
    ("nan", "None", ...) become "". Not lowercased. Idempotent.
    """
    if value is None:
        return ""
    s = str(value)
    if s.strip().lower() in _NULL_MARKERS:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = strip_invisible(normalize_digits(s)).replace(_TATWEEL, "")
    return " ".join(canonical_spaces(s).split())


# ── numbers & booleans ─────────────────────────────────────────────────────────

_ARABIC_DECIMAL = "٫"     # ٫
_ARABIC_THOUSANDS = "٬"   # ٬
_NUMBER_RE = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")


def to_number(value: object) -> float | None:
    """Parse "١٬٢٥٠٫٥٠", "1,250.50", "(1,250.50)" or "-1250.5" into a float.

    Parentheses mean negative (accounting style). Returns None when the value
    isn't a plain number — this never guesses.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = normalize_key(value).replace(_ARABIC_THOUSANDS, "").replace(",", "").replace(_ARABIC_DECIMAL, ".")
    s = s.replace(" ", "")
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    if not _NUMBER_RE.fullmatch(s):
        return None
    n = float(s)
    return -n if negative else n


_TRUE = {"true", "yes", "y", "1", "نعم"}
_FALSE = {"false", "no", "n", "0", "لا"}


def parse_bool(value: object) -> bool | None:
    """Parse English or Arabic yes/no ("نعم" / "لا"). None when it isn't one."""
    s = normalize_key(value).lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    return None


# ── dates ──────────────────────────────────────────────────────────────────────

_HIJRI_RE = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]1[34]\d{2}|1[34]\d{2}[/-]\d{1,2}[/-]\d{1,2})\b"
)


def looks_hijri(value: object) -> bool:
    """True when the value contains a Hijri-looking date (years 1300-1499 AH).

    Detection only: converting needs to know which Hijri calendar the source
    used (Umm al-Qura vs tabular), so that decision is left to the caller.
    """
    return bool(_HIJRI_RE.search(normalize_digits(str(value))))


# ── direction ──────────────────────────────────────────────────────────────────

def text_direction(text: str) -> str:
    """'rtl' or 'ltr' from the first strong character (Unicode bidi rule P2)."""
    for ch in text:
        bidi = unicodedata.bidirectional(ch)
        if bidi in ("R", "AL"):
            return "rtl"
        if bidi == "L":
            return "ltr"
    return "ltr"


# ── PDF presentation forms in visual order ─────────────────────────────────────

_PRESENTATION_RE = re.compile("[ﭐ-﷿ﹰ-﻿]")
_LTR_STRONG = {"L", "EN", "AN"}
_RTL_STRONG = {"R", "AL"}
_NEUTRAL = {"ES", "ET", "CS", "WS", "ON", "NSM"}
_MIRROR = str.maketrans("()[]{}<>«»", ")(][}{><»«")


def has_presentation_forms(text: str) -> bool:
    """True when the text contains Arabic presentation-form glyphs (U+FB50–U+FEFF)."""
    return bool(_PRESENTATION_RE.search(text.replace("﻿", "")))


def _runs(line: str, strong: set[str]):
    """(start, end) spans of `strong` chars plus the neutrals *between* them.

    Neutrals at a run's edges are left out: they take the paragraph direction.
    """
    kinds = [unicodedata.bidirectional(c) for c in line]
    i, n = 0, len(line)
    while i < n:
        if kinds[i] not in strong:
            i += 1
            continue
        start = last_strong = i
        j = i + 1
        while j < n and (kinds[j] in strong or kinds[j] in _NEUTRAL):
            if kinds[j] in strong:
                last_strong = j
            j += 1
        yield start, last_strong + 1
        i = last_strong + 1


def _reverse_runs(line: str, strong: set[str]) -> str:
    """Reverse (and bracket-mirror) each run of `strong` chars in place."""
    chars = list(line)
    for start, end in _runs(line, strong):
        chars[start:end] = line[start:end][::-1].translate(_MIRROR)
    return "".join(chars)


def _repair_line(line: str, base: str) -> str:
    if not has_presentation_forms(line):
        return line
    if base == "auto":
        # ponytail: majority-of-strong-chars guess; wrong for RTL lines that are
        # mostly Latin ("المبلغ Total Due"). Callers who know the layout pass base=.
        rtl = sum(unicodedata.bidirectional(c) in _RTL_STRONG for c in line)
        ltr = sum(unicodedata.bidirectional(c) == "L" for c in line)
        base = "rtl" if rtl >= ltr else "ltr"
    if base == "rtl":
        # RTL paragraph stored left-to-right: flip the whole line, then put each
        # LTR run (numbers, Latin words) back in its own order.
        line = _reverse_runs(line[::-1].translate(_MIRROR), _LTR_STRONG)
    else:
        # LTR paragraph with embedded Arabic: only the Arabic runs are reversed.
        line = _reverse_runs(line, _RTL_STRONG)
    # NFKC *after* reordering: a lam-alef ligature is one glyph in visual order
    # but two letters in logical order.
    return unicodedata.normalize("NFKC", line)


def repair_presentation_forms(text: str, base: str = "auto") -> str:
    """Fix Arabic extracted from PDFs that store shaped glyphs in visual order.

    Some PDF producers write Arabic as presentation-form glyphs laid out
    left-to-right, so naive extraction gives reversed, shaped text:
    "1250 ﻎﻠﺒﻤﻟﺍ" instead of "المبلغ 1250". This restores logical order and
    base letters, keeping numbers and Latin text in their original direction.
    Brackets in reversed segments are mirrored, since visual-order producers
    store the glyph as displayed. Lines without presentation forms are
    returned unchanged.

    base: paragraph direction of each line: "auto" (guess), "rtl" or "ltr".
    """
    if base not in ("auto", "rtl", "ltr"):
        raise ValueError(f"base must be 'auto', 'rtl' or 'ltr', got {base!r}")
    return "\n".join(_repair_line(line, base) for line in text.split("\n"))


# ── encodings ──────────────────────────────────────────────────────────────────

def sniff_encoding(raw: bytes) -> str:
    """Best-guess text encoding for CSV/TXT bytes, tuned for Arabic sources.

    Order: BOMs (UTF-8, UTF-16) → strict UTF-8 → Windows-1256 if the non-ASCII
    text decodes to mostly Arabic letters → Windows-1252 → Latin-1.
    Pass a sample (the first ~1 MB is plenty).
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError as exc:
        # A multi-byte char cut off at the end of a sample is still UTF-8.
        if exc.start >= len(raw) - 3 and exc.reason == "unexpected end of data":
            return "utf-8"
    non_ascii = [c for c in raw.decode("cp1256", errors="replace") if ord(c) > 127]
    if non_ascii and sum("؀" <= c <= "ۿ" for c in non_ascii) / len(non_ascii) >= 0.6:
        return "cp1256"
    try:
        raw.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return "latin-1"

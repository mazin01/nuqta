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
    "visual_to_logical",
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


# ── visual → logical order ─────────────────────────────────────────────────────
#
# PDF text extractors order characters by x position, so every Arabic line comes
# out in *visual* order. Visual order is what the Unicode Bidirectional Algorithm
# (UBA) produces from logical order; we undo it. The inverse isn't unique, so we
# re-apply the UBA rules that decide what gets reversed:
#   W2  a number after an Arabic letter becomes an "Arabic number": "-" no longer
#       holds it together, so 2025-03-14 displays as 14-03-2025
#   W4  a single "," "." "-" between digits keeps a number together
#   W5  "%", "$", "#" stick to the number next to them
#   W7  a number after a Latin letter joins the Latin run ("ORD-1000", "A4")
#   N0  a bracket pair takes the direction of what's inside it
# Tested by round-tripping through a reference UBA implementation (python-bidi).

_PRESENTATION_RE = re.compile("[ﭐ-﷿ﹰ-﻿]")
_MIRROR = str.maketrans("()[]{}<>«»", ")(][}{><»«")
_PAIRS = {"(": ")", "[": "]", "{": "}", "<": ">", "«": "»"}
_PAIRS.update({v: k for k, v in _PAIRS.items()})


def _kinds(s: str) -> list[str]:
    """Bidi class per char, collapsed: R (incl. AL), L, EN, AN, J (number joiner), N (neutral)."""
    out = []
    for c in s:
        k = unicodedata.bidirectional(c)
        if k == "AL":
            k = "R"
        elif k in ("CS", "ES", "ET"):
            k = "J"
        elif k not in ("R", "L", "EN", "AN"):
            k = "N"
        out.append(k)
    return out


def _arabic_letter_right_of(s: str, i: int) -> bool:
    """Is the nearest strong char right of index i an Arabic letter? (W2 in RTL lines)."""
    for c in s[i:]:
        k = unicodedata.bidirectional(c)
        if k in ("L", "R", "AL"):
            return k == "AL"
    return False


def _ltr_runs_in_rtl(s: str) -> list[tuple[int, int]]:
    """Spans that stay left-to-right inside an RTL line (Latin words, numbers)."""
    k, n, runs, i = _kinds(s), len(s), [], 0
    while i < n:
        if k[i] not in ("L", "EN", "AN"):
            i += 1
            continue
        start, end, has_latin = i, i + 1, k[i] == "L"
        j = end
        while j < n:
            if k[j] in ("L", "EN", "AN"):
                has_latin |= k[j] == "L"
                end = j = j + 1
                continue
            g = j
            while g < n and k[g] in ("J", "N"):
                g += 1
            if g == n:
                break
            gap, nxt = s[j:g], k[g]
            if has_latin and nxt in ("L", "EN"):                       # W7 + N1
                joins = True
            elif len(gap) == 1 and k[j] == "J" and k[end - 1] == nxt:  # W4
                cs = unicodedata.bidirectional(gap) == "CS"
                joins = cs or (nxt == "EN" and not _arabic_letter_right_of(s, g))
            else:
                joins = False
            if not joins:
                break
            end = j = g
        # W5: currency/percent signs attach to a European number, but not to one
        # that W2 already turned into an Arabic number.
        if not has_latin and not _arabic_letter_right_of(s, end):
            while start > 0 and unicodedata.bidirectional(s[start - 1]) == "ET" and k[start] == "EN":
                start -= 1
            while end < n and unicodedata.bidirectional(s[end]) == "ET" and k[end - 1] == "EN":
                end += 1
        runs.append((start, end))
        i = end
    return runs


def _number_runs(s: str) -> list[tuple[int, int]]:
    """Numbers inside an Arabic span: digits joined only by "," "." ":" "/" (W2 + W4)."""
    k, n, runs, i = _kinds(s), len(s), [], 0
    while i < n:
        if k[i] not in ("EN", "AN"):
            i += 1
            continue
        j = i + 1
        while j < n and (k[j] in ("EN", "AN") or (
                unicodedata.bidirectional(s[j]) == "CS" and j + 1 < n and k[j + 1] in ("EN", "AN"))):
            j += 1
        runs.append((i, j))
        i = j
    return runs


def _rtl_spans_in_ltr(s: str) -> list[tuple[int, int]]:
    """Spans of an LTR line that were displayed right-to-left (Arabic + its numbers)."""
    k, n, spans, i = _kinds(s), len(s), [], 0
    while i < n:
        if k[i] == "L":
            i += 1
            continue
        seg_end = i
        while seg_end < n and k[seg_end] != "L":
            seg_end += 1
        if any(k[p] == "R" for p in range(i, seg_end)):
            # Visual left edge is the logical end: numbers there followed the Arabic
            # (W2). On the right edge only Arabic digits belong to the span.
            start = next(p for p in range(i, seg_end) if k[p] in ("R", "EN", "AN"))
            end = max(p for p in range(i, seg_end) if k[p] in ("R", "AN")) + 1
            while True:  # N0: pull in a bracket whose partner is inside the span
                inner = s[start:end]
                left, right = s[start - 1] if start > i else "", s[end] if end < seg_end else ""
                if left in _PAIRS and inner.count(_PAIRS[left]) > inner.count(left):
                    start -= 1
                elif right in _PAIRS and inner.count(_PAIRS[right]) > inner.count(right):
                    end += 1
                else:
                    break
            spans.append((start, end))
        i = seg_end
    return spans


def _reverse_keeping(s: str, keep: list[tuple[int, int]]) -> str:
    """Reverse s (mirroring brackets) but leave the `keep` spans' insides as they are."""
    parts, pos = [], 0
    for a, b in keep:
        parts.append(s[pos:a][::-1].translate(_MIRROR))
        parts.append(s[a:b])
        pos = b
    parts.append(s[pos:][::-1].translate(_MIRROR))
    return "".join(reversed(parts))


def _guess_base(line: str) -> str:
    # ponytail: majority-of-strong-chars guess; wrong for RTL lines that are
    # mostly Latin ("المبلغ Total Due"). Callers who know the layout pass base=.
    rtl = sum(unicodedata.bidirectional(c) in ("R", "AL") for c in line)
    ltr = sum(unicodedata.bidirectional(c) == "L" for c in line)
    return "rtl" if rtl >= ltr else "ltr"


def _visual_to_logical_line(line: str, base: str) -> str:
    if not any(unicodedata.bidirectional(c) in ("R", "AL") for c in line):
        return line
    if base == "auto":
        base = _guess_base(line)
    if base == "rtl":
        return _reverse_keeping(line, _ltr_runs_in_rtl(line))
    out, pos = [], 0
    for a, b in _rtl_spans_in_ltr(line):
        span = line[a:b]
        out += [line[pos:a], _reverse_keeping(span, _number_runs(span))]
        pos = b
    return "".join(out) + line[pos:]


def _check_base(base: str) -> None:
    if base not in ("auto", "rtl", "ltr"):
        raise ValueError(f"base must be 'auto', 'rtl' or 'ltr', got {base!r}")


def visual_to_logical(text: str, base: str = "auto") -> str:
    """Turn visually ordered text (as PDF extractors return it) back into logical order.

    "1250 غلبملا" → "المبلغ 1250". Numbers and Latin words keep their own order,
    brackets are mirrored back, and lines with no Arabic/Hebrew are untouched.

    base: paragraph direction of each line: "auto" (majority guess), "rtl" or
    "ltr". Pass it when you know the document's direction; the guess is per line.
    """
    _check_base(base)
    return "\n".join(_visual_to_logical_line(line, base) for line in text.split("\n"))


def has_presentation_forms(text: str) -> bool:
    """True when the text contains Arabic presentation-form glyphs (U+FB50–U+FEFF)."""
    return bool(_PRESENTATION_RE.search(text.replace("﻿", "")))


def repair_presentation_forms(text: str, base: str = "auto") -> str:
    """Fix lines made of shaped Arabic glyphs in visual order (older PDF producers).

    "1250 ﻎﻠﺒﻤﻟﺍ" → "المبلغ 1250": `visual_to_logical`, then NFKC to turn the
    glyphs back into letters. NFKC runs *after* reordering because a lam-alef
    ligature is one glyph in visual order but two letters in logical order.
    Lines without presentation forms are returned unchanged.
    """
    _check_base(base)
    return "\n".join(
        unicodedata.normalize("NFKC", _visual_to_logical_line(line, base)) if has_presentation_forms(line) else line
        for line in text.split("\n")
    )


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

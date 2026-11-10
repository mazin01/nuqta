# nuqta

**Small, dependency-free fixes for messy Arabic text in real-world data.**

Arabic text that comes out of spreadsheets, CSV exports and PDFs looks fine on screen but breaks code:

| What you get | Why | Fix |
|---|---|---|
| `"INV-١٢٣"` ≠ `"INV-123"` | Eastern Arabic digits | `normalize_digits` |
| header `"رقم"` not found | Excel wrapped it in invisible RLM marks | `strip_invisible`, `normalize_key` |
| `float("١٬٢٥٠٫٥٠")` crashes | Arabic decimal/thousands separators | `to_number` |
| `"ﻎﻠﺒﻤﻟﺍ 1250"` from a PDF | shaped glyphs stored in visual order | `repair_presentation_forms` |
| mojibake when reading a CSV | legacy Windows-1256 export | `sniff_encoding` |
| `"15/09/1445"` parsed as year 1445 | Hijri dates | `looks_hijri` |

One module, standard library only, Python 3.10+.

## Install

```bash
pip install git+https://github.com/<you>/nuqta
```

## Usage

```python
import nuqta as nq

nq.normalize_digits("INV-١٢٣٤")             # 'INV-1234'
nq.normalize_key("‏رقمـ  الفاتورة") # 'رقم الفاتورة'  (join/match-safe)
nq.to_number("١٬٢٥٠٫٥٠")                    # 1250.5
nq.to_number("(1,250.00)")                  # -1250.0  (accounting negative)
nq.parse_bool("نعم")                         # True
nq.looks_hijri("١٥/٠٩/١٤٤٥")                 # True
nq.text_direction("المبلغ 1250")             # 'rtl'

# Text extracted from a PDF that stores Arabic in visual order:
nq.repair_presentation_forms("1250 ﻎﻠﺒﻤﻟﺍ")   # 'المبلغ 1250'

raw = open("export.csv", "rb").read(1_000_000)
open("export.csv", encoding=nq.sniff_encoding(raw))  # 'cp1256' for old Arabic Windows exports
```

## API

| Function | Does |
|---|---|
| `normalize_digits(text)` | Arabic-Indic (`٠-٩`) and Persian/Urdu (`۰-۹`) digits → `0-9` |
| `strip_invisible(text)` | Removes ZWSP/ZWJ/ZWNJ, LRM/RLM/ALM, bidi embeddings and isolates, BOM |
| `canonical_spaces(text)` | NBSP, figure and narrow spaces → regular space |
| `normalize_key(value)` | NFKC, ASCII digits, no invisibles or tatweel, collapsed whitespace; `"nan"`/`"None"`/`None` → `""`. Idempotent. For joins, matching and dedupe. |
| `to_number(value)` | Parses Arabic or Latin digits and separators and `(1,250)` negatives; `None` instead of guessing |
| `parse_bool(value)` | `true/false/yes/no/1/0` and `نعم/لا` → `bool`, else `None` |
| `looks_hijri(value)` | Detects Hijri-looking dates (AH years 1300–1499). Detection only: converting depends on which Hijri calendar the source used. |
| `text_direction(text)` | `'rtl'`/`'ltr'` from the first strong character (Unicode bidi rule P2) |
| `has_presentation_forms(text)` | Contains Arabic presentation-form glyphs (U+FB50–U+FEFF) |
| `repair_presentation_forms(text, base="auto")` | Restores logical order and base letters. Numbers and Latin runs keep their order, brackets are mirrored, and lam-alef ligatures are handled. `base="rtl"\|"ltr"` overrides the per-line direction guess. |
| `sniff_encoding(raw_bytes)` | BOM → UTF-8 → Windows-1256 (if the non-ASCII text is mostly Arabic) → Windows-1252 → Latin-1 |

### How `repair_presentation_forms` works

Some PDF producers write Arabic as already-shaped glyphs laid out left-to-right, so a text extractor returns each line reversed. Reversing the whole line back is the common fix, and it's wrong: numbers and Latin words get reversed too (`1250` → `0521`). nuqta does this instead:

1. It guesses the line's base direction by counting strong RTL and LTR characters, or uses `base=` if you pass it.
2. For an RTL line, it flips the whole line and then flips each LTR run back. A run is strong LTR characters plus the neutrals between them, so `INV-77` and `Total Due` survive intact.
3. For an LTR line, it reverses only the Arabic runs.
4. It applies NFKC *after* reordering, because a lam-alef ligature is one glyph in visual order but two letters in logical order.

Limits: the direction guess is a heuristic, and a mostly-Latin RTL line needs `base="rtl"`. Harakat (diacritics) in visual-order text aren't tested.

## Use cases

- Cleaning join keys before matching records across systems: invoice numbers, IDs, names.
- Reading Arabic CSV/Excel exports from accounting and ERP systems, banks, and government portals.
- Pre-processing text pulled from Arabic PDFs before it goes into search, an LLM, or a database.
- Picking `dir="rtl"` for user-generated text in a UI or a generated report.

## Development

```bash
pip install -e ".[test]"
pytest
```

## License

MIT

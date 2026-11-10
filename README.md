# nuqta

**Small, dependency-free fixes for messy Arabic text in real-world data.**

Arabic text that comes out of spreadsheets, CSV exports and PDFs looks fine on screen but breaks code:

| What you get | Why | Fix |
|---|---|---|
| `"INV-١٢٣"` ≠ `"INV-123"` | Eastern Arabic digits | `normalize_digits` |
| header `"رقم"` not found | Excel wrapped it in invisible RLM marks | `strip_invisible`, `normalize_key` |
| `float("١٬٢٥٠٫٥٠")` crashes | Arabic decimal/thousands separators | `to_number` |
| `"غلبملا 1250"` from a PDF | extractors return characters in visual order | `visual_to_logical` |
| `"ﻎﻠﺒﻤﻟﺍ 1250"` from an older PDF | shaped glyphs, also in visual order | `repair_presentation_forms` |
| mojibake when reading a CSV | legacy Windows-1256 export | `sniff_encoding` |
| `"15/09/1445"` parsed as year 1445 | Hijri dates | `looks_hijri` |

One module, standard library only, Python 3.10+.

## Install

```bash
pip install git+https://github.com/mazin01/nuqta
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

# Text from a PDF extractor (pdfplumber, pdfminer...) comes out in visual order:
nq.visual_to_logical("1250 غلبملا", base="rtl")                     # 'المبلغ 1250'
nq.visual_to_logical("Date / (١٤٤٦ ناضمر ١٣) 14-03-2025 :خيراتلا", base="ltr")
# 'Date / التاريخ: 2025-03-14 (١٣ رمضان ١٤٤٦)'

# Older PDFs store pre-shaped glyphs; this reorders *and* turns them back into letters:
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
| `visual_to_logical(text, base="auto")` | Visual → logical order, line by line, following the Unicode Bidirectional Algorithm's rules for numbers, Latin runs and brackets. `base="rtl"\|"ltr"` sets the paragraph direction; `"auto"` guesses per line. |
| `has_presentation_forms(text)` | Contains Arabic presentation-form glyphs (U+FB50–U+FEFF) |
| `repair_presentation_forms(text, base="auto")` | For lines made of presentation-form glyphs: `visual_to_logical` + NFKC (after reordering, so lam-alef ligatures come out right) |
| `sniff_encoding(raw_bytes)` | BOM → UTF-8 → Windows-1256 (if the non-ASCII text is mostly Arabic) → Windows-1252 → Latin-1 |

### How `visual_to_logical` works

PDF extractors order characters by x position, so Arabic comes out in *visual* order: the order produced by the Unicode Bidirectional Algorithm (UBA) when it lays logical text out for display. The usual fix is reversing the whole line, and it's wrong: numbers and Latin words get reversed too (`1250` → `0521`).

nuqta undoes the layout instead. It finds the spans the UBA would have reversed and reverses only those, keeping inner runs in order. The UBA rules that decide those spans are the ones that matter in practice:

- **W2:** a number after an Arabic word becomes an "Arabic number". `-` no longer holds it together, so `2025-03-14` is displayed as `14-03-2025`, and nuqta reads it back correctly.
- **W4/W5:** `1,250.00` stays one number, and `15%` and `$20` stay attached (except after Arabic, per W2).
- **W7:** a number after a Latin letter joins the Latin run, as in `ORD-1000` and `A4`.
- **N0:** bracket pairs follow their content, and brackets in reversed spans are mirrored back, matching what browser-printed PDFs contain.

The tests round-trip realistic AR/EN lines through [python-bidi](https://github.com/MeirKriheli/python-bidi), a full UBA implementation used as the reference: render forward, then `visual_to_logical`, and require the original string back. nuqta itself stays standard-library only.

Limits: the inverse isn't unique. For example, `Total 500 المبلغ` and `Total المبلغ 500` render identically, and nuqta assumes the number belongs to the Arabic. `base="auto"` guesses each line's direction by counting letters, so pass `base=` when you know the document's direction. Explicit bidi control characters and harakat (diacritics) aren't handled.

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

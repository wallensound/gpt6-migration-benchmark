# Case 07: contact normalisation under accumulated rules

## Task

The user message is a short note (ticket, email, chat message, CRM note) that contains one messy contact
record: a block of `Label<sep>value` lines for some of name, phone, email, company and country. The model
returns the normalised record. Only the record lines are a source of values; the notes around them never are.

## Output contract

A single bare JSON object, nothing before or after it (no Markdown fences, no prose), with exactly these five
keys: `name`, `phone`, `email`, `company`, `country`. Every value is a string or `null`. Key order is not scored.

## Rules (the 18 rules)

1. **Output.** Only the JSON object described above.
2. **Missing values.** A field whose line is absent, empty, or a placeholder (`-`, `--`, `n/a`, `na`, `none`,
   `unknown`, `?`, `null`, `TBD`, any case) is `null`. Never guess or infer a value that is not in the record
   (exception: rule 16).
3. **Assign by content, not by label.** A value containing `@` is the email. A value made only of digits, spaces
   and `+ - ( ) . /` (after removing a `tel:` prefix and an extension) with at least 7 digits is the phone. If the
   value under the name label ends in a legal suffix (rule 12) and the value under the company label does not, the
   two are swapped: the first is the company, the second the name. The country is always taken from the country line.
4. **Whitespace.** Trim every value and collapse internal runs of whitespace to one space.
5. **Name order.** `Last, First` becomes `First Last` (split at the first comma).
6. **Honorifics.** Drop leading honorifics: Dr, Mr, Mrs, Ms, Mx, Prof (with or without a dot, any case).
7. **Name casing.** Each space- or hyphen-separated part of the name: first character upper case, the rest lower
   case (`anna-lena BERG` -> `Anna-Lena Berg`).
8. **Unicode.** Keep every letter exactly, including diacritics and non-ASCII letters (`ÅSA KRÖNBERG` -> `Åsa Krönberg`);
   never transliterate. Strings are compared after Unicode NFC normalisation.
9. **Phone format.** E.164: `+`, country calling code, national significant number, digits only, no spaces.
   A leading `tel:` and an extension (`ext. 12`, `ext 12`, `x12`, `#12`, `extension 12`) are dropped from any phone.
10. **International phones.** A number is international if, ignoring a leading `tel:` and an opening parenthesis,
    it starts with `+` or `00`. `00` is replaced by `+`; a `(0)` in an international number is removed; all
    spaces, dashes, dots, slashes and parentheses are removed. The calling code written in the number is kept as is.
11. **National phones.** A number that is not international gets the calling code of the record's country (after
    rule 15); one leading trunk `0` is removed first. If the record has no country, the phone is `null`.
12. **Company.** Remove a trailing legal suffix (with an optional comma before it), matched case-insensitively:
    AB, GmbH, AG, Ltd, Ltd., PLC, Inc, Inc., LLC, Corp, Corp., AS, ASA, Oy, Oyj, A/S, ApS, SA, SAS, B.V., N.V.,
    S.p.A., Sp. z o.o., K.K., Pty Ltd, Ltda.
13. **Company casing.** Each space-separated word of the company: first character upper case, rest lower case.
14. **Email.** Remove a `mailto:` prefix and surrounding `< >`, then lower-case the whole address.
15. **Country.** ISO 3166-1 alpha-2, upper case. The country line may hold the English, Swedish or German name, the
    alpha-2 or alpha-3 code, in any case, or a common alias (UK, Great Britain -> GB; Holland -> NL; USA, U.S.A. ->
    US; Türkiye -> TR; Czech Republic -> CZ).
16. **Country from phone.** If the country is missing but the phone is international (rule 10), the country is the
    one the calling code belongs to. Calling codes shared by several countries (+1, +7) give no country (`null`).
17. **Country/phone disagreement.** If the country line and the phone's calling code disagree, the country comes
    from the country line and the phone keeps its own calling code.
18. **No other sources.** Nothing outside the record lines (notes, signatures, email domains, company suffixes)
    is used to fill or change a field.

**Precedence.** Rules 2 and 16 conflict when the country is missing and the phone is international: rule 16 wins,
so the country is filled from the calling code. In every other case rule 2 holds.

## Reference implementation

`case.py: normalise_record(record_lines)` implements the rules; `label(plan)` is
`normalise_record(plan["record_lines"])`. A test checks, over thousands of seeded plans, that it reproduces the
clean record each plan was built from.

## Data

- A clean record is sampled: person (`harness.entities.people()`), company (`companies("main")`, base name without
  suffix), a real country (16 main countries, weighted towards SE/DE/GB/US), a phone number with a realistic
  national significant number for that country, and an email built from the name and the company domain (20%
  generic mail providers).
- Messy surface forms: name casing, `Last, First`, honorifics, extra spaces; phone in international (`+`, `00`,
  `(0)`, dashes, compact) or national formats (trunk 0, dashes, parentheses, compact); email casing, `mailto:`,
  `< >`; company casing, with or without the legal suffix; country as English, Swedish or German name, alpha-3,
  alpha-2 or alias, in mixed casing. Labels vary (`Tel`, `E-mail`, `Org`, `Land`, ...), separators vary
  (`: `, ` : `, ` = `, tab), and about 30% of records have shuffled line order.
- The generator (gpt-6.2-sol) writes only the notes and places a `<<RECORD>>` line; `make_input` replaces it with
  the exact record lines. `verify` checks the record appears exactly once and the notes contain no `@`, no URLs,
  no number with five or more digits, no country name or alpha-3 code, no surname or company name, and no first
  name when the plan did not allow one.

## Slices

| Slice | What it forces |
| --- | --- |
| plain | ordinary mess only |
| precedence_conflict | country missing (absent or placeholder), phone international, never +1: rules 2 and 16 collide |
| international_phone | `00` prefix, `(0)`, extensions, dots; 30% with a phone from another country than the country line (rule 17) |
| missing_fields | 1–2 of phone/email/company/country missing; when country is missing the phone is missing too |
| unicode_names | non-ASCII first names, hyphenated first names, diacritics in the surname; more upper/lower-case mess |
| swapped_fields | phone/email under each other's label, or name/company swapped (company always has its suffix), or both |

**Shift set:** 12 unseen countries (JP, BR, MX, IN, AU, ZA, GR, TR, NZ, PT, CZ, KR), unseen companies
(`companies("shift")`, any legal suffix from rule 12), and in 60% of items unseen phone formats (`tel:` URIs,
`(+81)`, `00 81`, dots, slashes, `tel:` national numbers).

## Scoring

- `parse`: the whole stripped output must `json.loads` into an object (`strict_json`); otherwise the first `{...}`
  span is salvaged for diagnostics only.
- `valid`: strict JSON object with exactly the five keys and string-or-null values.
- `passed`: valid and every field equal to the expected value (NFC-normalised, otherwise exact; `null` must be
  `null`, not `""`).
- `nonanswer`: refusal, empty output, or no JSON and the text ends with a question mark.
- Secondary: per-item fields correct (out of 5), format-valid fields (phone `^\+[1-9]\d{6,14}$`, country
  `^[A-Z]{2}$`, email without upper case or whitespace, trimmed name and company, or `null`). `aggregate` pools
  field accuracy and format validity over all fields of all rows and reports per-field accuracy and JSON validity.
- Categories: `format`, `nonanswer`, `<field>_wrong`, `invented_value` (non-null where null expected),
  `dropped_value` (null where a value expected).

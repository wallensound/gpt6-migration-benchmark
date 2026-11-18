# Case 02: Invoice fields with a confidence flag

Single source of truth for the labeller, the scorer and the prompts.

## Task

Input: the text of one invoice (plain text, as pasted from a PDF, an e-mail body, a portal export or a
scan). Output: one JSON object with the eight invoice header fields below, plus review flags for fields a
human should check.

## Output contract

A single JSON object, nothing before or after it (no Markdown fences, no prose). It has exactly these eight
keys, each a string or `null`:

| Key | Meaning | Normal form |
| --- | --- | --- |
| `vendor` | The company that issued the invoice (seller, supplier, payee). Never the customer / bill-to party. | The vendor's name as written, including the legal suffix (e.g. `Velmora AB`). |
| `invoice_number` | The invoice's own identifier. Not an order number, PO number or customer number. | Exactly as written, without the label (e.g. `INV-2026-0412`). |
| `issue_date` | The invoice date (date of issue). Not a delivery date or order date. | ISO `YYYY-MM-DD`. |
| `due_date` | The payment due date, only if a date is stated. | ISO `YYYY-MM-DD`. |
| `currency` | The currency the invoice is billed in (the currency of net, VAT and total). | ISO 4217 code: `EUR`, `SEK`, `USD`, `GBP`, `CHF`, `NOK`, `DKK`. |
| `net` | Amount excluding VAT, after any discount (the taxable amount). | Decimal string with a dot and exactly two decimals, no thousands separators, no currency (e.g. `1234.50`). |
| `vat` | The VAT / moms / MwSt / sales-tax amount (not the rate). | Same as `net`. |
| `total` | The gross amount including VAT (the amount payable). | Same as `net`. |

Only under `flag_method: confidence_field` (see below) the object may carry one more key, `confidence`.

### Rules and edge cases

1. **Missing fields are `null`.** A field is `null` when the invoice does not state it. Values are never
   computed or inferred: no due date from payment terms, no net as total minus VAT, no VAT from a rate.
   (The data never contains payment terms in days.)
2. **Dates.** Every written form is converted to ISO: `14.10.2026`, `14/10/2026`, `14/10/26`, `4.3.2026`,
   `14 Oct 2026`, `14-Oct-2026`, `October 14, 2026`, `14th October 2026`, `14 oktober 2026`,
   `14. Oktober 2026`, `2026-10-14`. **Numeric dates are always day-first** (European), also when the day
   is 12 or less (`03/04/2026` is 3 April 2026). Two-digit years are 20YY.
3. **Amounts.** Written forms `1,234.50`, `1234.50`, `1.234,50`, `1 234,50`, `1234,50` all become `1234.50`.
   In the data every amount is written with exactly two decimals, so a comma or dot followed by two digits at
   the end is the decimal separator.
4. **Subtotal versus net.** When a subtotal is followed by a discount, `net` is the amount after the
   discount (the amount VAT is charged on), not the subtotal. Line-item amounts are never `net` unless the
   invoice labels them so.
5. **Currency.** Symbols map as `€` = EUR, `£` = GBP, `$` = USD, `kr` = SEK. When an invoice also shows an
   amount converted into another currency "for information", `currency` is still the billing currency and
   the converted amount is ignored.
6. **Vendor.** The issuer, never the customer. The data always writes the vendor's full legal name.
7. **Languages.** Labels may be English, Swedish or German, e.g. Fakturanummer, Fakturadatum,
   Förfallodatum, Moms, Att betala; Rechnungsnummer, Rechnungsdatum, Fällig am / Zahlbar bis, Nettobetrag,
   MwSt., Gesamtbetrag.
8. **Scanned-style noise** (shift set): broken lines and OCR typos in labels and prose. Value strings are
   never corrupted.

## Scoring

Normalisation, exactly and only this:

- `vendor`: case-insensitive, runs of whitespace collapsed, leading/trailing whitespace and a trailing `.`
  ignored. Must equal the full legal name.
- `invoice_number`: case-insensitive after stripping leading/trailing whitespace.
- `issue_date`, `due_date`: must be exactly `YYYY-MM-DD` and equal.
- `currency`: case-insensitive after stripping whitespace.
- `net`, `vat`, `total`: a JSON number, or a string matching `^-?\d+(\.\d{1,2})?$`; compared as decimals
  (`1234.5` equals `1234.50`). Strings with separators, spaces or currency (`1,234.50`, `EUR 12.00`) are
  wrong.
- Expected `null` requires `null` (an empty string is wrong); expected value with `null` is wrong.

`valid` means the output is exactly one JSON object with the eight keys (plus `confidence` only under the
confidence-field method), each value a string, number or `null`. Fenced or wrapped JSON, prose, extra or
missing keys are invalid (category `format`). Empty output, refusals and clarifying questions are
`nonanswer`.

**Pass** = valid and all eight fields correct. Flags never affect pass.

Secondary scores: field accuracy (correct fields / 8, pooled over items; invalid outputs count as eight
wrong fields), and review-flag precision and recall against the fields that are actually wrong, pooled over
valid outputs (an invalid output would go to review as a whole, so it is excluded from flag metrics).

## Review flags (`settings.flag_method`)

The output contract above stays the same under every method; only how flags are derived differs.

- `logprob` (legacy): Chat Completions with `logprobs: true`. A field is flagged when the mean token
  log-probability of the tokens of its value (the characters inside the quotes, or `null`) is below
  `settings.flag_threshold`. The threshold is tuned on train during calibration.
- `none`: no flags.
- `null_when_unsure`: the prompt tells the model to return `null` for unsure fields; every `null` field is
  flagged.
- `confidence_field`: the object carries `confidence`, an object with the eight keys, each `"high"` or
  `"low"`; `low` fields are flagged. A missing or malformed `confidence` gives no flags (still valid).
- `two_run_agreement`: the model is called twice (`samples: 2`); the fields come from the first run, and a
  field is flagged when the two runs disagree after normalisation (all fields if the second run is invalid).

# Case 03 — Ticket routing at no reasoning (spec, dataset v1)

Single source of truth for the labeller, the scorer and the legacy prompt.

## Task

Route one customer message, sent to a company's support desk, to exactly one of 12 labels and output the
label only.

## Labels

| Label | Meaning |
| --- | --- |
| `billing` | charges, payments, invoices, receipts, prices, payment methods, refunds of charges |
| `technical` | help setting up, connecting, configuring or using the product, app or website, when nothing is reported broken |
| `account_access` | logging in, passwords, two-factor codes, locked or blocked accounts |
| `shipping` | delivery of an order: tracking, delays, delivery address, parcels that have not arrived |
| `returns` | sending a physical product back, return labels, exchanges, the return window |
| `cancellation` | ending a subscription or plan, stopping automatic renewal |
| `feature_request` | asking for functionality the product does not have |
| `bug_report` | the product, app or website malfunctions: crashes, error codes, freezes, features that stop working |
| `privacy` | personal data: what is stored, copies of data, deletion of personal data, sharing, GDPR requests |
| `partnership` | business proposals: reselling, co-marketing, integrations, sponsorship, volume deals |
| `feedback` | opinions, praise or complaints with no request for help or action |
| `other` | anything unrelated to the company's products and services (off-topic) |

## Tie-break rules (applied before the first-issue rule)

1. `billing` beats `technical` and `bug_report` when a payment, charge or invoice is mentioned.
2. `cancellation` beats `billing` and `returns` when the customer wants to end a subscription.
3. `privacy` beats `account_access` and `cancellation` when the customer asks about or wants deletion of
   their personal data.

Fallback: if a message raises more than one issue and no tie-break rule decides, the label of the issue
mentioned **first** wins.

The labeller (`label(plan)`) applies exactly this: the plan lists the issues in the order they appear in the
message; with one issue the label is that issue; with two issues, if the pair is covered by a rule the rule's
winner is the label, otherwise the first issue's label is.

## Output contract

The reply is exactly one label string from the table, lowercase, with underscores as written.

## Scoring

- Normalisation: strip leading and trailing whitespace only. Nothing else (no lowercasing, no punctuation
  stripping, no fence removal). `Billing`, `billing.`, `"billing"` and `Label: billing` all fail.
- `passed`: the stripped output equals the expected label.
- `valid`: the stripped output is one of the 12 labels.
- `nonanswer`: refusal, empty output, output containing `?`, or output that contains no label word at all
  (e.g. a clarifying question cut off by the 5-token cap).
- Failure categories: `nonanswer`, `format` (a label is present but wrapped, recased or punctuated),
  `missed_other` (expected `other`, got another label), `false_other` (got `other` wrongly), `wrong_label`.
- Per-item secondary values: `expected_idx`, `predicted_idx` (index into the label list; -1 when invalid).
- Case-level secondary (`aggregate`): macro-F1 over the labels that occur as expected or predicted (invalid
  outputs count as a wrong prediction for the expected label's recall), validity, non-answer rate.
  Latency p50 / p95 come from the harness summary.

## Data plan

Every item is planned before any text exists: the issues (labels, in order), one decisive cue string per issue,
the language, the length band, the product domain, the brand, product and customer names, and style
(channel, tone, greeting, sign-off, order number, typos). The generator (gpt-6.2-sol, effort low) writes the
message and must include every cue verbatim, in the planned order.

Slices (main and shift alike):

| Slice | Share | Content |
| --- | --- | --- |
| `clear` | ~11.7% | one issue, any label except `other`, 25-90 words |
| `tie_break` | ~11.7% | two issues forming one of the six rule pairs; winner first or second at random |
| `off_topic` | ~11.7% | one off-topic request, label `other` |
| `multi_issue` | ~11.7% | two issues not covered by a rule; label = first issue |
| `very_short` | ~11.7% | one issue (any label incl. `other`), fewer than 8 words |
| `long` | ~11.7% | more than 150 words; clear (60%) or tie-break (40%) |
| `swedish` | 20% | Swedish; clear 55%, tie-break 20%, multi-issue 15%, off-topic 10% |
| `german` | 10% | German; same mix as Swedish |

Multi-issue pairs exclude `other`, `feedback`, `partnership`, the rule pairs, and `technical`+`bug_report`
(whose boundary is too fine to combine).

## Verification (code)

- Every planned cue appears in the message (case-insensitive; curly quotes and dashes normalised), and in
  the planned order.
- No cue of an unplanned label appears.
- Trigger-word blacklists for labels that take part in tie-break rules: when `billing` is not a planned issue,
  no payment words (charged, invoice, payment, paid, refund, ...; Swedish betal-, faktura, ...; German
  Rechnung, abgebucht, Zahlung, ...); when `cancellation` is not planned, no cancel words; when `privacy` is
  not planned, no personal-data words.
- `very_short`: fewer than 8 whitespace-separated words. `long`: more than 150 words.

Then gpt-6-luna checks the message against a brief with the label definitions, the rules, the planned issues
and the expected label; flagged items are dropped.

## Shift set

A new product domain (e-bikes on subscription with a rider app instead of smart home devices with a Plus
subscription), unseen brands (`companies(pool="shift")`) and paraphrased cue wordings for every label
in all three languages. The label definitions in the prompt stay as they are: the prompt is the object under
test and is fixed, so "label definitions paraphrased" is realised as paraphrased wording of the decisive cues
in the messages, which have the same meaning as the main-set cues.

## Decisions

- The fallback "first issue wins" rule is stated in the prompt and the spec in addition to the three tie-break
  rules; without it multi-issue items have no defined answer.
- Labels are part of the task definition and must appear in every prompt, so `answer_strings` returns an empty
  list (the default would forbid the label words themselves).
- The reference date is not needed (no date reasoning).

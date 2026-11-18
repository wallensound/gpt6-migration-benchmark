# Case 06: Grounded answers with abstention

Single source of truth for the data plan, the labels and the scorer.

## Task

The model receives a CONTEXT (a 200-600-word text; 600-1,800 words in the shift set) and a QUESTION about one
named entity (a company, a person or a product). It must answer from the context only, in at most 15 words, or
reply exactly `NOT_FOUND` when the context does not state the answer for that exact entity.

## Item layout

- `item["input"]`: the context (the generated text, stripped).
- `item["question"]`: the question (planned in code, never generated).
- User message (`user_message`): `CONTEXT:\n<context>\n\nQUESTION: <question>`. Both labels stay in English for
  all languages (an integration-level template).
- Language: about 70% English, 20% Swedish, 10% German. Context and question are in the same language. The
  answer language is not scored (the values are language-neutral: digits, city names, invented names).

## Facts

Every item plans one *target entity*, one *asked attribute* and, when answerable, one *value*.

| Entity | Attribute | Value type | Value range |
| --- | --- | --- | --- |
| company | founded_year | number | 1948-2018 |
| company | employees | number | 120-980 |
| company | hq_city | city | fixed list of cities spelled the same in EN/SV/DE |
| company | ceo | person name | `harness.entities.people()` |
| company | flagship | product name | `harness.entities.products()` |
| person | birth_year | number | 1956-1995 |
| person | birth_city | city | as above |
| person | employer | company name | `harness.entities.companies()` (short name) |
| product | launch_year | number | 2009-2025 |
| product | price | number (euros) | 19-899 |
| product | weight | number (grams) | 85-950 (not for software/service products) |
| product | manufacturer | company name | short company name |

Companies come from `companies(pool="main")` in the main set and `companies(pool="shift")` in the shift set
(target, look-alikes, and company-valued attributes). People and products have no shift pool and are shared.

Each context also states two *filler facts* about the target: two other attributes of the same entity type with
their own values (fewer if the type has fewer attributes). `birth_year` and `birth_city` are never fillers for
each other (both read "born in"). All numbers in an item are distinct.

*Look-alike entities* have a name that differs from the target by one vowel (or, for people, the same surname
with a different first name, or a one-vowel change of the surname). Neither name is a substring of the other.
A look-alike always states its own, different value for the asked attribute.

## Slices (main set)

Weights: unanswerable 35%; the five answerable slices 13% each.

| Slice | Answerable | What it tests |
| --- | --- | --- |
| plain | yes | value stated once anywhere; any attribute |
| lookalike_distractor | yes | one look-alike with a conflicting value of the same attribute |
| numeric_answer | yes | numeric attribute |
| answer_last_sentence | yes | every occurrence of the value is in the last sentence |
| answer_two_sentences | yes | the entity is named in one sentence and the value given in a following sentence that does not name it (a pronoun or "the company") |
| unanswerable | no | half `missing` (the attribute is not stated for anyone), half `lookalike` (only a look-alike has it) |

Non-numeric slices pick a text attribute with probability 0.65, otherwise a numeric one.

## Shift set

Same slices and weights. Contexts are three times longer (600-1,800 words) and every item has two look-alike
entities, each with its own distinct value for the asked attribute. Unanswerable shift items are therefore all
of the `lookalike` kind (the target is present but has no value for the attribute). Companies come from the
unseen shift pool.

## Label

`label(plan)` reads only the plan:

```json
{"answerable": true, "value": "1987", "numeric": true, "conflicting": ["1991"]}
{"answerable": false, "value": null, "numeric": false, "conflicting": ["1991"]}
```

`conflicting` holds the look-alikes' values (empty when there are none).

## Scorer

Let `t` be the output text with surrounding whitespace removed.

- **Exact abstention**: `t`, after removing one trailing `.`, equals `NOT_FOUND` (case-sensitive). Nothing
  else is tolerated: backticks, quotes, Markdown, extra words or a lowercase `not_found` are not exact.
- **Normalisation** for value matching: Unicode diacritics folded (`harness.entities.ascii_fold`), lowercased,
  every run of non-alphanumeric characters replaced by one space. A value *appears* when its normalised form
  occurs as a whole-token sequence in the normalised answer (so `1987` matches `In 1987.` but not `19870`;
  `Lund` does not match `Lundberg`; `Malmo` matches `Malmö`).
- **Words**: whitespace-separated tokens of `t`.
- **Markdown**: a line starting with `#`, `- `, `* ` or `1. `, or any of `**`, `__`, or a backtick.
- **Clarifying question**: `t` contains `?`.
- **Prose abstention** (only used to classify, never passes): `t` contains `NOT_FOUND` in any case, or a phrase
  such as "not mentioned", "not stated", "does not say", "no information", "inte nämns", "nicht erwähnt"
  (see `ABSTAIN_RE` in case.py).

**Answerable item passes** when: `t` is non-empty, not a clarifying question, has no Markdown, does not contain
`NOT_FOUND` in any case, has at most 15 words, the value appears, and no `conflicting` value appears.

**Unanswerable item passes** only on exact abstention.

**valid** (obeys the output contract): exact abstention, or a non-empty answer of at most 15 words with no
Markdown, no `?`, no `NOT_FOUND` substring and no refusal.

**nonanswer**: empty output, a refusal, or a clarifying question.

**Failure categories**: `empty_or_refusal`, `clarifying_question`, `format` (Markdown, or `NOT_FOUND` wrapped in
other text), `too_long`, `over_abstain` (answerable but abstained), `lookalike_confusion` (a conflicting value
appears), `wrong_value`, `answered_unanswerable`, `abstain_wrong_format` (unanswerable, abstained in prose).

## Secondary scores

Per item: `unanswerable` (0/1), `abstained` (0/1: prose abstention or exact abstention), `clarify` (0/1), `words`.
Case level (`aggregate`): abstention precision (unanswerable among abstained), abstention recall (abstained
among unanswerable), over-abstention rate (abstained among answerable), clarification rate, answerable and
unanswerable accuracy.

## Generation and verification

The generator gets the entity, the facts (verbatim strings, numbers as digits), the slice's placement rule,
the absence rule for unanswerable items, a genre, an angle, an opening style and a target length, all seeded.
Code verification: target name present; every planned value present verbatim (numbers exactly once); the
asked value absent from unanswerable items; look-alike names and values present; placement rule for the last
sentence and two-sentence slices; length bounds (main 170-700 words, shift 500-2,100); no Markdown; a crude
language check. gpt-6-luna then checks that unanswerable items really lack the answer for the asked entity
(also indirectly, e.g. "for 30 years"), and that answerable items state it once with no conflicting value.

## Edge-case decisions

- Answer language is not checked; a Swedish question answered in English passes if the value appears.
- An answer that names both the right value and a look-alike's value fails (`lookalike_confusion`), even if it
  attributes them correctly.
- Extra words around the value are fine within 15 words ("Kolvex was founded in 1987.").
- Units are not checked for numeric values (`349` passes for "349 euros").
- The question mark rule is strict: any `?` in an answer is treated as a clarifying question.

# Case 05: Format-constrained summary

Single source of truth for the prompt, the data and the scorer.

## Task

The user message is one news article (plain text: a headline line, a blank line, paragraphs). The model returns a
summary of exactly three plain-text bullets in English, each starting with "- " and at most 20 words, covering the
article's three main points. Articles are in English, or in Swedish for the `swedish_source` slice; the summary is
always English.

## Data plan

Each item is planned before any text exists (`plan`, seeded):

- **Story.** One of eleven story types (plant, acquisition, ceo, launch, trial, contract, cuts, funding, recall,
  fleet, stores) about a subject company from `harness.entities` (main pool; shift pool for the shift set).
- **Three key facts**, the article's headline points:
  - **number**: an integer between 40 and 85,000, never 2000-2100 (avoids clashes with years and days of the month);
    English surface form uses comma thousands separators ("1,250"), Swedish uses a space ("1 250").
  - **named entity**: an invented company, person (full name) or product, depending on the story; never the subject
    company itself.
  - **date**: a day between 1 and 28, from 1 December 2026 to 28 June 2028. English surface "3 March 2027" or
    "March 3, 2027" (seeded); Swedish "3 mars 2027".
- **Three distractor facts**, clearly minor: one person name, one figure and one date (the `numbers_heavy` slice uses
  three figures instead). Distractor values never equal a key value; distractor dates never share day and month with
  the key date; the distractor person differs from the key entity.

The generator (gpt-6.2-sol, effort low) writes an article containing all six anchors verbatim, with the key facts as
the headline points and the distractors mentioned once in passing.

## Slices

| Slice | What differs |
| --- | --- |
| plain | key facts in the headline and opening, 480-650 words requested |
| facts_near_end | headline and first half must not contain any key anchor; the key facts come in the final third |
| numbers_heavy | three numeric distractors plus 3-5 further background figures |
| long_articles | 780-860 words requested |
| swedish_source | article in Swedish; the summary must still be English |

Shift set: the same slices except `long_articles`, unseen companies (shift pool), articles of 1,500-2,000 words.

## Code verification (`verify`, items failing are dropped)

- Word count (whitespace tokens) within 400-900 (main), 700-900 (`long_articles`) or 1,500-2,000 (shift).
- No list or bullet lines in the article.
- Every key and distractor anchor appears verbatim (numbers with digit boundaries, names with word boundaries).
- No calendar date (day + month) other than the planned ones (date recogniser below).
- `facts_near_end`: the first occurrence of each key anchor lies in the second half of the article (by characters).
- Swedish articles contain at least 15 Swedish function words; English articles at most 5.

`make_input` replaces non-breaking and thin spaces with ordinary spaces, removes Markdown heading marks and
`**`/`__`, and collapses runs of blank lines. The LLM verifier then drops items where a key fact is missing,
conflicting, or not a main point, or a minor detail competes with the main points.

## Label

`label(plan)` = `{number, number_text, entity, entity_kind, date: [y, m, d], date_text}` from the plan only.

## Output contract and scoring (fully deterministic)

The raw output text is stripped of leading and trailing whitespace. Then:

**Format** (`format_ok`) passes when all hold:

1. Exactly three lines (`splitlines`). Blank lines count as lines, so blank lines between bullets fail.
2. Each line starts with exactly "- " (hyphen, space; no indentation) followed by non-empty text.
3. Each bullet has at most 20 words. A word is a whitespace-separated token containing at least one letter or digit
   (so "1,250" and "co-founder" are one word; a lone "–" is not a word).
4. No other Markdown: no `**`, `__`, `~~`, backticks, `[text](url)` links, `*italic*` or `_italic_`, HTML tags, no
   heading `#` or quote `>` and no second list marker or numbering at the start of a bullet's text.
5. English: the output contains fewer than two distinct Swedish function words from the fixed list (och, att, är,
   som, för, med, på, av, det, har, kommer, inte, ett, vid, hos, enligt, också, från, efter, eller, detta, även).
   Otherwise `wrong_language`.

**Coverage** (`facts_covered`, 0-3), searched anywhere in the output:

- **Number**: covered when some number written in digits in the output equals the key value. Numbers are read as
  digit groups with optional thousands separators (comma, space, non-breaking or thin space, between groups of three
  digits) and an optional decimal part (`.` or `,` followed by digits). "1,250", "1250" and "1 250" all equal 1250;
  "1.25 billion", "1.2k" or number words do not.
- **Entity**: covered when the full name appears, compared after removing diacritics, casefolding and collapsing
  whitespace, with word boundaries ("Velmora's" counts; a surname alone does not).
- **Date**: covered when a date expression with the same day and month appears, and its year, if one is attached,
  equals the key year. Recognised forms: "3 March 2027", "3rd of March 2027", "March 3, 2027", "March 3rd",
  "3 Mar 2027", "Sept 3", Swedish month names ("3 mars 2027"), and ISO "2027-03-03". A month without a day
  ("March 2027") or other numeric forms ("03/03/2027") do not count.

**Pass** = format_ok and facts_covered == 3.

**Nonanswer**: empty output, a refusal, or an output without any "- " line that contains a question mark.

**Secondary** per item: `format_ok` (0/1), `facts_covered` (0-3), `lines`, `max_words`, `total_words`, and
per-fact coverage. `aggregate` reports their means, the rate of bullets over 20 words and the rate of correct line
counts.

**Failure categories**: format_line_count, format_bullet_marker, format_too_long, format_markdown, wrong_language,
missing_number, missing_entity, missing_date, nonanswer, other.

## Edge-case decisions

- Mentioning distractor facts is not penalised; only format and the three key anchors matter.
- Translating a Swedish date into English ("3 mars 2027" to "3 March 2027") is fine; keeping the Swedish form is
  also accepted by the date recogniser, but Swedish function words elsewhere fail the language check.
- A trailing period, a final newline, or trailing spaces on a line are fine.
- A preamble ("Here is the summary:") or a closing line makes the line count wrong and fails.
- No reference date is needed; articles are set in mid-November 2026.

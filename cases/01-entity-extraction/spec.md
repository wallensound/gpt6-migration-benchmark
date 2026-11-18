# Case 01: Rule-heavy entity extraction

Single source of truth for the prompt, the labeller (`label`) and the scorer (`score`, `parse`).

## Task

The input is one news-style paragraph (120-400 words; shift set: 300-900 words) in English, Swedish or
German. Return every company named in it, as canonical names, under the 12 rules below.

## The 12 rules

1. **Output contract.** Reply with one JSON array of strings and nothing else: no Markdown fences, no prose
   before or after, no object wrapper, no comments. Example: `["Velmora", "Orsenta Energy"]`.
   (With Structured Outputs on, the reply is the object `{"companies": [...]}` with the same array.)
2. **What is a company.** Every business named in the text counts, including one that is mentioned only
   through a product name, a possessive or a web or email domain. These are not companies and are never
   returned: people (including their titles), places (cities, regions, countries), product categories and
   generic descriptions ("electric trucks", "payroll software", "a Swedish fintech", "a rival"), and
   companies that are not named.
3. **Legal suffixes.** Strip the legal-form suffix: AB, GmbH, AG, Ltd, PLC, Inc., LLC, Corp., AS, ASA, Oy,
   Oyj, A/S, ApS, SA, SAS, B.V., N.V. (with or without a final period). "Velmora AB" -> "Velmora".
4. **Name words stay.** Words that are part of the name itself are kept: Group, Systems, Labs, Partners,
   Works, Freight, Energy, Foods. "Orsenta Energy Ltd" -> "Orsenta Energy".
5. **Products map to the parent.** A product or service name built from a company name plus a product word
   ("Velmora Mail", "the Velmora Pay app") is a mention of the parent company: return "Velmora". This holds
   whether or not the parent company is also named on its own. Product names are never returned.
6. **Sibling products.** Several products of one company ("Velmora Mail and Velmora Pay") give one entry.
7. **Possessives.** "Velmora's", "Velmora’s" and the Swedish or German genitive "Velmoras" -> "Velmora".
8. **Domains.** A web address or email domain ("velmora.se", "www.velmora.se", "press@velmora.se") is a
   mention of the company that owns it. Use the company's name as written elsewhere in the text; if the
   company is named nowhere else, return the part before the top-level domain with its first letter
   capitalised ("velmora.se" -> "Velmora").
9. **Spelling.** Write each name exactly as the text writes it, with the same capitalisation and diacritics
   ("Dåskor", never "Daskor"). Never translate, abbreviate or ASCII-fold a name.
10. **Deduplicate.** Each company appears exactly once, however many times and in however many forms it is
    mentioned. A duplicate entry is an error.
11. **Order.** List companies in the order of their first mention in any form. (Order is not scored.)
12. **Empty.** If no company is named, reply `[]`.

The rules apply unchanged to Swedish and German text; names are never translated.

## Data decisions (how items are built so that the rules give one answer)

- Companies come from `harness.entities.companies(pool="main")` (shift set: `pool="shift"`). The canonical
  name is the entity's `name`. Each planned company has one or more planned mentions (surface forms):
  `plain` ("Velmora"), `legal` (the entity's `legal_name`), `possessive` ("Velmora's"; English items only),
  `product` (name + product word from a fixed list), `domain` (the entity's `domain`, optionally as
  `www.` or an email address).
- Product mentions are only planned for one-word company names, so the parent is unambiguous.
- Domain-only companies (named nowhere else) are only one-word names without diacritics, so rule 8 gives
  the entity name.
- Two-word companies are always written in full; a lone first word is never planned.
- Distractors: people from `entities.people()` (with job titles), real cities, product categories.
  No other organisation of any kind (company, brand, bank, exchange, news outlet, agency, university)
  may appear; such items are dropped by the verifier.
- The label is the list of canonical names in planned order of first mention, deduplicated.

## Scoring

- `parse`: the reply text, stripped of surrounding whitespace, must be valid JSON that is an array of
  strings (with Structured Outputs on: that array, or an object whose only key is `companies` holding it).
  Anything else (fences, prose, other shapes, non-string elements) is invalid.
- Names are compared after Unicode NFC normalisation and stripping surrounding whitespace; nothing else is
  normalised (case and diacritics matter).
- **Pass**: the reply is valid, has no duplicates, and its set of names equals the expected set.
- Secondary per item: `tp`, `fp`, `fn` (an invalid reply counts every expected name as `fn`), `valid`,
  `duplicates`. Case level (`aggregate`): micro precision, recall and F1 over all items, and format validity.
- Non-answer: empty reply, refusal, or a reply with no JSON array that reads as a question or refusal.

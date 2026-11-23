# GPT-6 migration benchmark — brief

17 November 2026. The original design brief for this benchmark, kept as the specification the repository implements. Where the build had to deviate, PROGRESS.md records why.

Build eight synthetic test cases where a prompt that worked on GPT-5.6 is likely to break on GPT-6. Run the same automated migration loop on each, three times over, and measure whether the fix reproduces. No production code or customer data is involved, and the whole run is designed for Claude Code to execute unattended over two nights.

## Goal

Find out whether automated prompt migration to GPT-6 is reproducible: does the same loop, run on different tasks and with different random seeds, reliably bring a legacy prompt back to its old accuracy on a newer model?

No production pipeline is involved. Every test case is synthetic and self-contained, so the benchmark can be published in full, rerun by anyone, and run overnight by a coding agent.

**The four questions it answers:**

1. **How much breaks?** When a prompt tuned on GPT-5.6 moves to each GPT-6 model unchanged, how much accuracy is lost, and where?
2. **Does the loop fix it?** After automated optimisation, does the GPT-6 prompt match the legacy prompt on its original model?
3. **Is the fix reproducible?** Do three independent loop runs per case land close together and reach the same verdict?
4. **What does it cost?** Cost per correct answer before and after, per model.

**Done when:**

- **Cases built.** Eight test cases exist, each with a spec, a legacy prompt, a data generator, a tested scorer and sealed data.
- **Runs complete.** The baseline sweep, the loop runs and the sealed final evaluation have run for every case.
- **Verdicts written.** A report answers each question with the numbers behind it, against thresholds fixed before the first run.
- **Reproducible.** The repository reruns end to end from one command.

## Scope

Eight synthetic test cases, one legacy "before" setup per case, and four GPT-6 targets, all on OpenAI's own API.

**Before: the legacy setup.** Each case's legacy prompt is tuned until it works well on `gpt-5.6-sol`, using the settings older integrations typically used: Chat Completions, reasoning effort `none` and `temperature: 0`. This stands in for a prompt that ran fine in production before GPT-6. Confirm the model ID and that it accepts these settings. If it doesn't, use the closest GPT-5.x model that does, and record which one.

**After: the GPT-6 targets.** Every GPT-6 call goes through the Responses API.

| Target | Role | Reasoning efforts to test | Price per 1M tokens, in / out |
| --- | --- | --- | --- |
| gpt-6.2-astra | Quality ceiling | low, medium | $8 / $40 (Standard) |
| gpt-6.2-sol | Main tier | low, medium | $2 / $10 (Standard) |
| gpt-6.1-terra | Fast mid-tier | none, low | $0.50 / $2.50 (Flex) |
| gpt-6-luna | Cheapest; built for focused, high-volume work | none, low | $0.05 / $0.25 (Flex) |

**Which targets get the optimisation loop:**

- **gpt-6-luna and gpt-6.1-terra:** all eight cases, three seeds each. These answer the reproducibility question at low cost.
- **gpt-6.2-sol:** three cases, three seeds each, to check that the result holds on the main tier.
- **gpt-6.2-astra:** no loop. It is the quality ceiling, measured zero-shot and in the final evaluation.

**Out of scope:** production code, prompts and data; other model families; fine-tuning, which OpenAI has closed to new users.

**Pin and date everything.** Record exact model IDs, the run date and the SDK version with every result. Check each target's supported reasoning efforts on its model page before the sweep.

## What changes in GPT-6

Swapping the model string is not enough: GPT-6 changes the request shape, removes the sampling controls older prompts rely on, and behaves differently with long rule lists. Each change below is probed by at least one test case. Sources: OpenAI's [GPT-6 guide](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra) and [deployment checklist](https://developers.openai.com/api/docs/guides/deployment-checklist).

| Area | What changes | Probed by |
| --- | --- | --- |
| Endpoint | OpenAI says to start with the Responses API. Astra and 6.1 Sol require it for tool calling; 6 Sol and Luna allow function calling in Chat Completions only at effort `none` | Case 4 |
| Sampling | When reasoning effort is not `none`, `temperature`, `top_p`, `top_logprobs` and `logprobs` must go | Case 2, and every case's stability measure |
| Reasoning effort | Astra and 6.1 Sol have no `none`. OpenAI suggests `low` for extraction and classification | Case 3 |
| Output format | Structured Outputs move to `text.format` with a JSON schema | Cases 1, 2 and 7 |
| Length | `text.verbosity` now sets default detail; "be concise" instructions may stop working | Case 5 |
| Behaviour | Astra follows instructions more literally, is more sensitive to conflicting guidance, asks for clarification more often, and leans towards Markdown | Cases 1, 6, 7 and 8 |
| Caching | Explicit cache breakpoints; `prompt_cache_retention` becomes `prompt_cache_options.ttl`; cache writes cost 1.25× input | Measured in every case |
| Errors | A 429 can mean `slow_down` or a billing problem; 503 `server_is_overloaded` comes with `Retry-After` | Handled by the harness |

OpenAI's own blog says [guidance that helps Sol or Luna may over-constrain GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra). Case 7 tests that directly.

## Test cases

Eight cases, each built around one documented way a GPT-5.6-era prompt can break on GPT-6. Together they cover extraction, structured output, classification, tool calling, formatting, grounded answers, rule-heavy normalisation and constrained translation.

| # | Case | Migration risk it probes | Pass means |
| --- | --- | --- | --- |
| 1 | Rule-heavy entity extraction | Long emphatic rule lists; literal instruction following | Exact set of canonical names |
| 2 | Invoice fields with a confidence flag | `logprobs` and `temperature` removed; `response_format` replaced | All eight fields correct |
| 3 | Ticket routing at no reasoning | No `none` effort on Astra and Sol; clarifying questions | Exact label |
| 4 | Tool selection and arguments | Tool calling moves to Responses | Right function, exact arguments |
| 5 | Format-constrained summary | Markdown habits; `text.verbosity` | Format rules met and three facts present |
| 6 | Grounded answers with abstention | Over-cautious reading of "NEVER" rules | Correct answer, or `NOT_FOUND` when unanswerable |
| 7 | Accumulated, conflicting rules | Over-constraint from stacked guidance | All fields exact |
| 8 | Terminology-locked translation | Freer writing; glossary adherence | All terminology checks pass |

### Rules for every case

- **Self-contained folder.** Each case lives in `cases/<nn-name>/` with `spec.md`, `legacy_prompt.md`, `legacy_config.yaml`, code for plan, generate, verify, label and score, and tests.
- **Legacy markers.** Each legacy prompt must contain the old-style patterns listed for its case, so it is realistically "old". A test checks that the markers are present.
- **Calibration floor.** The legacy prompt must score at least 90% on the source model on dev (85% for cases 5 and 8) before the case counts. Tune it on train only, for at most four rounds, then freeze it with a hash. A prompt that never worked cannot be migrated.
- **Fixed reference date.** Prompts that need "today" state 17 November 2026 explicitly.
- **Invented entities.** Generate fictional lists once and reuse them: 2,000 companies, 500 people, 300 products. Real cities and countries are fine.
- **Languages.** English by default, with about 20% Swedish and 10% German items in cases 1, 2, 3 and 6. Case 8 is Swedish to English.
- **Sizes per case.** Train 120, dev 200, test 300, shift 150.

### Case 1: Rule-heavy entity extraction

- **Task:** From a news-style paragraph, return every company named, as a JSON array of canonical names under a 12-rule spec.
- **Why it may break:** A long, emphatic rule list written for an older model. GPT-6 follows instructions more literally and may over-apply rules, add Markdown fences, or ask about ambiguous names.
- **Legacy setup:** About 1,200 tokens of rules with all-caps NEVER and ALWAYS; free-form JSON parsed by code; temperature 0, effort `none`.
- **Data plan:** Pick 0–12 companies from the invented list, each with a planned surface form: legal suffix, product phrase ("Acme Mail"), possessive, domain form ("acme.se"), diacritics. The generator writes a 120–400-word paragraph containing every form verbatim, plus distractors such as people, cities and product categories.
- **Expected output and scorer:** A deterministic canonicaliser applies the spec to the plan. Pass is an exact set match; also report micro precision, recall and F1, and format validity.
- **Slices:** legal suffixes; parent brand present; parent absent; sibling products; domain forms; diacritics; distractors; no companies; dense (10 or more); Swedish; German.
- **Shift set:** an unseen company list, with paragraphs two to three times longer.

### Case 2: Invoice fields with a confidence flag

- **Task:** Extract eight fields from invoice text into JSON (vendor, invoice number, issue date, due date, currency, net, VAT, total) and flag fields that need human review.
- **Why it may break:** The legacy pipeline flags low-confidence fields using `logprobs` at temperature 0. With reasoning on, GPT-6 drops both, so flagging must be redesigned. Output also moves from `response_format` to `text.format`.
- **Legacy setup:** Chat Completions with a `response_format` JSON schema and `logprobs: true`. A field is flagged when its mean token log-probability falls below a threshold tuned on train.
- **Data plan:** Sample field values in code and render the text from 12 layout templates, then an LLM paraphrase pass. Include European dates, decimal commas, currency symbols and codes, subtotals next to totals, missing fields (expected `null`), and Swedish and German labels ("Förfallodatum", "MwSt").
- **Expected output and scorer:** Labels are the sampled values. Dates normalise to ISO and amounts to two decimals. Pass means all eight fields correct; also report field accuracy, and review-flag precision and recall against the fields that are actually wrong.
- **Migration note:** The loop may replace logprob flags with nulls for unsure fields, a per-field confidence value in the schema, or agreement across two runs. The report must say which one won.
- **Slices:** date formats; decimal comma; missing field; subtotal versus total; mixed currencies; Swedish; German.
- **Shift set:** three unseen layout templates and scanned-style noise (broken lines, OCR typos).

### Case 3: Ticket routing at no reasoning

- **Task:** Route one customer message to exactly one of 12 labels and output the label only.
- **Why it may break:** The legacy prompt runs at effort `none` for speed, which Astra and 6.1 Sol don't offer, and `low` costs more and takes longer. Astra may also ask clarifying questions on ambiguous tickets, or wrap the label in prose.
- **Legacy setup:** A short prompt with label definitions and three tie-break rules, such as "billing beats technical when a payment is mentioned"; effort `none`, temperature 0, at most 5 output tokens.
- **Data plan:** Plan the label, a difficulty (clear, tie-break, off-topic meaning "other", multi-issue) and a decisive cue. The generator writes the message, which must contain the cue; a check confirms it does.
- **Expected output and scorer:** The label comes from the plan via the tie-break rules. Pass is the exact label string; also report macro-F1, non-answer rate, and p50 and p95 latency.
- **Slices:** clear; tie-break; off-topic; multi-issue; very short (under 8 words); long (over 150 words); Swedish.
- **Shift set:** label definitions paraphrased with the same meaning, and a new product domain.

### Case 4: Tool selection and arguments

- **Task:** Given a request and eight function definitions, call exactly one function with the correct arguments, or none when no tool applies.
- **Why it may break:** Tool calling moves to the Responses API for Astra and Sol. On 6 Sol and Luna, Chat Completions function calling only works at effort `none`. Call formats and parsing change.
- **Legacy setup:** Chat Completions `tools` with `tool_choice: "auto"`, effort `none`, temperature 0. Tools: `create_event`, `find_contact`, `send_email`, `create_task`, `log_call`, `search_docs`, `get_weather`, `convert_currency`.
- **Data plan:** Sample an intent and argument values from each schema; the generator writes a natural request containing them. Relative dates such as "next Tuesday" resolve against the fixed reference date stated in the prompt. 15% of requests need no tool.
- **Expected output and scorer:** The label is the function name plus normalised arguments. Pass means the right function and every required argument exact; also report tool-name accuracy, argument accuracy, and the false-call rate on no-tool requests. Functions are never executed.
- **Slices:** relative dates; optional arguments left out; look-alike tools (`create_task` versus `create_event`); no tool needed; several candidate values with a selection rule.
- **Shift set:** two tools renamed with reworded descriptions, and requests in Swedish.

### Case 5: Format-constrained summary

- **Task:** Summarise a 400–900-word article into exactly three plain-text bullets starting with "- ", each at most 20 words, covering three planted key facts.
- **Why it may break:** GPT-6 Astra leans towards Markdown, headings and longer output, and `text.verbosity` now sets the default level of detail, so legacy "be concise" wording may stop working.
- **Legacy setup:** Formatting rules in the prompt ("no headings", "be concise"), temperature 0.
- **Data plan:** Plan three key facts (a number, a named entity, a date) and three distractor facts. The generator writes an article containing all six verbatim, with the key facts as the article's main points.
- **Expected output and scorer, fully deterministic:** Format passes when there are exactly three lines, each starting with "- ", each at most 20 words, with no other Markdown. Each key fact counts as covered when its anchor (the number, name or date, normalised) appears. Pass requires both.
- **Slices:** facts near the end; numbers-heavy; long articles; Swedish source with an English summary.
- **Shift set:** articles of 1,500–2,000 words.

### Case 6: Grounded answers with abstention

- **Task:** Answer a question from a given context in at most 15 words, or reply exactly `NOT_FOUND` when the context does not contain the answer.
- **Why it may break:** Legacy prompts use strong "NEVER guess" language that GPT-6 may take too seriously, so it over-abstains. Astra is also more likely to ask for clarification.
- **Legacy setup:** A prompt with all-caps prohibitions, temperature 0.
- **Data plan:** Plan a fact (entity, attribute, value); the generator writes a 200–600-word context around it. 35% of items are unanswerable: the attribute is missing, or only a look-alike entity has it.
- **Expected output and scorer:** Answerable items pass when the normalised value appears and the answer is at most 15 words. Unanswerable items pass only on exactly `NOT_FOUND`. Also report abstention precision and recall, and the clarification rate.
- **Slices:** look-alike distractor; numeric answer; answer in the last sentence; answer spread over two sentences; unanswerable.
- **Shift set:** contexts three times longer, with two look-alike entities.

### Case 7: Accumulated, conflicting rules

- **Task:** Normalise a messy contact record (name, phone, email, company, country) into a fixed JSON format under 18 rules.
- **Why it may break:** The rules accumulated over "several model generations": duplicates, an IMPORTANT block, and two rules that conflict in edge cases, settled by a precedence note at the bottom. OpenAI warns that this kind of guidance can over-constrain GPT-6 Astra or make it pause.
- **Legacy setup:** The long accumulated prompt, free-form JSON, temperature 0.
- **Data plan:** Entirely in code. Sample a clean record, then apply messy transformations: phone formats, casing, whitespace, country names in three languages, swapped fields. A deterministic normaliser produces the expected output. An LLM pass adds natural-looking notes around the record.
- **Expected output and scorer:** Pass means every field exact; also report field accuracy and format validity.
- **Slices:** precedence conflicts; international phone numbers; missing fields; Unicode names; swapped fields.
- **Shift set:** unseen countries and phone formats.
- **What to watch:** whether the loop simplifies the prompt, and whether the simplified prompt still wins on Luna.

### Case 8: Terminology-locked translation

- **Task:** Translate a Swedish product description of 80–250 words into English as plain text, using a mandatory 40-term glossary.
- **Why it may break:** GPT-6 writes more freely and tends towards formatting and recurring phrases, so legacy glossary instructions may be followed differently.
- **Legacy setup:** The glossary embedded as a list, "plain text only", temperature 0.
- **Data plan:** Plan which glossary terms appear (3–8 per item) and two forbidden alternatives per term. The generator writes the Swedish source containing the planned terms verbatim.
- **Expected output and scorer, deterministic:** Every planned term's required English rendering appears; no forbidden alternative appears; there is no Markdown; and the length is 0.8–1.4 times a reference length. Pass requires all four. Fluency is not scored, and the write-up says so.
- **Slices:** inflected Swedish forms; compound words; terms inside lists; terms used twice.
- **Shift set:** an unseen 20-term extension of the glossary.

## Building the data

Every case uses the same plan-first recipe, made strict: decide the correct answer before generating the input, generate an input that must contain it, verify, then label with deterministic code.

### The recipe

1. **Spec.** `spec.md` holds the rules, the output contract and every edge-case decision. It is the single source of truth for prompt and labels alike.
2. **Reference implementation.** Deterministic code turns a plan into the expected output: a canonicaliser, a normaliser or a fact list, depending on the case. It has at least 15 unit-test fixtures, covering every slice.
3. **Plan.** For each item, a seeded random generator picks the answer, the slice and the surface forms. The seed is recorded.
4. **Generate.** `gpt-6.2-sol` at effort `low` writes the input around the plan, and must include every planned string verbatim.
5. **Verify.** Code checks that every planned string appears exactly. `gpt-6-luna` then flags anything that would change the answer, such as an unplanned company or a second total. Flagged items are dropped, never edited. If more than 20% of a case's items are dropped, fix that case's generator prompt and regenerate the case.
6. **Label.** The reference implementation produces the expected output from the plan.
7. **Split and seal.** Stratify by slice into train, dev, test and shift. Remove duplicates by exact hash and by near-duplicate similarity (character 5-gram overlap above 0.8). Write test and shift to `data/sealed/<case>/` and record their SHA-256 hashes in `data/MANIFEST.json`.
8. **Report.** Write a stats file per case: items per slice and split, drop rate, and average input tokens.

Generate about 30% more items than needed to cover the drops.

### Splits and sizes

| Split | Items per case | Used for | Access |
| --- | --- | --- | --- |
| Train | 120 | Legacy calibration and the loop's failure reports | Open to the loop |
| Dev | 200 | Baseline sweep and accepting candidates | Scores only; the optimiser never sees items |
| Test | 300 | The final verdict, run once | Sealed until the final phase |
| Shift | 150 | Robustness: unseen entities, templates or longer inputs | Sealed until the final phase |

That is 770 items per case and 6,160 in total.

### What these sizes can detect

- **Test.** At around 90% accuracy, 300 items give a 95% margin of about ±3.4 points per case. The verdicts pool evidence across eight cases and three seeds, so the overall picture is firmer than any single case.
- **Dev.** With 200 paired items and about 10% of items flipping between two prompts, McNemar's test detects gains of roughly 6–7 points at 80% power. Smaller real gains will often be rejected, which makes the loop conservative rather than wrong.
- **Knob.** For a publication-grade rerun, double every split. The harness should take sizes from config, not code.

### Disclosed limitation

The inputs are model-written by an OpenAI model and judged on OpenAI models. The write-up states this, and the shift sets with unseen templates are the main check against it.

## Metrics

Each case has its own pass rule, defined by its scorer. Around it sits a common set of metrics so cases can be compared, plus outcome and reproducibility measures that answer the four questions.

### Per run

| Metric | Definition |
| --- | --- |
| Primary score | Share of items that pass the case's rule |
| Secondary scores | Case-specific: F1, field accuracy, abstention precision and recall, tool-name accuracy, review-flag quality |
| Per-slice score | Primary score within each slice |
| Format validity | Share of outputs that obey the output contract |
| Non-answer rate | Clarifying questions, refusals and empty outputs; all count as failures |
| Stability | Share of items whose pass or fail flips across three repeated runs |
| Tokens | Input, cached, cache-write, output and reasoning tokens |
| Latency | p50 and p95 seconds per item |
| Cost per correct answer | Total cost divided by passing items |

### Per case and target

- **Zero-shot drop:** the target's primary score with the frozen legacy prompt, minus the legacy prompt's score on the source model, both on test.
- **Recovery:** the optimised prompt's score on the target, minus the legacy score on the source model.
- **Migrated:** the optimised target is non-inferior to the legacy setup, meaning the lower end of a one-sided 95% paired-bootstrap interval for the difference is above −3 points.

### Reproducibility

- **Seed spread:** the gap between the highest and lowest final test score across the three seeds.
- **Verdict agreement:** whether all three seeds reach the same migrated verdict.
- **Shift gap:** the optimised prompt's test score minus its shift score. A large gap signals overfitting to the generator's style.

### Statistics

- **Intervals.** Report scores with 95% Wilson intervals, and differences with paired bootstrap intervals (2,000 resamples over items).
- **Accepting candidates.** Use McNemar's exact test on dev items where two prompts disagree.
- **Many comparisons.** Apply a Holm correction when the final phase compares several configurations within a case.
- **Pre-registration.** All thresholds live in `PROTOCOL.md`, committed before the sweep and never edited afterwards. The report quotes them verbatim.

## Optimisation loop at a glance

The loop tunes on train and decides on dev. Each run is one case, one target and one seed. The sealed test and shift sets are opened only in the final step.

## Optimisation loop v2

A simple migration loop already has the two ideas that matter most: rewriting from failure patterns rather than individual items, and a final check on unseen data. Version 2 adds a separate dev set for every decision, competing candidates in each round, a statistical bar for accepting them, and seeds so every run can be repeated.

### What changes from a simple loop

| Simple loop | Version 2 | Why |
| --- | --- | --- |
| One set for tuning and checking until the end | Train, dev and sealed test sets | The loop can no longer tune itself to the set that judges it |
| One new prompt per round | Four candidates per round, each from a different kind of edit | Explores more widely and gets stuck less |
| Accept if accuracy goes up | Accept only if the gain is significant and no slice regresses | Small bumps on 200 items are often chance |
| Models and prompts combined ad hoc | The sweep fixes the effort per target, then one loop per case, target and seed | Results stay comparable |
| An LLM reads raw failures | Code diffs every item; an LLM only labels and summarises | Cheaper, consistent and auditable |
| One run | Three seeded runs per case and target | Measures whether the result reproduces |

### Parameters

| Parameter | Value |
| --- | --- |
| Rounds | At most 5 |
| Candidates per round | 4 |
| Screening | 60 stratified train items |
| Dev evaluation | The best screened candidate on all 200 dev items |
| Early stop | Two rounds in a row with nothing accepted |
| Optimiser model | gpt-6.2-sol at effort `high` |
| Failure labeller | gpt-6-luna |
| Seeds | 11, 22 and 33 |

### Step by step

1. **Sweep.** Run each case's frozen legacy prompt on dev: once on the source setup, and once per target and effort. Results feed the "what broke" chapter.
2. **Choose the effort.** For each case and target, keep the effort with the best primary score per dollar; on ties, the lower effort. It stays fixed for the loop.
3. **Mechanical port.** Make only the changes the API forces: move to Responses, drop `temperature` and `logprobs`, move the schema to `text.format`. Score this port on dev too; it is the honest "just swap the model" baseline and the loop's starting prompt.
4. **Run on train** with the current prompt and score every item.
5. **Diagnose.**
   1. Code computes each failing item's diff against the expected output.
   2. gpt-6-luna labels each failure with one category from the case's taxonomy and a one-line cause.
   3. Code builds a failure report: counts per category and slice, the top three patterns, and up to three examples per pattern, rewritten with invented values that appear in no split.
6. **Propose.** The optimiser receives the spec, the current prompt and settings, the failure report and the rejection log. It returns four candidates, each using a different kind of edit:
   - **Targeted fix:** one rule change aimed at the top failure pattern.
   - **Example swap:** add or replace one worked example, with invented values.
   - **Simplify:** merge or delete rules and shorten. This is the key test for case 7.
   - **Restructure:** reorder sections, or move the core requirement to the top.
   - **Rewrite:** a fresh prompt written from the spec alone.
   - **Settings change:** Structured Outputs on or off, or a different `text.verbosity`.
7. **Screen** all four on 60 train items. Drop any that trail the current prompt by more than 3 points or fall below 98% format validity.
8. **Evaluate** the best survivor on all 200 dev items.
9. **Decide.** Accept only if McNemar's test favours the candidate at p < 0.05, no slice drops more than 2 points, and format validity is at least 99%. Log every rejection with its reason.
10. **Check for leakage** before accepting. The candidate must contain no six-word sequence from any dev, test or shift input, and no expected answer from those splits.
11. **Stop** at the round limit, after two empty rounds, or when the phase budget runs out. Save the final prompt, settings, manifest and full round log.

### What a seed changes

The seed sets the order of train items, the screening sample, which failure examples are shown and the optimiser's sampling. Dev and test stay identical across seeds, so differences between seeds are paired and directly comparable.

### Rules for the optimiser

- It may change only the prompt text and the settings listed above. Model and effort are fixed per run.
- It may rephrase the spec but never change it, and must keep the output contract.
- It must never include any string taken from the data.
- Every candidate carries a one-line rationale. Those rationales become the story in the write-up.

Never return to the loop after the final phase. If a case disappoints, report it as it is. A rerun needs a new dataset version and a new entry in `PROTOCOL.md`.

## Reproducibility protocol

"Reproducible" is tested in six separate ways, each with a pass threshold fixed in `PROTOCOL.md` before the first run.

| Check | How it runs | Passes if |
| --- | --- | --- |
| Seed repeats | Three loop runs per case and target, with seeds 11, 22 and 33 | Seed spread is at most 3 points and all three seeds reach the same verdict |
| Across cases | The same loop and parameters on all eight cases | Migrated in at least 6 of 8 cases, for both Luna and Terra |
| Main tier | Sol loops on cases 1, 3 and 7 | Same verdicts as Terra on those cases, with a seed spread of at most 3 points |
| Data version | Regenerate cases 1 and 5 with a new generation seed (dataset v2) and run one loop seed on each | Final score within 3 points of the v1 seed mean |
| Shift | Every optimised prompt on its case's shift set | Shift gap of at most 5 points; anything larger is flagged as overfitting |
| Clean rerun | After night two: fresh clone, empty cache, `make reproduce CASE=03` | Matches the reported numbers within 2 points |

### The overall verdict

- **Reproducible:** seed repeats pass in at least 6 of 8 cases for both Luna and Terra, and the data-version and clean-rerun checks pass.
- **Partly reproducible:** seed repeats pass in 4 or 5 cases, or one of the other checks fails.
- **Not reproducible:** anything worse.

The report shows every case, including the ones that fail. A clear "partly" with honest reasons is more convincing than a perfect score.

### Reading the results

- **Wide seed spread, same verdicts:** the loop finds different prompts of similar quality. That is fine, and worth saying.
- **Same scores, different verdicts:** the case sits near the 3-point margin. Report it as borderline.
- **Large shift gap:** the prompts fit the generator's style, not the task. The method needs more varied data.
- **Luna migrates where Terra doesn't, or the reverse:** a model-specific finding, and good material for the OpenAI observations.

## Local build

A Python project in its own folder, built by Claude Code from this brief. Python because OpenAI's cookbook and most eval tooling use it, and its statistics libraries cover everything here.

### Layout

```text
gpt6-migration-benchmark/
  PLAN.md               this brief, exported as Markdown
  CLAUDE.md             rules for the agent (see the runbook)
  PROTOCOL.md           thresholds and decision rules, frozen before the sweep
  PROGRESS.md           append-only log the agent writes
  REPORT.md             results, regenerated from runs/
  budget.json           per-phase spending caps
  Makefile              every command below
  config/
    models.yaml         model IDs, efforts, prices, rate limits
    sizes.yaml          split sizes, loop parameters, seeds
  cases/
    01-entity-extraction/
      spec.md  legacy_prompt.md  legacy_config.yaml
      case.py           plan, generate, verify, label, score, slices
      tests/            scorer and labeller fixtures
    02-invoice-fields/  ... one folder per case, same shape
  harness/
    runner.py           Responses and Chat Completions calls, retries, cache, cost, budget guard
    generate.py         plan-first data building, verification, splitting, sealing
    loop.py             the optimisation loop
    optimiser.py        candidate generation and leakage checks
    stats.py            Wilson, bootstrap, McNemar, Holm, non-inferiority
    report.py           tables and charts
  data/
    open/<case>/        train.jsonl, dev.jsonl
    sealed/<case>/      test.jsonl, shift.jsonl
    MANIFEST.json       dataset versions and SHA-256 hashes
  runs/                 one DuckDB file, raw JSONL responses, run manifests
```

### The case interface

Every `case.py` exposes the same functions, so the harness treats all eight cases alike.

```text
slices()                        -> list of slice names
plan(rng, slice)                -> Plan      the answer and surface forms, decided first
generator_prompt(plan)          -> str       instructions for writing the input
verify(plan, text)              -> ok, why   planned strings present, nothing extra
label(plan)                     -> Expected  deterministic expected output
score(expected, output)         -> Score     pass, secondary scores, failure categories
legacy_markers()                -> list      patterns that make the legacy prompt "old"
```

### Records

```text
item    case, id, split, slice, input, expected, plan_seed, dataset_version
run     run_id, case, phase, model, effort, api, settings, prompt_hash, seed, git_commit, started_at
result  run_id, item_id, raw_output, parsed, valid, tokens_in, tokens_cached, tokens_cache_write,
        tokens_out, tokens_reasoning, latency_ms, cost_usd, error_code
score   run_id, item_id, passed, secondary, categories
```

### Commands

- `make setup`: environment, pinned dependencies, and a check that the API key works.
- `make check-models`: confirm every model ID and its supported efforts, and write `config/models.yaml`.
- `make data CASE=01`: build, verify and seal one case.
- `make calibrate CASE=01`: tune and freeze the legacy prompt on the source model.
- `make sweep CASE=01`: the legacy prompt across the source setup and every target.
- `make loop CASE=01 TARGET=gpt-6-luna SEED=11`: one loop run.
- `make final`: the only command allowed to read `data/sealed/`.
- `make report`: rebuild REPORT.md and the charts from `runs/`.
- `make reproduce CASE=03`: a clean end-to-end rerun of one case.
- `make status`: spend so far, phases done, runs in progress.

### Runner requirements

- **Cache:** key every response by a hash of model, API, settings, prompt and item, so reruns cost nothing.
- **Concurrency:** async, with a per-model limit from config. Start at 20 parallel requests and slow down on `slow_down` errors.
- **Errors:** branch on `error.code`. Retry rate limits and `server_is_overloaded` with exponential backoff and jitter, honour `Retry-After`, and stop the phase on billing errors.
- **Cost:** compute each call's cost from its token usage and the price table, counting cached and reasoning tokens.
- **Budget guard:** estimate a run's cost before starting it, and refuse if it would exceed the phase cap in `budget.json`.
- **Raw first:** store every raw response before parsing it.
- **Caching:** put the stable prompt first, and log `cached_tokens` and `cache_write_tokens`.

**Dependencies:** Python 3.12 with uv; the official `openai` SDK pinned to a release at least two weeks old; numpy, scipy, pandas, duckdb, matplotlib and pytest. Nothing else needs credentials.

## Overnight runbook for Claude Code

Everything Claude Code needs to work through the benchmark unattended over two nights: the setup you do first, the kickoff message, the rules file, the phases with their definitions of done, and your morning checklist. Night one stops after the sweep by design, so you can check the scorers before the expensive phases.

### Before you start (you, about 30 minutes)

1. **Dedicated OpenAI project.** Create a new project for the benchmark with a hard spend limit of $800 and its own API key. Put the key only in the agent's environment, as `OPENAI_API_KEY`.
2. **Isolated workspace.** Run Claude Code in a separate folder, ideally inside a container or VM, with no production code, credentials or access present. If you let it run without permission prompts, do that only inside this sandbox.
3. **Rate limits.** Look up the project's rate limits per model and put them in `config/models.yaml` as concurrency caps.
4. **Files in place.** Export this brief as `PLAN.md` into an empty repository, and create `CLAUDE.md` from the rules below.
5. **Stop time.** Set it to 06:30 Stockholm time in `budget.json`.

### Kickoff message, night one

```text
Read PLAN.md in full, then CLAUDE.md. Work through the runbook phases P0 to P4 in order,
starting from the first phase whose definition of done is not yet met.
Do not ask me anything: make reasonable decisions and record them in PROGRESS.md under "Decisions".
After each step, run its checks, commit, and append a dated entry to PROGRESS.md.
Work the cases in this order: 01, 03, 06, 02, 05, 07, 04, 08.
If a case is blocked, log why, skip it and continue with the next.
Respect budget.json and the stop time. Stop when P4 is done for every case.
Before stopping for any reason, run `make report` and write a short summary at the top of REPORT.md.
```

**Night two:** the same message, with "P0 to P4" changed to "P5 to P7" and "Stop when P4 is done" changed to "Stop when P7 is done".

### CLAUDE.md rules

- **Sealed data.** Never read, print or summarise anything in `data/sealed/` outside `make final`. Log every access to that folder.
- **Frozen files.** Once a case is sealed, never edit its `spec.md`, labeller or scorer. If you find a bug, log it, bump the case's dataset version and rebuild that case from scratch.
- **Protocol.** Never edit `PROTOCOL.md` after the first sweep call. Never weaken a threshold or a test to make something pass.
- **One path to the API.** Every call goes through `harness/runner.py`, so caching, retries, cost tracking and the budget guard always apply.
- **Commits.** Commit after every step and every loop run, with a message naming the case, phase and result.
- **Errors.** Back off on API errors. After three failed attempts at the same step, log it, skip it and move on.
- **Secrets.** Never write keys or tokens to logs, commits or reports.
- **Time.** Start no new loop run within 60 minutes of the stop time. Use that hour to finish runs in progress and write the report.
- **Decisions.** When the brief is ambiguous, choose the simpler option, record it in PROGRESS.md under "Decisions", and keep going.

### Phases

| Phase | Work | Definition of done | Budget cap |
| --- | --- | --- | --- |
| P0 Setup | Repository skeleton, environment, Makefile, model check, price table | `make check-models` lists every model ID with its supported efforts; the budget guard has tests | $2 |
| P1 Harness | Runner, cache, statistics, storage, report skeleton and a stub case | Unit tests pass on recorded responses; a five-item dry run works end to end | $5 |
| P2 Cases | Per case: spec, reference labeller, scorer with 15+ fixtures, generator, data build, sealing | Tests pass; drop rate under 20%; hashes in `MANIFEST.json`; stats file written | $80 |
| P3 Calibrate | Tune each legacy prompt on the source model, train only, at most four rounds; then freeze it | Dev score at or above the floor; legacy markers present; prompt hash frozen | $50 |
| P4 Sweep and port | `PROTOCOL.md` committed first. Legacy prompt on dev for the source and every target setting; mechanical port; effort choice | Sweep table per case; chosen effort per target recorded | $130 |
| P5 Loops | Luna and Terra: 8 cases × 3 seeds. Sol: cases 1, 3 and 7 × 3 seeds. Dataset v2 runs for cases 1 and 5 | Every run has a manifest, round log, rejection log and passed leakage checks | $300 |
| P6 Final | Unseal once. Test and shift sets for the legacy setup, mechanical ports and every optimised prompt; three stability repeats for finalists | Final tables, with verdicts computed exactly as `PROTOCOL.md` states | $205 |
| P7 Report | REPORT.md, charts, the reproducibility verdict, and a clean rerun of case 3 on Luna only, to keep it cheap | `make report` rebuilds everything from `runs/`; the clean rerun lands within 2 points | $25 |

The caps add up to $797, just under the project's $800 limit.

### Your morning checklist (about 20 minutes)

1. Read the summary at the top of REPORT.md and the Decisions list in PROGRESS.md.
2. Spot-check 10 items per case: input, expected output, model output and score. You are checking the scorer, not the model.
3. Compare spend in `make status` with the OpenAI project's usage page.
4. Check the sealed-data access log. Only `make final` should appear, and only after night two.
5. Check calibration: every legacy prompt is above its floor and genuinely reads as old.
6. Decide: continue, rebuild a case as a new dataset version, or raise a cap.

### When something goes wrong

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Spend rising faster than estimated | Longer outputs or more reasoning tokens than assumed | The runner pauses at the cap. Update the token assumptions, or drop Astra from the shift sets in P6 |
| A case drops more than 20% of items | Generator prompt too loose | Fix the generator and rebuild the case before sealing |
| A legacy prompt can't reach its floor | Task too hard or spec ambiguous | Simplify the spec; if it still fails, drop the case, log it and continue with seven |
| Many 429 errors | Concurrency above the project's limits | Lower the concurrency caps in config |
| The loop accepts nothing in a case | High bar or a weak optimiser | Expected for some cases. Report it; never loosen the rule afterwards |
| A scorer bug found after sealing | — | New dataset version for that case and rerun its phases. Keep the old runs and say so in the report |

## Cost and timeline

About $760 in API spend over two nights, inside a hard $800 limit on the project.

**Assumptions:** an average of 1,500 input and 300 output tokens per call, reasoning included, at the prices on [OpenAI's pricing page](https://developers.openai.com/api/docs/pricing). `gpt-5.6-sol` is assumed at $4 / $20 per million tokens; confirm it, since OpenAI notes its promotional pricing ends on 30 November 2026. Terra and Luna run on Flex. After P4, the agent replaces these assumptions with measured token counts and re-estimates the rest.

| Stage | API calls | Estimated cost |
| --- | --- | --- |
| Data generation and verification: 8 cases × 770 items, plus 30% spare | \~16,000 | \~$70 |
| Legacy calibration on gpt-5.6-sol | \~3,800 | \~$45 |
| Sweep: 9 settings × 200 dev items × 8 cases | 14,400 | \~$120 |
| Loops on gpt-6-luna: 24 runs | \~67,200 | \~$10 |
| Loops on gpt-6.1-terra: 24 runs | \~67,200 | \~$100 |
| Loops on gpt-6.2-sol: 9 runs | \~25,200 | \~$150 |
| Optimiser calls (gpt-6.2-sol at effort high) | \~285 | \~$20 |
| Final evaluation and stability repeats | \~44,000 | \~$200 |
| Dataset v2 runs and the clean rerun | \~10,000 | \~$40 |
| Total | \~248,000 | \~$760 |

**Throughput:** about 160,000 loop calls, mostly to Luna and Terra. At 600 requests a minute that is roughly 4.5 hours, so night two fits if the project's rate limits allow it. If not, the agent picks up from the last completed run the next night.

**Ways to spend less:**

- **Drop the Sol loops** (about $150) and treat Terra as the main-tier proxy.
- **Use two seeds instead of three,** at the cost of weaker reproducibility evidence.
- **Skip Astra on the shift sets** in the final phase.
- **Cache the stable part of each prompt;** cached input is a small fraction of the uncached price.

### Timeline

1. **Evening one:** your 30-minute setup, then the kickoff.
2. **Night one:** P0 to P4.
3. **Morning one:** your checklist, then fix or approve.
4. **Night two:** P5 to P7.
5. **Morning two:** your checklist, then read REPORT.md.
6. **Days three and four:** write-up, charts and publishing.


## What to publish

One write-up of 1,500–2,000 words, one public repository with all data, and a short list of observations for OpenAI. Working title: *Is prompt migration to GPT-6 reproducible? Eight legacy prompts, four models, three seeds each.*

### Write-up outline

1. **The short version:** the answer to each of the four questions, with one number each.
2. **The eight cases:** what each tests and why a GPT-5.6-era prompt might break on it.
3. **What broke on the swap:** zero-shot drop per case and model, with one example of each failure type.
4. **The method:** plan-first data, sealed splits, the loop and the rules fixed in advance.
5. **Did the loop fix it?** Recovery per case and target.
6. **Is it reproducible?** Seed spread, verdict agreement, the data-version check, shift gaps and the clean rerun.
7. **Cost per correct answer** before and after, per model.
8. **Advice for teams migrating:** five lessons, each backed by a result.
9. **Observations for OpenAI:** each with a minimal reproduction.
10. **Limitations:** synthetic inputs, model-written data, sample sizes.
11. **Reproduce it:** repo link and the commands to rerun.

### Four charts

- **Zero-shot drop:** a grid of cases by target, one value per cell.
- **Recovery with spread:** per case and target, the mean recovery across seeds, with the seed range marked.
- **Cost against score:** cost per correct answer against primary score for every final configuration, with the frontier marked.
- **Loop progress:** dev score by round for each seed, with accepted and rejected candidates marked.

### The repository

Everything goes public once the final phase has run: harness, cases, specs, generators, all splits including test and shift, prompt histories, run manifests and results. Because the data is synthetic, nothing needs holding back, and anyone can check every number.

### Observations for OpenAI

Write each as observation, minimal reproduction, impact and suggestion. Candidates to check during the runs, to verify rather than assume:

- Clarifying questions or Markdown in strict extraction and routing tasks.
- Over-abstention on "NEVER"-style instructions in case 6.
- Whether simplified prompts beat accumulated ones across models (case 7).
- What replaced logprob-based confidence best (case 2), and what developers lose without it.
- Run-to-run variance now that temperature is gone.

## Risks and guardrails

The main risks come from running an agent unattended: runaway cost, quietly broken scorers, and an agent that "fixes" tests to make them pass. Each has a guardrail built into the plan.

| Risk | Guardrail |
| --- | --- |
| The agent runs up cost | A dedicated OpenAI project with a hard $800 limit, plus per-phase caps enforced by the runner |
| The agent edits tests or thresholds to pass | CLAUDE.md forbids it, git history shows any attempt, and the morning checklist looks for it |
| Scorer bugs skew results quietly | 15+ fixtures per scorer, plus your spot-check of 10 items per case each morning |
| The agent touches production systems | A separate machine, container or VM with its own key and no production credentials present |
| Synthetic tasks feel artificial | Calibration floors, legacy markers, shift sets and an honest limitations section |
| Model-written inputs favour OpenAI models | Disclosed in the write-up; checked against the shift sets with unseen templates |
| Data leaks into prompts | Automated six-word-sequence and answer-string checks on every candidate |
| Models change mid-study | Pin model IDs, record dates, and finish both nights within one week |
| Results are underpowered | Sizes are stated with what they can detect; double them for a publication-grade rerun if results are close |

## Sources

Checked on 17 November 2026. Model names and prices change often, so recheck them before the sweep.

- [Using GPT-6: model guide](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra), OpenAI
- [API deployment checklist](https://developers.openai.com/api/docs/guides/deployment-checklist), OpenAI
- [Pricing](https://developers.openai.com/api/docs/pricing), OpenAI
- [Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra), OpenAI developer blog
- [GPT-6 Astra API: breaking changes to fix before you migrate](https://byteiota.com/gpt-6-astra-api-migration/), byteiota
- [Re-test AI skills after a model update](https://www.singlegrain.com/artificial-intelligence/retest-ai-skills-after-model-update/), Single Grain

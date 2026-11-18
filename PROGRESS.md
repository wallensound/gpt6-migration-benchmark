# PROGRESS

Append-only log. Newest entries at the bottom.

## Decisions

- **D1 (2026-11-18) Providers.** OpenAI's own API is not available to this project. All GPT-6 targets, the data generator, the verifier, the failure labeller and the optimiser run on AWS Bedrock's OpenAI-compatible endpoint (`bedrock-runtime.eu-north-1`, `global.openai.*` inference profiles), which supports Chat Completions and the Responses API. The legacy source model runs on Azure OpenAI (`gpt-5.6-sol-2026-07-09`, deployment `gpt-5.6`), because Bedrock accepts `logprobs` but returns `null`, and case 2's legacy setup needs them.
- **D2 Prices.** Costs are computed from the brief's price table (OpenAI list prices; Flex for Terra and Luna; gpt-5.6-sol at the assumed $4 / $20), not from Bedrock or Azure invoices. Cached input is priced at 0.1x input and cache writes at 1.25x.
- **D3 Stop time.** The owner asked for one continuous run until the whole brief is done, so `budget.json` has no stop time and the two morning checkpoints are replaced by the agent's own spot-checks, logged here.
- **D4 SDK.** `openai==3.45.0` (released 2026-11-04, the newest release at least two weeks old on 2026-11-18).
- **D5 Cache TTL.** Bedrock only accepts `prompt_cache_options.ttl = "30m"`.

## Log
- **D6 numpy pin.** numpy 2.5.5's `_pocketfft_umath` DLL is blocked by this machine's Windows Application Control policy; numpy is pinned to 2.3.5, which loads.
- **D7 Output-token caps in the port.** The mechanical port keeps a legacy output-token cap only at effort `none`. With reasoning on, reasoning tokens count against `max_output_tokens`, so a 5-token cap would guarantee empty output.
- **D8 Sweep = mechanical port per setting.** At every target setting the sweep sends the literal legacy request once (to record which legacy parameters are rejected), then scores the mechanical port of the legacy prompt on dev. The zero-shot numbers are therefore "legacy prompt, minimum forced API changes".
- **D9 Flex.** Bedrock rejects `service_tier: flex` (Terra, Luna) and errors on it for Sol/Astra, so all calls use the default tier; costs still use the brief's Flex prices for Terra and Luna (D2).

### 2026-11-18 P0 Setup: done
- Repo skeleton, uv environment (Python 3.12.10, openai 3.45.0), Makefile, config, budget.json.
- `make check-models`: all five models answer. Efforts: gpt-5.6-sol none/low/medium/high/xhigh (Azure, `gpt-5.6-sol-2026-07-09`); gpt-6.2-astra and gpt-6.2-sol low..max (no `none`); gpt-6.1-terra and gpt-6-luna none..max. GPT-6 rejects `temperature` when effort is not `none`; Bedrock returns no logprobs for GPT-6; `text.format`, `text.verbosity` and `prompt_cache_options.ttl=30m` accepted everywhere.
- Budget guard has tests (refuses an over-cap estimate; stops a run at the cap).

### 2026-11-18 P1 Harness: done
- Runner (cache, adaptive concurrency, retries, error-code branching, cost, budget guard, raw-first), requests (chat/responses, mechanical port), evaluate + run storage, stats (Wilson, bootstrap, McNemar, Holm, non-inferiority, flip rate), data gate, generate pipeline, entities.
- 18 unit tests pass on recorded responses. Five-item dry run (stub case) works end to end: 5 generated, 0 dropped, source 5/5, Luna port 5/5, $0.002.

### 2026-11-18 P2+P3 case 03 ticket routing: sealed and frozen
- 1001 planned, 992 kept (drop 0.9%), splits 120/200/300/150, $2.22 data. 41 tests.
- Calibration: one train round (95.8%), dev 94.5% (floor 90%), prompt hash c48d9074a9274e6a.
- **D10 (case 03) shift.** The prompt is fixed, so "label definitions paraphrased" is realised as paraphrased cue wordings in the messages, plus a new product domain (e-bike subscription) and unseen brands.
- **D11 (case 03)** a "first issue mentioned wins" fallback after the three tie-break rules gives multi-issue items a defined answer; `answer_strings` is empty (labels are part of the contract); the port raises a sub-16 output cap to 16 (Responses API minimum; only relevant at effort `none`).
- **D12 Azure content filter.** Azure's content filter blocks a small share of source-model calls (2 of 200 case 03 dev items). They are scored as failures (`api_error`) of the source setup, as a production integration would experience them.

### 2026-11-18 P2+P3 case 07 contact normalisation: sealed and frozen
- 1001 planned, 961 kept (drop 4.0%), splits 120/200/300/150. 33 tests. Legacy train 99.2%, dev 99.5% (floor 90%), one round, hash ebbe139d619e0122.
- **D13 (case 07)** the generator writes only the notes around a `<<RECORD>>` placeholder and code inserts the exact messy record, so the record is verbatim by construction; verify still rejects notes containing emails, URLs, long numbers, country names or names. Conflict: rule 2 / IMPORTANT block ("NEVER guess or infer") vs rule 16 (infer the country from the calling code when missing); the precedence note says rule 16 wins. +1 and +7 never set a country. Shift: 12 unseen countries and unseen phone formats in 60% of items.
- Spot-check (agent): 8 dev items read; labels and slices correct; the single dev miss is a genuine "Last, First" reorder error.

### 2026-11-18 P2+P3 case 04 tool selection: sealed and frozen
- 1001 planned, 961 kept (drop 4.0%), splits 120/200/300/150. 25 tests. Legacy train 100%, dev 99.0% (floor 90%), one round, hash df7e39915955f900.
- **D14 (case 04)** "next <weekday>" = that day in next week (23-29 Nov 2026); "on/this <weekday>" = first such day after today; a clock time means `create_event`, no clock time `create_task`; with two candidate values the last correction wins and a work address beats a webmail address; optional arguments must be omitted unless given (documented defaults tolerated); free text (`body`, `notes`) not scored. Shift: `create_task` -> `add_todo`, `search_docs` -> `query_knowledge_base` with reworded descriptions, Swedish requests, unseen companies; the legacy prompt still names the old tools (part of the shift test).
- **Known data limitations (case 04).** (a) The LLM verifier wrongly dropped about 20 `log_call` items phrased "spoke with / talked to" (outcome `connected`), so that phrasing is under-represented; labels are unaffected. (b) Spot-check found one dev item (of 200; 0 of 120 train) where the generator put a comma inside the closing quote of a title (`"Prepare the board slides,"`); the label follows the plan (no comma) and the spec only strips `. ! ?`, so a model that copies the comma fails. This is a generation artefact rather than a scorer bug, affects every setup equally and about 0.5% of items, so the case is not rebuilt (simpler option); it is listed as a limitation.

### 2026-11-18 P2+P3 case 02 invoice fields: sealed and frozen
- 1001 planned, 997 kept (drop 0.4%), splits 120/200/300/150. 43 tests. Legacy train 100%, dev 100% (floor 90%), one round; frozen hash 96525dff10409f06.
- **D15 (case 02)** amounts are compared as decimals (strings with two decimals expected; numbers and one-decimal strings accepted; separators or currency in the value make it wrong); numeric dates are day-first; vendor is the full legal name. Flag methods: `logprob` (mean logprob of the value's characters), `null_when_unsure`, `confidence_field` (extra `confidence` object, allowed only under that method), `two_run_agreement` (samples=2, flag disagreeing fields). The port maps `logprob` to `none`. Flag metrics pool valid outputs only.
- **D16 (case 02) flag threshold.** The source model made no field errors on train, so the threshold could not be tuned for flag F1; field mean logprobs sit at about 0 with noise near 1e-5. Rule used: the highest power-of-ten threshold that flags no train field (-0.01). The legacy logprob flags therefore catch nothing here (1 false flag on dev); comparisons of flag methods rest on target-model errors.
- Limitation: the source model is at the ceiling (100%), so zero-shot drop and recovery are measured against a ceiling.

### 2026-11-18 P2+P3 case 08 glossary translation: sealed and frozen
- 1001 planned, 879 kept (drop 12.2%: 80 LLM verifier, 42 code verify), splits 120/200/300/150. 36 tests. Legacy train 99.2%, dev 98.0% (floor 85%), one round, hash 7b55c35e98c0471c.
- **D17 (case 08)** reference length = Swedish source word count x 1.15 (pass band 0.8-1.4x); matching is case-insensitive with word boundaries, hyphens/dashes as spaces, and only last-word inflections +s/+es/y->ies/drop-s; forbidden alternatives are checked for planned terms only; preambles ("Here is ...") and "Note:" lines fail as not plain text; shift items get the 20-term extension as item context and the legacy prompt says to apply an "Additional glossary".
- **Limitation (case 08), from the spot-check.** Adverbial Swedish forms such as "trådlöst" are naturally rendered "wirelessly", which the frozen matching rule does not accept as "wireless"; the inflected-forms slice therefore tests strict glossary wording, not just meaning. Common-word renderings ("case", "mode") can pass by accident, and a forbidden word used in an unrelated sense fails an item.

### 2026-11-18 P2+P3 case 01 entity extraction: sealed and frozen
- 1001 planned, 984 kept (drop 1.7%), splits 120/200/300/150; shift inputs ~815 tokens vs ~366 main. 69 tests. Legacy train 99.2% (the one failure is an Azure content-filter rejection), dev 99.5% (floor 90%), one round, hash 7b4c50e8226a4ca4.
- **D18 (case 01)** duplicates in the output fail (rule 10) even when the set is right; first-mention order (rule 11) is requested but not scored; names compare after NFC and whitespace trimming only; domain-only and product-phrase mentions are planned only for one-word names; possessives "X's" only in English items (the spec still tells the model to strip Swedish/German genitive -s); no other organisations (banks, media, agencies) may appear; shift paragraphs are 2-3x the planned main length with the unseen company pool.
- Spot-check: 4 dev items read, labels correct; the single dev miss keeps a Swedish genitive ("Velplums").

### 2026-11-18 P2+P3 case 06 grounded abstention: sealed and frozen
- 1001 planned, 997 kept (drop 0.4%), splits 120/200/300/150 (35% unanswerable). 38 tests. Legacy train 100%, dev 100% (floor 90%), one round, hash bc5d1392c1fcda7c.
- **D19 (case 06)** the question is a separate item field; the user message is `CONTEXT: ... QUESTION: ...` with English labels for every language; `NOT_FOUND` is case-sensitive and only surrounding whitespace and one trailing period are tolerated; answers match on diacritic-folded whole tokens (units and answer language not scored); an answer that also contains a look-alike's value fails; any `?` counts as a clarifying question. People and products have no shift pool, so only companies are unseen in the shift set; all unanswerable shift items are of the "look-alike has it" kind.
- Limitation: the source model is at the ceiling (100%), so the case can only show regressions.
- Spot-check: 6 dev items read (EN/SV/DE), labels and contexts correct.

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

### 2026-11-18 P2+P3 case 05 format summary: sealed and frozen
- 1001 planned, 974 kept (drop 2.7%), splits 120/200/300/150; inputs ~920 tokens main, ~2,560 shift. 34 tests. Legacy train 99.2% (the one failure is an Azure content-filter rejection), dev 100% (floor 85%), one round, hash 541bc181051a4a52.
- **D20 (case 05)** key numbers are integers 40-85,000 outside 2000-2100; key dates are days 1-28 between Dec 2026 and Jun 2028; numbers match by value ignoring thousands separators; dates match day and month (plus year if given) in English, Swedish or ISO form; names need the full name (case and diacritics folded); exactly three lines (blank lines fail); a summary with two or more Swedish function words fails as `wrong_language`; the shift set omits `long_articles` (every shift article is long); `make_input` normalises non-breaking spaces and strips Markdown from generated articles.
- Limitation: the source model is at the ceiling (100%).
- Spot-check: 3 dev items read (incl. Swedish source), labels correct.
- **D21 Budget reallocation (2026-11-18).** After P4, measured spend was far below the brief's estimates (P2 $36 of $80, P4 $43 of $130), while the final evaluation is estimated above its cap (~$220 vs $205, driven by Astra on long shift inputs). Caps changed to P2 $45, P4 $70, P6 $300 (P2 and P4 had finished); the sum of caps stays $797 and the $800 total limit still applies. This is the "raise a cap" option from the brief's checklist, chosen over skipping Astra on the shift sets so that P6 runs exactly as PROTOCOL.md states.

### 2026-11-18 P4 Sweep and port: done (all 8 cases)
- PROTOCOL.md committed (4756990) before the first sweep call; `runs/protocol_lock.json` holds its hash.
- Every case's legacy prompt on the source setup and all 8 target settings on dev, plus the literal-swap probe. Literal swap fails everywhere: `temperature` is rejected when reasoning is on, a 5-token cap is below the Responses minimum of 16, and `logprobs` are not supported with reasoning models.
- Zero-shot (mechanical port, dev): only case 07 breaks substantially (Terra none 55.5%, Sol 80-84%, Luna none 79%, vs 99.5% legacy); case 08 drops slightly on Luna/Terra (95.5-97.5% vs 98.0%); cases 01-04 and 06 port at or above the legacy score.

### 2026-11-18 P5 Loops: done
- 59 runs: Luna and Terra x 8 cases x seeds 11/22/33, Sol x cases 01/03/07 x 3 seeds, dataset v2 for cases 01 and 05 (generation seeds 2001 and 2005, drop 1.1% and see stats) with one Luna seed-11 loop each. No run failed; every final prompt passed the leakage check.
- The loop accepted candidates only in case 07 (Terra 55.5% -> 98.5-99.0% dev on all seeds; Sol 83.5% -> 97.0-100%); everywhere else the port was already at the ceiling and the loop stopped after two empty rounds, as the acceptance rule intends.
- Sealed-data access log before P6: 20 entries, all `write(generate)` from the data builds; no reads.
- Spend so far $141 (P2 $36, P3 $10, P4 $44, P5 $51).

### 2026-11-18 P6 Final: done
- `make final` run once, as eight parallel per-case processes (`harness.cli final --case NN`, BENCH_FINAL=1); an initial single-process start was stopped after two evaluations and resumed (evaluations already stored are skipped, so nothing ran twice). 302 evaluations: source, 4 ports and every optimised prompt on test and shift, three test repeats for source, ports and seed-11 optimised prompts. Nothing skipped for budget; P6 spend $108.
- Bug fixed in the analysis only (`final.analyse`): the stability calculation indexed dataset-v2 configurations with v1 item ids and crashed after all evaluations were stored; no evaluation was rerun.
- **D22 Seed spread caveat.** Where the loop accepted nothing, all three seeds return the identical (ported) prompt; identical requests are served from the response cache, so their test results are identical and the seed spread is 0 by construction. Run-to-run variance of the models is measured separately by the three-repeat flip rate (stability), which the report shows next to the seed spread.
- Headline: Partly reproducible (seed repeats pass 8/8 Luna, 7/8 Terra; data-version check passes; across-cases fails: Luna migrated in 4 of 8; main-tier fails on case 07; clean rerun pending).

### 2026-11-18 P7 Report: done
- Clean rerun (`scripts/clean_rerun.sh`): fresh clone of the repo, empty cache (`cache_was_empty: true`), `make reproduce CASE=03` on Luna seed 11: tests pass, loop accepts nothing as in the reported run, final test score 95.3% vs 94.7% reported (diff +0.7 points, threshold 2) -> pass. Cost $0.09, recorded in the clone's own ledger (not in this repo's `make status`).
- `make report` rebuilds `runs/bench.duckdb` (1,198 evaluations, 177,285 scored responses), REPORT.md and the four charts (zero-shot drop, recovery with seed range, cost against score, loop progress per target) from `runs/`. Charts were rendered and checked by eye (title clipping, legend overlap and y-ranges fixed).
- Overall verdict per PROTOCOL.md: **Reproducible** (seed repeats 8/8 Luna, 7/8 Terra; data version and clean rerun pass), with the across-cases check (Luna 4/8) and main-tier check (case 07) failing; caveats in REPORT_SUMMARY.md and D22.
- Write-up `docs/writeup.md` (1,949 words), observations for OpenAI and limitations in `report/observations.md`. `make all` added for an end-to-end rerun.
- Total spend $249.48 (+$0.09 clean rerun) of the $800 limit. 126 tests pass.

### 2026-11-23 Publication preparation
- **D23 Provider-agnostic configuration.** Providers and model IDs now come from the environment (`.env`, see `.env.example`): OpenAI's API by default, or Azure OpenAI, AWS Bedrock or any OpenAI-compatible gateway, per model if needed. Model IDs for this study's setup are unchanged, so every cached response and result still applies.
- **D24 Added after the protocol:** `make import` (bring your own examples instead of generating them, `cases/_template-byod/`) and `make recommend` (per case, the cheapest setup that is non-inferior to the legacy setup on dev, confirmed once on test, with a fallback when the dev pick fails on test). Neither changes a PROTOCOL.md verdict. Smoke-tested end to end in a fresh clone on 320 imported tickets ($4.95).
- **D25 History rewritten once before publication.** Private planning notes were removed from the brief (PLAN.md now holds the cleaned design brief) and from every earlier commit, and an account-specific endpoint name was replaced. Short hashes cited in run manifests and in this log refer to the pre-rewrite commits; `docs/commit-map.txt` maps them to the published ones (e.g. the PROTOCOL.md commit 4756990).

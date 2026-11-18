# Writing a case

Each case lives in `cases/<nn-name>/` and is self-contained. Read `PLAN.md` first: the section
"Rules for every case", your case's section, and "Building the data". The brief is binding.

## Files

```text
cases/<nn-name>/
  spec.md               rules, output contract, every edge-case decision. Single source of truth.
  legacy_prompt.md      the GPT-5.6-era prompt (system message), with the case's legacy markers
  legacy_config.yaml    model / api / effort / settings of the legacy setup
  case.py               the interface below
  tests/test_case.py    >= 15 labeller + scorer fixtures covering every slice, plus a legacy-marker test
```

`legacy_config.yaml` looks like:

```yaml
model: gpt-5.6-sol        # the source model (Azure; Chat Completions)
api: chat
effort: none
settings:
  temperature: 0
  max_output_tokens: null # e.g. 5 for case 3
  structured_outputs: false   # true = response_format json_schema from case.schema(settings)
  logprobs: false
  # case-specific keys are allowed (e.g. flag_method, flag_threshold for case 2)
```

## The interface (`case.py`)

See the docstring of `harness/cases.py` and the minimal example `tests/stub_case/case.py`.

```text
CASE_ID = "01"; NAME = "..."
slices() -> list[str]                    main-set slices
shift_slices() -> list[str]              optional; slices for the shift set (default: slices())
slice_weights(variant) -> dict|None      optional; relative share of each slice (default: equal)
plan(rng, slice, variant) -> dict        decide the answer and the surface forms first. variant is "main" or
                                         "shift". JSON-serialisable. Use only `rng` (a seeded random.Random).
generator_prompt(plan) -> str            instructions for gpt-6.2-sol (effort low) to write the input text
make_input(plan, text) -> str            optional; post-process the generated text into the item input
item_extras(plan) -> dict                optional; extra item fields, e.g. {"tools": [...]} or {"context": "..."}
verify(plan, text) -> (ok, why)          code check: every planned string present verbatim, nothing extra
verifier_brief(plan) -> str              tells gpt-6-luna what the answer is and what would change it
label(plan) -> expected                  deterministic, from the plan only (never from the text)
user_message(item, settings) -> str      optional; default: item["input"] (+ "\n\n" + item["context"])
tools(item, settings) -> list|None       optional; neutral tool defs {name, description, parameters}
schema(settings) -> dict|None            optional; JSON schema for Structured Outputs (root must be an object;
                                         strict mode: every property required, additionalProperties false)
SCHEMA_NAME = "..."                      optional
parse(output, settings, item) -> parsed  output = {"text", "tool_calls":[{name, arguments}], "logprobs", "status",
                                         "refusal"} (a list of these when settings["samples"] > 1).
                                         Must never raise: return something the scorer marks invalid.
score(expected, parsed) -> dict          {"passed": bool, "valid": bool (obeys the output contract),
                                          "nonanswer": bool (clarifying question, refusal, empty),
                                          "secondary": {numeric per-item values}, "categories": [taxonomy labels
                                          for failures], "diff": "short code diff expected vs got"}
aggregate(rows) -> dict                  optional; case-level secondary scores from the result rows
                                         (each row has "passed", "valid", "nonanswer", "secondary", "slice", ...)
failure_taxonomy() -> list[str]          categories the failure labeller may use
settings_space() -> dict                 optional; settings the optimiser may change and their allowed values
                                         (default: verbosity, and structured_outputs if schema() exists)
port_settings(settings) -> dict          optional; extra forced changes in the mechanical port (case 2: logprob
                                         flags cannot survive, so flag_method -> "none")
answer_strings(expected) -> list[str]    optional; strings the optimiser must never put in a prompt
legacy_markers() -> list[str]            regexes; every one must match legacy_prompt.md
```

Rules that apply to every case:

- **Plan first.** The answer is decided in `plan` before any text exists; `label` reads only the plan.
- **Reference date.** Anything needing "today" uses 17 November 2026 (a Tuesday) and the prompt says so.
- **Invented entities.** Use `harness.entities`: `companies(pool="main")` (1,500), `companies(pool="shift")`
  (500 unseen ones, for shift sets), `people()` (500), `products()` (300). Real cities and countries are fine.
- **Languages.** Cases 1, 2, 3 and 6: about 20% Swedish and 10% German items (case 8: Swedish to English).
- **Shift set.** `variant == "shift"` gives the distribution change listed in PLAN.md for the case.
- **Generator prompts** must demand every planned string verbatim, forbid extra entities or values that would
  change the answer, ask for plain output only, and vary style using the plan (seeded) so items are not
  near-duplicates (character 5-gram Jaccard > 0.8 are dropped).
- **Scorer robustness.** Normalise exactly as the spec says, nothing more. Markdown fences, prose around the
  answer, clarifying questions and refusals are failures, classified via `valid` / `nonanswer` / categories.
- **Legacy prompt.** Realistically old: it must contain the case's legacy patterns (all-caps NEVER/ALWAYS,
  "be concise", embedded glossary, IMPORTANT block, etc., per PLAN.md) and still work well on gpt-5.6-sol.
  Do not deliberately sabotage it for GPT-6; write it the way a 2025-2026 team would have.

## Workflow and commands

All commands run from the repo root in Git Bash. `make` lives at
`$LOCALAPPDATA/Microsoft/WinGet/Packages/ezwinports.make_Microsoft.Winget.Source_8wekyb3d8bbwe/bin`
(prepend it to PATH), or call `.venv/Scripts/python -m harness.cli <cmd>` directly.

1. Write spec, case.py, tests. `.venv/Scripts/python -m pytest cases/<nn-name> -q` must pass (no API calls).
2. **Pilot** (cheap, throwaway; never part of any split):
   `.venv/Scripts/python -m harness.cli pilot <nn> --n 24` then read `data/pilot/<folder>/items.jsonl` and
   `dropped.jsonl`. Check inputs look natural, contain the planned strings and labels are right.
   `.venv/Scripts/python -m harness.cli pilot-eval <nn>` runs the legacy prompt on the pilot items.
   Iterate on generator, verify, spec and scorer until the pilot drop rate is well under 20% and the legacy
   prompt is near its floor. Repeat pilots are cheap (cached) only when nothing changed; keep it to a few.
3. **Build and seal**: `.venv/Scripts/python -m harness.cli data <nn>`. After this, `spec.md`, `label`, `score`,
   `parse` and their helpers are frozen (a fix means a new dataset version). It refuses if the drop rate > 20%.
4. **Calibrate** on the source model, at most four tuning rounds on train:
   `... calibrate <nn> --split train` -> read `runs/P3/<folder>/train-failures-<hash>.jsonl`, adjust
   `legacy_prompt.md` (keep it legacy-style, keep the markers). Then `... calibrate <nn> --split dev` (scores
   only) and, when dev >= floor (90%; 85% for cases 05 and 08), `... calibrate <nn> --freeze`.

## Hard rules

- Never read, open, print or summarise anything under `data/sealed/`. Never set BENCH_FINAL.
- Do not edit anything under `harness/`, `config/`, `budget.json`, other cases' folders, or `PROTOCOL.md`.
  If the harness blocks you, work around it inside your `case.py` and describe the problem in your report.
- Do not commit; the coordinator commits.
- Every model call goes through the harness commands above (no direct API calls).
- Keep spend modest: data build ~ $8-15 per case, pilots and calibration a few dollars.

## Bring your own data (no synthetic generation)

If you already have real examples with known-good answers, you can skip the plan -> generate -> verify ->
label steps entirely.

1. **Make the case folder.** Copy `cases/_template-byod/` to `cases/<nn>-<name>/` (e.g. `cases/09-my-task/`).
2. **Describe the task.** Fill in `spec.md` (what a correct answer is), paste your current production prompt
   into `legacy_prompt.md`, and set the model and settings it runs on today in `legacy_config.yaml`.
3. **Check the scorer.** The template's `score()` does exact text match, or JSON equality when the expected
   answer is JSON. Edit it only if "correct" needs looser rules (case, dates, numbers), and add a few
   fixtures to `tests/test_case.py`.
4. **Put your examples in a file.** Use CSV with a header, or JSONL, with one example per row:

   | column | required | meaning |
   | --- | --- | --- |
   | `input` | yes | what the model receives (the user message) |
   | `expected` | yes | the known-good answer; JSON such as `{"total": "12.50"}` or `["Acme"]` is parsed |
   | `slice` | no | a group name (e.g. `swedish`, `long`, `edge_case`) for per-slice scores and stratified splits |
   | `id` | no | your own id, kept as `source_id` |
   | anything else | no | copied onto the item; a `context` column is appended to the user message |

5. **Import.** Run `make import CASE=09 FILE=my_examples.csv`. Optionally add `SHIFT=newer_examples.csv`
   for a robustness set, such as later or harder examples the prompt was never tuned on.

   The import dedupes, splits (train 120 / dev 200 / test 300 when there are enough rows, otherwise the same
   proportions with at least ~110 rows), seals test and shift, and writes the hashes, stats and leakage index.

6. **Continue as for any case.** Run `make calibrate CASE=09`, then `calibrate-dev`, `freeze`, `sweep`,
   `loop` and `final`. The same rules apply: never read `data/sealed/`, and never edit the spec or scorer
   after importing; a fix means a new dataset version (`VERSION=2`).

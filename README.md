# GPT-6 migration benchmark

**Find out which GPT-6 model your prompt can move to, what breaks on the way, and how much you save.**

This repository does two things:

1. **A published study.** Eight realistic GPT-5.6-era prompts were moved to four GPT-6 models, repaired
   by an automated optimisation loop, and checked for reproducibility with three seeds each. Everything is
   in the repo: data, prompts, logs and results.
2. **A tool you can point at your own prompt.** Give it your current prompt and a file of examples with
   known-good answers. It tells you, per GPT-6 model, how much accuracy you keep, whether an automated
   rewrite fixes what broke, and which model is the cheapest one that holds up.

## What we found

| Question | Answer (see [REPORT.md](REPORT.md) and the [write-up](docs/writeup.md)) |
| --- | --- |
| How much breaks? | Usually little. In 7 of 8 tasks the old prompt lost at most 3.3 points after the API-forced changes. One task with piled-up, conflicting rules lost **42 points** on gpt-6.1-terra. |
| Does an automated loop fix it? | Yes, where something broke: 55% -> 99% on that task. Where nothing broke it changes nothing. |
| Is it reproducible? | Yes by the pre-registered checks (seeds, a regenerated dataset, a clean rerun), with caveats in the report. |
| What does it save? | The cheapest model that holds accuracy is **2-100x cheaper per correct answer** than the old setup. |

Which model each task should move to (cheapest setup that is no worse than the old one, chosen on dev
and confirmed once on held-out test data; from `make recommend`):

| Task | Move to | Test accuracy (old setup) | Cheaper by |
| --- | --- | --- | --- |
| Entity extraction | gpt-6.1-terra, prompt ported as is | 99.0% (100.0%) | 2.3x |
| Invoice fields | gpt-6-luna, prompt ported as is | 100.0% (100.0%) | 105x |
| Ticket routing | gpt-6.1-terra, prompt ported as is | 97.7% (96.3%) | 8.0x |
| Tool calling | gpt-6-luna, prompt ported as is | 99.7% (99.0%) | 52x |
| Format-constrained summary | gpt-6-luna, prompt ported as is | 100.0% (100.0%) | 80x |
| Grounded answers | gpt-6-luna, prompt ported as is | 98.3% (99.7%) | 78x |
| Contact normalisation (conflicting rules) | gpt-6.1-terra, **loop-rewritten prompt** | 98.3% (99.3%) | 4.2x |
| Glossary translation | gpt-6.1-terra, prompt ported as is | 97.0% (96.7%) | 8.0x |

Costs use OpenAI list prices (November 2026).

## Use it on your own prompt

You need:
- Python 3.12, [uv](https://docs.astral.sh/uv/) and `make`. On Windows, use Git Bash and
  `winget install ezwinports.make`.
- An API key.
- **About 150-800 examples** of your task, each with its correct answer.

**1. Install and add your key**

```bash
git clone https://github.com/<you>/gpt6-migration-benchmark && cd gpt6-migration-benchmark
cp .env.example .env          # put OPENAI_API_KEY=... in it (Azure, AWS Bedrock or any
                              # OpenAI-compatible gateway also work; see .env.example)
make setup                    # installs dependencies and shows which provider each model will use
make check-models             # confirms every model ID and its reasoning efforts on your account
```

**2. Describe your task.** Copy the template and fill in three short files:

```bash
cp -r cases/_template-byod cases/09-my-task
```

- `spec.md`: what a correct answer is.
- `legacy_prompt.md`: your current production prompt, unchanged.
- `legacy_config.yaml`: the model and settings it runs on today.

The built-in scorer handles exact text answers (labels, short answers) and JSON answers (extraction). Edit
`score()` in `case.py` only if "correct" needs looser rules.

**3. Add your examples** as a CSV or JSONL file with an `input` and an `expected` column. An optional
`slice` column (e.g. `swedish`, `edge_case`) gives per-group scores.

```bash
make import CASE=09 FILE=my_examples.csv     # dedupes, splits, and locks away the test set
```

**4. Run it**

```bash
make calibrate CASE=09 && make calibrate-dev CASE=09 && make freeze CASE=09   # baseline on your current model
make sweep CASE=09                                       # your prompt on every GPT-6 model and effort
make loop CASE=09 TARGET=gpt-6-luna SEED=11              # automated repair, per model you care about
make loop CASE=09 TARGET=gpt-6.1-terra SEED=11
make final CASE=09                                       # one-time check on the locked test set
make recommend                                           # which model to move to, and the saving
make report                                              # full report with charts in REPORT.md
```

`freeze` expects your current prompt to score at least 90% on your examples. If it scores lower and you
still want the comparison, set its floor in `config/sizes.yaml` (e.g. `'09': 0.0`).

**What you get:**
- a table of accuracy and cost per correct answer for every model and effort;
- an improved prompt per model, where the loop found a provable fix, with its reasoning logged;
- a recommendation such as "move to gpt-6-luna; accuracy 99.7% vs 99.0%; 52x cheaper".

Every API call is cached, so reruns are free. A budget guard (`budget.json`) stops anything that would
exceed its cap.

## How it works

- **Locked test data.** Examples are split into train (used to repair the prompt), dev (used to accept
  changes) and test (opened once, at the end). Nothing tuned on test can leak into the result.
- **The repair loop.** It runs your prompt, groups the failures, and asks a strong model for four
  different kinds of rewrite. It keeps a rewrite only if it is significantly better on dev and no group of
  examples gets worse.
- **Rules fixed in advance.** Thresholds live in [PROTOCOL.md](PROTOCOL.md) and are locked by hash before
  any results exist.
- **Honest cost.** Every call's tokens (including reasoning and cached tokens) are priced from
  `config/models.yaml`.

Details:
- [cases/README.md](cases/README.md): writing or importing a case.
- [PLAN.md](PLAN.md): the full design.
- [PROGRESS.md](PROGRESS.md): every decision taken while building it.

## Reproduce this study

```bash
make test                 # unit tests, no API calls
make reproduce CASE=03    # clean rerun of one task on gpt-6-luna, compared with the reported number
make report               # rebuild REPORT.md and the charts from runs/
```

The study ran the GPT-6 models on AWS Bedrock and the legacy model on Azure OpenAI. To rerun everything
on your own account, move `runs/P4` to `runs/P7` and `runs/protocol_lock.json` aside, then run `make all`
(about $250 at list prices).

## Layout

```text
cases/        eight study tasks, plus _template-byod/ for your own
harness/      runner (API calls, cache, retries, cost, budget), loop, optimiser, statistics, report
config/       models.yaml (model IDs per provider, prices), sizes.yaml (split sizes, loop settings)
data/         examples (test and shift sets in data/sealed/), MANIFEST.json with SHA-256 hashes
runs/         every run: manifests, results, round logs, prompts
report/       charts and observations; REPORT.md is rebuilt by `make report`
```

## Limitations

- **Synthetic study data.** The study's examples were written by an OpenAI model and judged on OpenAI
  models, and the old prompts started near 100% accuracy. Your own data is the real test.
- **Strict loop.** It accepts only rewrites it can prove are better. With about 200 dev examples it misses
  gains smaller than roughly 6 points.
- **Checkable tasks only.** Scoring is code, so the tool suits tasks with a right answer (extraction,
  classification, routing, tool calls, formatted output), not open-ended writing.

## License

MIT, see [LICENSE](LICENSE).

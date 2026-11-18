# Is prompt migration to GPT-6 reproducible?

Eight synthetic legacy prompts, four GPT-6 models, three seeds each.

This repository builds eight self-contained test cases where a prompt tuned on `gpt-5.6-sol` is likely to
break on GPT-6, runs the same automated migration loop on each case three times with different seeds, and
measures whether the fix reproduces. Everything is synthetic: all data, prompts, run logs and results are
in the repository, and every number in `REPORT.md` is rebuilt from `runs/` by `make report`.

- `PLAN.md`: the brief this benchmark implements.
- `PROTOCOL.md`: thresholds and decision rules, committed before the first sweep call and never edited.
- `REPORT.md`: results (regenerated); charts in `report/`.
- `PROGRESS.md`: the build log, including every decision taken where the brief was ambiguous.

## Layout

```text
cases/<nn-name>/   spec.md, legacy_prompt.md, legacy_config.yaml, case.py, tests/   (see cases/README.md)
harness/           runner (the one path to the API), requests, generate, evaluate, loop, optimiser,
                   stats, final, report, reproduce, batch, cli
config/            models.yaml (IDs, efforts, prices, probe results), sizes.yaml (splits, loop parameters)
data/              entities/, open/<case>/{train,dev}.jsonl, sealed/<case>/{test,shift}.jsonl,
                   MANIFEST.json (versions and SHA-256), stats/, leak/ (hashed leakage index)
runs/              P0..P7 run folders (manifest.json, results.jsonl.gz, round and rejection logs),
                   prompts/ (every prompt and setting by hash), sealed_access.log
```

## Models and providers

GPT-6 targets (`gpt-6.2-astra`, `gpt-6.2-sol`, `gpt-6.1-terra`, `gpt-6-luna`), the data generator, verifier,
failure labeller and optimiser run on AWS Bedrock's OpenAI-compatible endpoint. The legacy source model
`gpt-5.6-sol` runs on Azure OpenAI, because Bedrock does not return `logprobs` (case 2 needs them).
Credentials come from the environment: `AWS_BEARER_TOKEN_BEDROCK` and `AZURE_OPENAI_API_KEY` (or a
git-ignored `.env`). Endpoints are in `config/models.yaml`; point them at your own deployments to rerun.

## Commands

```text
make setup                 environment (uv, pinned deps) and an API-key check
make check-models          probe every model ID and its supported efforts; writes config/models.yaml
make test                  unit tests (harness and every case's scorer/labeller fixtures)
make data CASE=01          build, verify and seal one case
make calibrate CASE=01     one legacy tuning round on train; calibrate-dev; freeze
make sweep CASE=01         legacy prompt on the source setup and every target setting, plus the port
make loop CASE=01 TARGET=gpt-6-luna SEED=11
make final                 the only command allowed to read data/sealed/
make report                rebuild REPORT.md and the charts from runs/
make reproduce CASE=03     clean end-to-end rerun of one case (Luna, seed 11)
make status                spend so far, phases done, runs in progress
make all                   end to end from the committed data and frozen prompts: tests, model check,
                           sweeps, loops, final, report
```

`make all` skips stages whose results already exist in `runs/`, so in a fresh clone it rebuilds the
report from the committed runs at no cost. To rerun the API stages themselves, move `runs/P4` to `runs/P7`
and `runs/protocol_lock.json` aside first (about $200 at list prices with an empty cache).
`scripts/clean_rerun.sh` performs the one-case clean rerun used for the reproducibility check.

Results: `REPORT.md` (numbers and charts), `docs/writeup.md` (the write-up).

Responses are cached by a hash of model, API, request and repeat index (`runs/state.sqlite`, not committed),
so a rerun with a warm cache costs nothing; `make reproduce` in a fresh clone starts from an empty cache.

## Disclosed limitations

The inputs are written by an OpenAI model (`gpt-6.2-sol`) and judged on OpenAI models; the shift sets with
unseen entities, templates and longer inputs are the main check against that. Scores are deterministic code
checks; fluency (case 8) is not scored. Costs are computed from list prices, not from the providers' invoices.

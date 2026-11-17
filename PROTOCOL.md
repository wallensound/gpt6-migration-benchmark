# PROTOCOL

Thresholds and decision rules for the GPT-6 migration benchmark. This file is committed before the
first sweep call and never edited afterwards (`runs/protocol_lock.json` records its SHA-256; the sweep,
loop and final commands refuse to run if it changes). REPORT.md quotes it verbatim.

## P1. Setups

- **Source (legacy) setup.** Each case's frozen `legacy_prompt.md` and `legacy_config.yaml` on `gpt-5.6-sol`
  (Azure deployment of `gpt-5.6-sol-2026-07-09`), Chat Completions, effort `none`, temperature 0.
- **Targets.** `gpt-6.2-astra` (low, medium), `gpt-6.2-sol` (low, medium), `gpt-6.1-terra` (none, low),
  `gpt-6-luna` (none, low), all through the Responses API (AWS Bedrock `global.openai.*` profiles).
- **Mechanical port.** The legacy prompt with only the changes the API forces: Responses API; no
  `temperature`, `top_p`, `logprobs` or `top_logprobs`; Structured Outputs moved from `response_format` to
  `text.format`; a legacy output-token cap kept only at effort `none`; case-specific forced changes in
  `port_settings` (case 2: logprob-based review flags become impossible, so no flags).
- **Effort choice.** Per case and target, the effort with the highest dev primary score per dollar
  (primary score divided by mean cost per item); on exact ties, the lower effort. Fixed for the loop and
  the final evaluation.

## P2. Calibration (before the sweep)

- A legacy prompt counts only if it scores at least **90%** primary on dev on the source setup
  (**85%** for cases 05 and 08), after at most **four** tuning rounds on train, and contains its legacy markers.
- It is then frozen with a hash (`cases/<case>/legacy_frozen.json`). A case that cannot reach its floor is
  dropped and reported; the benchmark continues with the remaining cases.

## P3. The loop

Parameters: at most **5** rounds; **4** candidates per round, each a different edit kind drawn by the seed
from {targeted fix, example swap, simplify, restructure, rewrite, settings change}; screening on **60**
stratified train items; dev evaluation of the best screened candidate on all **200** dev items; early stop
after **2** consecutive rounds with nothing accepted; optimiser `gpt-6.2-sol` at effort `high`; failure
labeller `gpt-6-luna`; seeds **11, 22, 33**.

- **Screening.** A candidate is dropped if its screening primary score trails the current prompt's score on
  the same 60 items by more than **3 points**, or its format validity is below **98%**.
- **Acceptance (dev).** The best surviving candidate (highest screening score; ties: shorter prompt) is
  accepted only if all hold:
  1. McNemar's exact test (two-sided, binomial on discordant dev items) gives **p < 0.05** and the
     candidate wins more discordant items than it loses;
  2. **no dev slice's primary score drops by more than 2 points** relative to the current prompt;
  3. dev format validity is at least **99%**.
- **Leakage.** A candidate is rejected (before screening) if it contains any six-word sequence from any
  train, dev, test or shift input, or any expected-answer string of five or more characters from those
  splits, except text that already occurs in the case's spec, legacy prompt or tool definitions.
- **Rules for the optimiser.** It may change only the prompt text and the case's listed settings; model and
  effort are fixed per run; it must keep the spec and output contract; every candidate carries a one-line
  rationale. Rejections are logged with their reason and shown to the optimiser in later rounds.
- **Never return to the loop after the final phase.** If a case disappoints, it is reported as it is. A
  rerun needs a new dataset version and a new protocol file (`PROTOCOL-v2.md`); this file stays frozen.

## P4. Final evaluation (run once)

- `make final` unseals test (300 items) and shift (150 items) once, and evaluates: the source setup; the
  mechanical port on every target at its chosen effort; every optimised prompt from every loop run.
- **Stability.** The source setup, every mechanical port and the seed-11 optimised prompt of every
  case and target are run **3** times in total on test (repeats 0, 1, 2); stability is the share of items
  whose pass/fail flips across the three runs.

## P5. Per case and target

- **Zero-shot drop** = mechanical-port primary score on the target minus the source setup's primary score,
  both on test.
- **Recovery** = optimised prompt's test primary score minus the source setup's test primary score.
- **Migrated** = the optimised setup is non-inferior to the source setup: the lower end of a one-sided 95%
  paired-bootstrap interval (2,000 resamples over test items, seed 0) for (optimised minus source) is
  above **-3 points**. Within each case, the bootstrap non-inferiority p-values (share of resampled
  differences at or below -3 points) of all optimised configurations are **Holm-corrected**; a
  configuration is "migrated" only if its Holm-adjusted p-value is below **0.05**.
- **Seed spread** = highest minus lowest final test primary score across the three seeds.
- **Verdict agreement** = all three seeds reach the same migrated verdict.
- **Shift gap** = optimised prompt's test score minus its shift score; above **5 points** is flagged as
  overfitting.
- Scores are reported with 95% Wilson intervals; differences with 95% paired-bootstrap intervals.

## P6. Reproducibility checks

| Check | Passes if |
| --- | --- |
| Seed repeats (per case and target, Luna and Terra) | seed spread at most **3 points** and all three seeds reach the same verdict |
| Across cases | migrated in at least **6 of 8** cases for both Luna and Terra (a case counts as migrated for a target when at least two of its three seeds are migrated) |
| Main tier | Sol loops on cases 01, 03, 07: same per-case verdicts as Terra on those cases, and seed spread at most **3 points** in each |
| Data version | cases 01 and 05 regenerated as dataset v2 (new generation seed), one Luna loop (seed 11) each: final v2 test score within **3 points** of the v1 Luna seed mean |
| Shift | every optimised prompt has a shift gap of at most **5 points**; larger gaps are flagged as overfitting |
| Clean rerun | fresh clone, empty cache, `make reproduce CASE=03` (Luna, seed 11): final test score within **2 points** of the reported number |

## P7. Overall verdict

- **Reproducible:** seed repeats pass in at least **6 of 8** cases for both Luna and Terra, and the
  data-version and clean-rerun checks pass.
- **Partly reproducible:** either seed repeats pass in **4 or 5** cases (taking the lower of the Luna and
  Terra counts) and both the data-version and clean-rerun checks pass; or seed repeats pass in at least
  6 of 8 cases for both and exactly one of the data-version and clean-rerun checks fails.
- **Not reproducible:** anything worse.
- The data-version check passes only if it passes for both case 01 and case 05.

Cases dropped at calibration count as failing the seed-repeat check. Every case is reported, including
those that fail.

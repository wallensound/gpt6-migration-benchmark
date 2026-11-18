## Advice for teams migrating (each backed by a result above)

1. **Fix the request before the prompt.** Every literal model swap failed with an HTTP 400 before any prompt
   behaviour mattered. `temperature` is rejected once effort is above `none`; output caps below 16 tokens are
   rejected; `logprobs` is rejected for reasoning models (see the sweep's literal-swap list). The mechanical
   port alone recovered seven of eight cases.
2. **Accumulated, conflicting rule lists are where GPT-6 breaks.** Case 07 is the only large regression
   (Terra -42.3 points, Sol -11.0), and the failure is literal obedience to "NEVER guess or infer": fields
   that are present get nulled. Every accepted fix restructured or simplified the prompt. They put the output
   contract and the dependency order first, or merged duplicate rules. None of them added rules.
3. **Effort `none` is not free accuracy.** On case 07 Terra at `none` scored 55.5% on dev and at `low` 71.0%,
   but the pre-registered score-per-dollar rule picked `none`. When accuracy matters, choose the effort on
   accuracy first.
4. **Logprob-based confidence has no drop-in replacement.** Case 02's legacy flags cannot be ported. The
   loop proposed two-run agreement and a per-field confidence value, but with near-zero field errors on every
   model none of them can be judged, and an accuracy-based acceptance rule never selects them. If review
   flags matter, evaluate them with a flag-specific metric and data that contains real errors.
5. **Repeat runs to see variance.** Without temperature, 0-14% of test items flip between three identical
   runs (largest on Sol and Terra in case 07, 2-3% on Luna in case 08). A single run can mislead by a few
   points.

## Observations for OpenAI (observation, minimal reproduction, impact, suggestion)

1. **Literal reading of prohibitions overrides an explicit precedence note (gpt-6.1-terra, gpt-6.2-sol).**
   - *Reproduction:* case 07's legacy prompt, plus a record such as
     `Contact : mrs karl romgardez / Phone : +44-7659-889051 / EMAIL = karlr@bronnogeolabs.co.uk / Employer =
     Bronnogeo Labs, Ltd / Country/Region : unknown`. gpt-6.1-terra (effort `none`) returns `"email": null,
     "company": null` even though both are present.
   - *Impact:* 57.0% vs 99.3% on test.
   - *Suggestion:* document that stacked "NEVER" rules are applied globally, and state in the migration
     guide that precedence notes at the end of a prompt are weak.
2. **Effort `low` changes the output budget semantics silently.** A legacy `max_output_tokens: 5` is
   rejected (minimum 16), and caps that are accepted now include reasoning tokens.
   - *Impact:* every short-output integration (routing, classification) needs a code change.
   - *Suggestion:* return a migration hint in the 400 error.
3. **No `none` effort on gpt-6.2-astra and gpt-6.2-sol** (confirmed by `make check-models`). For routing at
   effort `low` they used no reasoning tokens on these tasks, so the cost difference was small here.
4. **Run-to-run variance without temperature** is measurable: up to 14% item flips on case 07 for
   gpt-6.2-sol. A documented determinism option (or seed) would help evaluation teams.
5. **Clarifying questions and Markdown did not appear** in strict extraction or routing tasks on any GPT-6
   model (non-answer rate 0 in every sweep row). This candidate observation from the brief was checked and
   is not supported here.

## Limitations

- **Synthetic, model-written inputs.** All inputs were written by `gpt-6.2-sol` and judged on OpenAI models.
  The shift sets (unseen entities, templates, longer inputs) are the main check; no optimised prompt had a
  shift gap above 5 points.
- **Ceiling effects.** Legacy prompts scored 94.5-100% on dev. Five cases were at 99-100%, so they can only
  show regressions, and several GPT-6 ports matched them exactly. The benchmark says little about headroom.
- **Seed spread by construction.** When the loop accepts nothing, all seeds return the same prompt and,
  through the response cache, the same outputs (PROGRESS.md D22).
- **Sample sizes.** 300 test items per case give about ±3.4 points at 90%, and less near 100%. Holm
  correction makes "migrated" stricter than the raw bound: Terra seed 22 on case 07 has a lower bound of
  -2.7 points but a Holm-adjusted p of 0.15.
- **Providers and prices.** GPT-6 ran on AWS Bedrock and gpt-5.6-sol on Azure OpenAI. Azure's content
  filter rejected a few source-model calls (scored as failures). Bedrock does not offer Flex, and costs use
  OpenAI list prices.
- **Case-specific caveats** (PROGRESS.md D10-D20): case 04 has one dev item with a comma inside a quoted
  title; case 08's strict matching rejects "wirelessly" for "wireless"; case 02's flags cannot be evaluated
  because there are almost no field errors.
- **Fluency is not scored** (case 8), and order of first mention is not scored (case 1).

## Reproduce it

```text
git clone <this repository> && cd gpt6-migration-benchmark
make setup                # uv environment + credential check (AWS_BEARER_TOKEN_BEDROCK, AZURE_OPENAI_API_KEY)
make test                 # harness and case tests, no API calls
make reproduce CASE=03    # clean rerun of one case on Luna, seed 11, compared with the reported number
make report               # rebuild REPORT.md and the charts from runs/
```

The full pipeline is `make data`, `calibrate`, `freeze`, `sweeps`, `loops`, `final` and `report` (see the
Makefile). `scripts/clean_rerun.sh` performs the fresh-clone check.

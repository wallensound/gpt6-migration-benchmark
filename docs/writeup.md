# Is prompt migration to GPT-6 reproducible? Eight legacy prompts, four models, three seeds each

## The short version

- **How much breaks?** Less than you would fear, with one sharp exception. In seven of eight synthetic
  tasks, a GPT-5.6-era prompt moved to GPT-6 with only the API-forced changes lost at most 3.3 points. The
  eighth, a contact-normalisation prompt that had accumulated duplicate and conflicting rules, lost
  **42 points** on gpt-6.1-terra.
- **Does an automated loop fix it?** Yes, where something was broken. One accepted rewrite per run took
  that case from 55.5% to about 99% on Terra and from 83.5% to 97-100% on gpt-6.2-sol.
- **Is the fix reproducible?** By the pre-registered rules, yes. Seed repeats passed in 8 of 8 cases on Luna
  and 7 of 8 on Terra, a regenerated dataset landed within 1 point, and a clean rerun from an empty cache
  landed within 0.7 points. The honest reading is narrower: most cases had nothing to fix, and the one case
  the loop really changed is where seeds disagreed.
- **What does it cost?** The cheapest GPT-6 model, gpt-6-luna, answered correctly for a median
  **$0.00006** per correct answer, about 50 times cheaper than the legacy setup, at 94-100% accuracy.

## The eight cases

Each case is a self-contained synthetic task built around one documented way an old prompt can break:

1. **Rule-heavy entity extraction:** 12 all-caps rules for returning canonical company names.
2. **Invoice fields with a confidence flag:** the legacy pipeline flags uncertain fields with `logprobs`.
3. **Ticket routing at no reasoning:** 12 labels, three tie-break rules and a 5-token output cap.
4. **Tool selection:** eight functions, relative dates, look-alike tools.
5. **Format-constrained summary:** exactly three plain bullets of at most 20 words, with three facts.
6. **Grounded answers with abstention:** "NEVER guess" prompts and `NOT_FOUND`.
7. **Accumulated, conflicting rules:** 18 rules with duplicates, an IMPORTANT block and a precedence note.
8. **Terminology-locked translation:** Swedish to English with a mandatory 40-term glossary.

Every legacy prompt was written in the style of its era and tuned on `gpt-5.6-sol` with Chat Completions,
effort `none` and temperature 0. It counted only if it scored at least 90% on dev (85% for cases 5 and 8).
All eight cleared the floor after one tuning round, at 94.5-100%. That matters for how to read everything
below: these prompts worked, and most of them worked almost perfectly.

## What broke on the swap

The first thing that breaks is not the prompt but the request. A literal model-string swap failed in
every case with an HTTP 400:

- `temperature` is rejected once reasoning effort is above `none`;
- a 5-token output cap is rejected, because the minimum is 16;
- `logprobs` is rejected for reasoning models.

None of this is surprising after reading the migration guide, but every integration hits it.

After the mechanical port (Responses API, no sampling parameters, schema in `text.format`), most cases held
up. Several GPT-6 ports scored higher than the legacy setup; ticket routing, for example, gained up to 3.7
points on gpt-6.2-astra. The cheapest model, gpt-6-luna, gave up 1.3-3.3 points in five cases.

The exception was case 7. The legacy prompt says "NEVER guess or infer" in an IMPORTANT block and then, in
a precedence note at the bottom, says that one rule (fill the country from the phone's calling code) wins
over it. gpt-6.1-terra at effort `none` scored 57.0% against the legacy 99.3%. The failures are not
confined to the edge case the precedence note was written for: Terra nulled email addresses and company
names that were plainly present in the record. Given a record with
`EMAIL = karlr@bronnogeolabs.co.uk` and `Employer = Bronnogeo Labs, Ltd`, it returned `null` for both. The
model reads the prohibition as global, which matches OpenAI's own warning that accumulated guidance can
over-constrain newer models.

What did not appear is just as useful. In strict extraction and routing tasks, no GPT-6 model asked a
clarifying question, refused, or wrapped its answer in Markdown: the non-answer rate was 0 in every sweep row.

## The method

**Plan-first data.** For every item, code decides the correct answer and the surface forms first. Then
gpt-6.2-sol writes an input that must contain every planned string verbatim. Code checks the strings,
gpt-6-luna flags anything that would change the answer, flagged items are dropped (never edited), and
deterministic code produces the label from the plan. The drop rate was 0.4-12.2% per case. Each case has
120 train, 200 dev, 300 test and 150 shift items. The shift sets use unseen entities, unseen templates or
two to three times longer inputs.

**Sealed splits.** Test and shift were written once, hashed into a manifest, and read only by `make final`.
The access log shows 20 writes during data generation and 40 reads, all by the final step.

**The loop.** Each run is one case, one target and one seed:

- It starts from the mechanical port, runs the current prompt on train, and has code diff every failure.
- gpt-6-luna labels each failure, and code builds a failure report with invented-value examples.
- gpt-6.2-sol at effort `high` proposes four candidates, each a different kind of edit (targeted fix,
  example swap, simplify, restructure, rewrite, settings change).
- Candidates are screened on 60 train items. The best survivor is accepted on dev only if McNemar's exact
  test gives p < 0.05, no slice drops more than 2 points, and format validity is at least 99%.
- A leakage check rejects any candidate containing a six-word sequence or an answer string from the data.
- Each run has at most five rounds and stops after two empty rounds.

**Rules fixed in advance.** Every threshold, including the non-inferiority margin of 3 points (Holm-corrected
within each case), the 3-point seed-spread limit and the overall verdict, sat in `PROTOCOL.md`. It was
committed before the first sweep call, and its hash was locked by the harness.

## Did the loop fix it?

Where there was something to fix, yes. All six case-7 loop runs on Terra and Sol accepted a candidate in
round 1. The rationales the optimiser wrote are the most useful part of the study:

- "puts the output contract first and orders the workflow so field assignment and country resolution
  precede final formatting";
- "consolidates repeated constraints into a compact extraction and transformation checklist with one
  explicit country fallback";
- "adds a null check to the missing-value rule".

Not one accepted fix added a rule. They restructured or simplified. On the sealed test set the optimised
prompts scored 97.7-99.3%, against the legacy setup's 99.3%.

Everywhere else the loop accepted nothing, and that is the acceptance rule working as designed. Ticket
routing on Luna is a good example. A rewrite raised dev from 94.5% to 97.5%, but it won only 10 discordant
items against 4 (p = 0.18) and cost 4.3 points on the tie-break slice, so it was rejected. With 200 dev
items the rule only detects gains of about 6-7 points, so it is conservative rather than wrong.

The cost of that conservatism shows up on Luna. In four cases Luna sat 1.7-3.3 points below the legacy
setup, close enough that the interval crossed the 3-point margin, so it "migrated" in only 4 of 8 cases.
Terra migrated in 7 of 8. On case 2 none of the proposed replacements for logprob flags (two-run agreement, a
per-field confidence value, nulls when unsure) could win. No model made enough field errors for flag
quality to be measured, and the acceptance rule only looks at accuracy. A team that cares about review
flags needs a flag-specific metric and data with real errors.

## Is it reproducible?

The pre-registered verdict is **Reproducible**:

- seed repeats passed in 8 of 8 cases on Luna and 7 of 8 on Terra;
- regenerating cases 1 and 5 with a new generation seed moved the score by +1.0 and -0.3 points;
- a clean rerun of case 3 on Luna, from a fresh clone with an empty cache, scored 95.3% against 94.7%
  reported.

Three things qualify that verdict:

- **Seed spread by construction.** When the loop accepts nothing, all three seeds return the same prompt,
  and their test results are identical. A seed spread of 0 there says the loop's *decision* was stable, not
  that the model is deterministic.
- **Model variance.** Measured separately by running identical setups three times, up to 14% of test items
  flipped (gpt-6.2-sol on case 7), while most setups stayed under 3%.
- **The real fix is where seeds disagree.** Case 7 is where the loop actually changed prompts, and there the
  seeds disagreed on the verdict. Terra's three runs reached 97.7%, 98.3% and 99.0%: one was migrated
  after Holm correction, and one had a lower bound of -2.7 points but a corrected p-value of 0.15. So the
  across-cases check (6 of 8 for both Luna and Terra) and the main-tier check (Sol agreeing with Terra)
  both failed, even though the overall verdict passed.

None of this is a failure of the method, but a headline "reproducible" without these qualifications would
oversell it.

## Cost per correct answer

Median cost per correct answer across the eight cases, at OpenAI list prices:

| Setup | Median cost per correct answer |
| --- | --- |
| Legacy gpt-5.6-sol | $0.0028 |
| gpt-6.2-astra | $0.0068 |
| gpt-6.2-sol | $0.0016 |
| gpt-6.1-terra | $0.0005 |
| gpt-6-luna | $0.00006 |

Optimised prompts cost the same as the ports, because the accepted fixes did not make prompts longer. On
these tasks Astra bought almost nothing that Sol did not, at four times the price.

## Advice for teams migrating

1. **Fix the request first.** Sampling parameters, tiny output caps and logprobs all fail with HTTP 400s.
   The mechanical port alone recovered seven of eight cases.
2. **Audit accumulated rule lists.** Duplicates, IMPORTANT blocks and precedence notes are where GPT-6
   broke, and simplifying or restructuring is what fixed it.
3. **Choose effort on accuracy, not only price.** Terra at `none` scored 55.5% on case 7 and at `low`
   71.0%. A score-per-dollar rule picked `none`.
4. **Treat confidence as a separate project.** Logprob flags have no drop-in replacement, and accuracy-based
   tuning will never select one.
5. **Run things three times.** Without temperature, a few percent of items flip between identical runs.

## Observations for OpenAI

Each of these comes with a minimal reproduction in the repository:

- prohibitions are applied globally over an explicit precedence note (case 7);
- output caps below 16 tokens are rejected, and caps now include reasoning tokens;
- gpt-6.2-sol shows measurable run-to-run variance without temperature;
- a determinism option, or migration hints in 400 errors, would help.

## Limitations

- **Model-written data.** All inputs were written by an OpenAI model and judged on OpenAI models. The shift
  sets are the check against that: no optimised prompt lost more than 5 points on them.
- **Ceiling effects.** The legacy prompts were near the ceiling, so the benchmark measures regressions
  better than headroom.
- **Sample sizes.** 300 test items per case give about ±3.4 points.
- **Providers and prices.** The GPT-6 models ran on AWS Bedrock and gpt-5.6-sol on Azure OpenAI, and costs
  use list prices rather than invoices.
- **Scoring scope.** Fluency is not scored in the translation case.

## Reproduce it

```text
make setup && make test
make reproduce CASE=03
make report
```

The repository contains the harness, all eight cases with their specs and generators, every split
including test and shift, every prompt and setting by hash, the round and rejection logs of all 59 loop
runs, and the results database `make report` rebuilds. The total API spend for the full study was about
$250 at list prices.

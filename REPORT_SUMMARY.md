## Summary

**Verdict, per PROTOCOL.md: Reproducible, with a large caveat.** The loop behaved consistently across seeds,
cases, a regenerated dataset and a clean rerun. In seven of eight cases, though, it had almost nothing to fix:
the mechanical port was already as good as the legacy setup.

The four questions, one number each (test split, 300 items per case):

1. **How much breaks?** Almost nothing, except case 07. Swapping to GPT-6 with only the API-forced changes
   lost at most 3.3 points in seven of eight cases. The worst of these was Luna, and in several cases the
   port scored higher than the legacy setup. Case 07, the accumulated and conflicting rules prompt, lost
   **42.3 points on gpt-6.1-terra** (99.3% to 57.0%) and 11.0 on gpt-6.2-sol: the models null out fields
   that are present, obeying the prompt's "NEVER guess" rule over its precedence note. The literal model
   swap failed everywhere with HTTP 400 errors: `temperature` is rejected once reasoning is on, a 5-token
   output cap is rejected (the minimum is 16), and `logprobs` is rejected for reasoning models.
2. **Does the loop fix it?** Yes, where something was broken. On case 07 one accepted candidate per run
   lifted Terra from 55.5% to 98.5-99.0% on dev, and Sol from 83.5% to 97.0-100%. Final test scores were
   97.7-99.3%, against 99.3% for the legacy setup. Elsewhere the acceptance rule (McNemar p < 0.05, no slice
   drop of more than 2 points) accepted nothing, which is the intended conservative behaviour. Luna stays
   just short of the non-inferiority margin in four cases (01, 03, 07, 08: 1.7-3.3 points below the legacy
   setup), so it migrated in **4 of 8 cases**. Terra migrated in 7 of 8.
3. **Is the fix reproducible?** The seed-repeat check passes in **8 of 8 cases for Luna and 7 of 8 for
   Terra**. The data-version check passes (case 01 v2 +1.0 point, case 05 v2 -0.3 points against the v1 Luna
   mean), and so does the clean rerun (case 03 on Luna, fresh clone and empty cache: 95.3% against 94.7%
   reported). Two caveats:
   - Where the loop accepted nothing, all three seeds return the same prompt, so their seed spread of 0
     is by construction (PROGRESS.md D22). Run-to-run variance is measured separately: up to 14% of test
     items flip between three identical runs (Sol, case 07 port).
   - The one case the loop really changed, case 07, is also where reproducibility is weakest. Terra's seeds
     reach different verdicts (1 of 3 migrated after Holm correction; spread 1.3 points), and Sol reaches
     2 of 3. So the across-cases and main-tier checks fail even though the overall verdict passes.
4. **What does it cost?** Median cost per correct answer, across cases: legacy gpt-5.6-sol $0.0028;
   gpt-6.2-astra $0.0068; gpt-6.2-sol $0.0016; gpt-6.1-terra $0.0005; gpt-6-luna **$0.00006**, about 50x
   cheaper than the legacy setup at 94-100% accuracy. Optimised prompts cost the same as the ports, because
   the accepted case 07 prompts are about the same length.

**Read this first:** the legacy prompts were calibrated to 94.5-100% on the source model, so most cases
start at the ceiling, and the cases measure regressions rather than headroom. The inputs were written by
`gpt-6.2-sol` and judged on OpenAI models (see Limitations). All models ran through AWS Bedrock (GPT-6) and
Azure OpenAI (gpt-5.6-sol), not OpenAI's own API. Costs come from list prices, not invoices
(PROGRESS.md D1, D2).

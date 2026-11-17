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

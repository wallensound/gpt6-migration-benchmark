# Rules for the agent

This repository is the GPT-6 migration benchmark described in PLAN.md. Read PLAN.md in full before working.

- **Sealed data.** Never read, print or summarise anything in `data/sealed/` outside `make final` (and `make reproduce`, which runs the final step for one case). Every access through `harness/data.py` is logged in `runs/sealed_access.log`. Never open sealed files with other tools.
- **Frozen files.** Once a case is sealed, never edit its `spec.md`, labeller (`label` and helpers) or scorer (`score`, `parse`). If you find a bug, log it, bump the case's dataset version and rebuild that case from scratch.
- **Protocol.** Never edit `PROTOCOL.md` after the first sweep call. Never weaken a threshold or a test to make something pass.
- **One path to the API.** Every model call goes through `harness/runner.py`, so caching, retries, cost tracking and the budget guard always apply.
- **Commits.** Commit after every step and every loop run, with a message naming the case, phase and result.
- **Errors.** Back off on API errors. After three failed attempts at the same step, log it, skip it and move on.
- **Secrets.** Never write keys or tokens to logs, commits or reports. Keys come from the environment or the git-ignored `.env`.
- **Time.** Start no new loop run within 60 minutes of the stop time in `budget.json` (if one is set). Use that hour to finish runs in progress and write the report.
- **Decisions.** When the brief is ambiguous, choose the simpler option, record it in PROGRESS.md under "Decisions", and keep going.

## Practical notes

- Python 3.12 via uv: `uv run python -m harness.cli <command>`; the Makefile wraps every command.
- On Windows, run the Makefile from Git Bash with GNU make installed (e.g. `winget install ezwinports.make`).
- Providers and model IDs come from the environment (`.env`, see `.env.example`), never from code. This study ran the GPT-6 models on AWS Bedrock and the legacy `gpt-5.6-sol` on Azure OpenAI, because Bedrock does not return `logprobs`.

# Every command of the benchmark. Run from Git Bash or any POSIX shell.
PY ?= uv run --frozen python
CASE ?= 01
TARGET ?= gpt-6-luna
SEED ?= 11
VERSION ?= 1
N ?= 20
CASES := 01 03 06 02 05 07 04 08

.PHONY: dryrun setup check-models entities test pilot pilot-eval data calibrate calibrate-dev freeze sweep loop loops final report reproduce status

setup:            ## environment, pinned dependencies, and a check that the API keys work
	uv sync --frozen
	$(PY) -m harness.cli setup

check-models:     ## confirm every model ID and its supported efforts; rewrites config/models.yaml
	$(PY) -m harness.cli check-models

entities:
	$(PY) -m harness.cli entities

test:
	$(PY) -m pytest

pilot:            ## a few throwaway items through the full data pipeline (never part of a split)
	$(PY) -m harness.cli pilot $(CASE) --n $(N)

pilot-eval:
	$(PY) -m harness.cli pilot-eval $(CASE)

data:             ## build, verify and seal one case
	$(PY) -m harness.cli data $(CASE) --version $(VERSION)

calibrate:        ## one tuning round of the legacy prompt on train (source model)
	$(PY) -m harness.cli calibrate $(CASE) --split train

calibrate-dev:    ## floor check of the current legacy prompt on dev (scores only)
	$(PY) -m harness.cli calibrate $(CASE) --split dev

freeze:           ## freeze the legacy prompt with a hash once it clears the floor
	$(PY) -m harness.cli calibrate $(CASE) --freeze

sweep:            ## legacy prompt across the source setup and every target setting, plus the mechanical port
	$(PY) -m harness.cli sweep $(CASE)

loop:             ## one loop run
	$(PY) -m harness.cli loop $(CASE) --target $(TARGET) --seed $(SEED) --version $(VERSION)

final:            ## the only command allowed to read data/sealed/
	BENCH_FINAL=1 $(PY) -m harness.cli final

report:           ## rebuild REPORT.md and the charts from runs/
	$(PY) -m harness.cli report

reproduce:        ## clean end-to-end rerun of one case (Luna, seed 11) against the reported numbers
	BENCH_FINAL=1 $(PY) -m harness.cli reproduce $(CASE) --target $(TARGET) --seed $(SEED)

status:           ## spend so far, phases done, runs in progress
	$(PY) -m harness.cli status

dryrun:           ## P1: five stub items end to end
	$(PY) -m harness.dryrun

sweeps:           ## P4 for every case (parallel)
	$(PY) -m harness.batch sweeps --cases 01,03,06,02,05,07,04,08 --parallel 4

loops:            ## P5: Luna and Terra on all cases x 3 seeds, Sol on 01/03/07, dataset v2 runs
	$(PY) -m harness.batch loops --cases 01,03,06,02,05,07,04,08 --targets gpt-6-luna,gpt-6.1-terra --seeds 11,22,33 --parallel 12
	$(PY) -m harness.batch loops --cases 01,03,07 --targets gpt-6.2-sol --seeds 11,22,33 --parallel 9
	$(PY) -m harness.batch loops --cases 01,05 --targets gpt-6-luna --seeds 11 --version 2 --parallel 2

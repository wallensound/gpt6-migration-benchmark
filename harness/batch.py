"""Run many loop runs (P5) or sweeps (P4) concurrently in one process, committing after each.

    python -m harness.batch loops --cases 01,03 --targets gpt-6-luna --seeds 11,22,33 --parallel 6
    python -m harness.batch sweeps --cases 01,03,06 --parallel 4

Finished runs are skipped. A run that fails is retried up to three times, then logged and skipped.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
import traceback

from . import config
from .cases import Case
from .loop import run_id_for, run_loop
from .phases import sweep
from .runner import BillingError, BudgetExceeded

_git_lock: asyncio.Lock | None = None


async def commit(paths: list[str], msg: str):
    global _git_lock
    _git_lock = _git_lock or asyncio.Lock()
    async with _git_lock:
        def go():
            subprocess.run(["git", "add", "--", *paths], cwd=config.ROOT, capture_output=True)
            subprocess.run(["git", "commit", "-q", "-m", msg + "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"],
                           cwd=config.ROOT, capture_output=True)
        await asyncio.to_thread(go)


def log(msg: str):
    p = config.RUNS / "batch.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
    print(msg, flush=True)


def loop_done(case_id, target, seed, version) -> bool:
    c = Case(case_id)
    m = config.RUNS / "P5" / run_id_for(c, target, seed, version) / "manifest.json"
    return m.exists() and json.loads(m.read_text(encoding="utf-8")).get("finished", False)


async def _with_retries(label, coro_fn, attempts=3):
    for a in range(1, attempts + 1):
        try:
            return await coro_fn()
        except (BudgetExceeded, BillingError) as e:
            log(f"STOP {label}: {e}")
            raise
        except Exception as e:  # noqa: BLE001
            log(f"FAIL {label} attempt {a}: {type(e).__name__}: {e}")
            (config.RUNS / "batch_errors.log").open("a", encoding="utf-8").write(
                f"--- {time.strftime('%Y-%m-%dT%H:%M:%S')} {label} attempt {a}\n{traceback.format_exc()}\n")
            await asyncio.sleep(20 * a)
    log(f"SKIP {label}: three failed attempts")
    return None


async def loops(cases, targets, seeds, parallel, version=1):
    sem = asyncio.Semaphore(parallel)
    stop = {"flag": False}

    async def one(cid, t, s):
        if loop_done(cid, t, s, version) or stop["flag"]:
            return
        async with sem:
            if stop["flag"]:
                return
            label = f"loop {cid} {t} seed {s} v{version}"
            log(f"START {label}")
            try:
                r = await _with_retries(label, lambda: run_loop(cid, t, s, version=version))
            except (BudgetExceeded, BillingError):
                stop["flag"] = True
                return
            if r:
                log(f"DONE {label}: port dev {r['port_dev']:.3f} -> final dev {r['final_dev']:.3f}, accepted {r['accepted_rounds']}, {r['stop_reason']}, P5 spent ${r['spent_phase']:.2f}")
                await commit([f"runs/P5/{r['run_id']}", "runs/prompts", "runs/batch.log"],
                             f"P5 loop {cid} {t} seed {s}: dev {r['port_dev']:.3f} -> {r['final_dev']:.3f}, accepted rounds {r['accepted_rounds'] or 'none'}")
    await asyncio.gather(*[one(c, t, s) for t in targets for s in seeds for c in cases])


async def sweeps(cases, parallel):
    sem = asyncio.Semaphore(parallel)

    async def one(cid):
        c = Case(cid)
        if (config.RUNS / "P4" / f"{c.folder}-sweep" / "sweep.json").exists():
            return
        async with sem:
            log(f"START sweep {cid}")
            r = await _with_retries(f"sweep {cid}", lambda: sweep(cid))
            if r:
                log(f"DONE sweep {cid}: source {r['source']['primary']:.3f}; effort choice {json.dumps({k: v['effort'] for k, v in r['effort_choice'].items()})}")
                await commit([f"runs/P4/{c.folder}-sweep", "runs/prompts", "runs/protocol_lock.json", "runs/batch.log"],
                             f"P4 sweep {cid}: source dev {r['source']['primary']:.3f}")
    await asyncio.gather(*[one(c) for c in cases])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("what", choices=["loops", "sweeps"])
    p.add_argument("--cases", required=True)
    p.add_argument("--targets", default="gpt-6-luna")
    p.add_argument("--seeds", default="11,22,33")
    p.add_argument("--parallel", type=int, default=4)
    p.add_argument("--version", type=int, default=1)
    a = p.parse_args()
    cases = a.cases.split(",")
    if a.what == "loops":
        asyncio.run(loops(cases, a.targets.split(","), [int(s) for s in a.seeds.split(",")], a.parallel, a.version))
    else:
        asyncio.run(sweeps(cases, a.parallel))


if __name__ == "__main__":
    main()

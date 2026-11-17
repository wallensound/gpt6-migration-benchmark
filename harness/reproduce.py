"""`make reproduce CASE=03`: a clean end-to-end rerun of one case on one target and seed.

Meant to run in a fresh clone with an empty cache (no runs/state.sqlite). It reruns the case tests, the loop
(from the committed dataset, frozen legacy prompt and recorded effort choice) and the final test evaluation of
the resulting prompt, then compares the test score with the number reported in runs/P6/final.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from . import config, data
from .cases import Case
from .evaluate import RunStore, evaluate
from .loop import run_id_for, run_loop
from .runner import Runner


async def reproduce(case_id: str, target: str = "gpt-6-luna", seed: int = 11) -> dict:
    if os.environ.get("BENCH_FINAL") != "1":
        raise RuntimeError("reproduce reads the sealed test split; run it through `make reproduce`")
    case = Case(case_id)
    cache_was_empty = not config.STATE_DB.exists() or _cache_rows() == 0
    t = subprocess.run([sys.executable, "-m", "pytest", "-q", str(case.dir)], cwd=config.ROOT, capture_output=True, text=True)
    loop = await run_loop(case_id, target, seed, phase="P7")
    setup = json.loads((config.RUNS / "P7" / loop["run_id"] / "final_setup.json").read_text(encoding="utf-8"))
    test = data.load_split(case.folder, "test", 1)
    runner = Runner(phase="P7", purpose="reproduce final")
    ev = await evaluate(runner, case, setup, test, eval_id="reproduce|test|r0")
    store = RunStore("P7", f"{case.folder}-reproduce-final", {"case": case.folder, "kind": "reproduce"})
    store.add_eval(ev)
    store.set(finished=True)
    reported = None
    fp = config.RUNS / "P6" / "final.json"
    if fp.exists():
        f = json.loads(fp.read_text(encoding="utf-8"))
        reported = (f["cases"].get(case.folder, {}).get("opt", {}).get(run_id_for(case, target, seed, 1)) or {}).get("test")
    rerun = ev["summary"]["primary"]
    out = {"case": case.folder, "target": target, "seed": seed, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "cache_was_empty": cache_was_empty, "tests_passed": t.returncode == 0, "tests_output": t.stdout[-300:],
           "loop": loop, "rerun_test": rerun, "reported_test": reported,
           "diff": (rerun - reported) if reported is not None else None,
           "pass": reported is not None and abs(rerun - reported) <= 0.02 + 1e-9 and t.returncode == 0,
           "spent_P7": runner.spent, "git_commit": config.git_commit()}
    p = config.RUNS / "P7" / "reproduce.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def _cache_rows() -> int:
    import sqlite3
    try:
        return sqlite3.connect(config.STATE_DB).execute("SELECT COUNT(*) FROM cache").fetchone()[0]
    except Exception:
        return 0

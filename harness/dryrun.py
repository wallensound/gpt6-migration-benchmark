"""P1 dry run: five stub items through plan -> generate -> verify -> label -> evaluate -> score -> store -> stats."""
from __future__ import annotations

import asyncio
import json

from . import config, requests, stats
from .cases import Case
from .evaluate import RunStore, evaluate
from .generate import make_plans, run_pipeline, _to_item
from .runner import Runner


async def dryrun() -> dict:
    case = Case(str(config.ROOT / "tests" / "stub_case"))
    runner = Runner(phase="P1", purpose="dryrun")
    kept, dropped = await run_pipeline(runner, case, make_plans(case, "main", 5, 777_000))
    items = [{**_to_item(case, k, 0, i), "split": "dry"} for i, k in enumerate(kept)]
    legacy = case.legacy_setup()
    store = RunStore("P1", "dryrun", {"case": "stub", "kind": "dryrun"})
    src = await evaluate(runner, case, legacy, items, eval_id="source")
    store.add_eval(src)
    port = requests.mechanical_port(case, legacy, "gpt-6-luna", "low")
    tgt = await evaluate(runner, case, port, items, eval_id="port-luna-low")
    store.add_eval(tgt)
    a = [r["passed"] for r in tgt["rows"]]
    b = [r["passed"] for r in src["rows"]]
    store.set(finished=True)
    return {"generated": len(kept), "dropped": len(dropped), "inputs": [i["input"] for i in items],
            "source": src["summary"]["primary"], "luna_port": tgt["summary"]["primary"],
            "noninferiority": {k: v for k, v in stats.noninferiority(a, b).items()},
            "spent_P1": runner.spent, "run_dir": str(store.dir)}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(dryrun()), indent=2, default=str))

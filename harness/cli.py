"""Command-line entry point: `python -m harness.cli <command> ...` (the Makefile wraps these)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from . import config


def _print(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_setup(a):
    """Show which provider each model resolves to, check the keys, and ping two models."""
    config.load_dotenv()
    from .runner import Runner
    rows, missing = [], set()
    for name in config.models()["models"]:
        m = config.model_cfg(name)
        p = config.models()["providers"][m["provider"]]
        if not os.environ.get(p["key_env"]):
            missing.add(p["key_env"])
        try:
            url = config.provider_cfg(m["provider"])["base_url"]
        except RuntimeError as e:
            url = f"MISSING ({e})"
        rows.append(f"  {name:14s} -> {m['provider']:10s} {m['model_id']:30s} {url}")
    print("Models and providers (from the environment / .env):")
    print("\n".join(rows))
    if missing:
        print(f"\nmissing credentials: {sorted(missing)}. Copy .env.example to .env and fill it in.")
        sys.exit(1)
    r = Runner(phase="P0", purpose="setup")

    async def ping():
        out = {}
        for name in ("gpt-5.6-sol", "gpt-6-luna"):
            m = config.model_cfg(name)
            body = ({"messages": [{"role": "user", "content": "Reply OK"}], "reasoning_effort": "none"} if m["api"] == "chat"
                    else {"input": "Reply OK", "reasoning": {"effort": "none"}})
            res = await r.call(name, m["api"], body)
            out[name] = "ok" if res["raw"] else f"error {res['error_code']}: {res.get('error_message')}"
        return out
    _print({"sdk": config.sdk_version(), "ping": asyncio.run(ping())})


def cmd_check_models(a):
    from .phases import check_models
    _print(asyncio.run(check_models()))


def cmd_entities(a):
    from . import entities
    entities.build_and_save()
    print("entities written to data/entities/")


def cmd_pilot(a):
    from .generate import pilot
    _print(asyncio.run(pilot(a.case, a.n)))


def cmd_data(a):
    from .generate import build
    _print(asyncio.run(build(a.case, version=a.version, gen_seed=a.gen_seed, phase=a.phase)))


def cmd_import(a):
    from .byod import import_examples
    _print(import_examples(a.case, a.file, shift_file=a.shift_file, version=a.version))


def cmd_pilot_eval(a):
    """Run the legacy prompt on pilot items (never part of any split) to sanity-check spec, scorer and prompt."""
    from . import data
    from .cases import Case
    from .evaluate import evaluate
    from .runner import Runner
    case = Case(a.case)
    items = data.read_jsonl(config.DATA / "pilot" / case.folder / "items.jsonl")
    ev = asyncio.run(evaluate(Runner(phase="P2", purpose="pilot-eval"), case, case.legacy_setup(), items,
                              eval_id="pilot"))
    fails = [{"item_id": r["item_id"], "slice": r["slice"], "diff": r["diff"], "out": r["raw_output"][:600]}
             for r in ev["rows"] if not r["passed"]]
    s = ev["summary"]
    _print({"primary": s["primary"], "validity": s["validity"], "per_slice": s["per_slice"],
            "secondary": s["secondary"], "cost": s["cost_usd"], "failures": fails[: a.show]})


def cmd_calibrate(a):
    from .phases import calibrate
    _print(asyncio.run(calibrate(a.case, split=a.split, freeze=a.freeze)))


def cmd_sweep(a):
    from .phases import sweep
    res = asyncio.run(sweep(a.case))
    _print({"effort_choice": res["effort_choice"], "rows": [
        {k: r[k] for k in ("setting", "primary", "validity", "nonanswer_rate", "cost_per_item")} for r in res["rows"]],
        "literal_swap": res["literal_swap"]})


def cmd_loop(a):
    from .loop import run_loop
    _print(asyncio.run(run_loop(a.case, a.target, a.seed, version=a.version)))


def cmd_final(a):
    os.environ["BENCH_FINAL"] = "1"
    from .final import run_final
    _print(asyncio.run(run_final(cases=a.case, only=a.only)))


def cmd_report(a):
    from .report import build_report
    print(build_report())


def cmd_reproduce(a):
    from .reproduce import reproduce
    _print(asyncio.run(reproduce(a.case, a.target, a.seed)))


def cmd_recommend(a):
    from .recommend import recommend, table
    print(table(recommend()))
    print("\nDetails: runs/recommend.json. Chosen on dev, confirmed once on test (see harness/recommend.py).")


def cmd_status(a):
    from .status import status
    print(status())


def main(argv=None):
    p = argparse.ArgumentParser(prog="harness")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(f=cmd_setup)
    sub.add_parser("check-models").set_defaults(f=cmd_check_models)
    sub.add_parser("entities").set_defaults(f=cmd_entities)
    s = sub.add_parser("pilot"); s.add_argument("case"); s.add_argument("--n", type=int, default=20); s.set_defaults(f=cmd_pilot)
    s = sub.add_parser("pilot-eval"); s.add_argument("case"); s.add_argument("--show", type=int, default=15); s.set_defaults(f=cmd_pilot_eval)
    s = sub.add_parser("data"); s.add_argument("case"); s.add_argument("--version", type=int, default=1)
    s.add_argument("--gen-seed", type=int, default=None); s.add_argument("--phase", default="P2"); s.set_defaults(f=cmd_data)
    s = sub.add_parser("import", help="bring your own examples (CSV/JSONL) instead of generating data")
    s.add_argument("case"); s.add_argument("--file", required=True); s.add_argument("--shift-file", default=None)
    s.add_argument("--version", type=int, default=1); s.set_defaults(f=cmd_import)
    s = sub.add_parser("calibrate"); s.add_argument("case"); s.add_argument("--split", default="train")
    s.add_argument("--freeze", action="store_true"); s.set_defaults(f=cmd_calibrate)
    s = sub.add_parser("sweep"); s.add_argument("case"); s.set_defaults(f=cmd_sweep)
    s = sub.add_parser("loop"); s.add_argument("case"); s.add_argument("--target", required=True)
    s.add_argument("--seed", type=int, required=True); s.add_argument("--version", type=int, default=1); s.set_defaults(f=cmd_loop)
    s = sub.add_parser("final"); s.add_argument("--case", default=None); s.add_argument("--only", default=None); s.set_defaults(f=cmd_final)
    sub.add_parser("report").set_defaults(f=cmd_report)
    s = sub.add_parser("reproduce"); s.add_argument("case"); s.add_argument("--target", default="gpt-6-luna")
    s.add_argument("--seed", type=int, default=11); s.set_defaults(f=cmd_reproduce)
    sub.add_parser("status").set_defaults(f=cmd_status)
    sub.add_parser("recommend", help="which model should each task move to").set_defaults(f=cmd_recommend)
    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()

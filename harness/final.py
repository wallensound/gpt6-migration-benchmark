"""P6: unseal test and shift once, evaluate every final configuration, compute verdicts per PROTOCOL.md."""
from __future__ import annotations

import json
import os
import time

import numpy as np

from . import config, data, requests, stats
from .cases import Case, all_case_ids, prompt_hash
from .evaluate import RunStore, evaluate, read_results
from .phases import effort_choice, frozen_info, lock_protocol, targets
from .runner import BudgetExceeded, Runner

LOOP_TARGETS = ("gpt-6-luna", "gpt-6.1-terra", "gpt-6.2-sol")


def loop_runs(case: Case) -> list[dict]:
    out = []
    d = config.RUNS / "P5"
    if not d.exists():
        return out
    for p in sorted(d.glob(f"{case.folder}-*")):
        m = p / "manifest.json"
        f = p / "final_setup.json"
        if m.exists() and f.exists():
            man = json.loads(m.read_text(encoding="utf-8"))
            if man.get("finished"):
                out.append({"run_id": man["run_id"], "target": man["target"], "seed": man["seed"],
                            "version": man.get("dataset_version", 1), "setup": json.loads(f.read_text(encoding="utf-8"))})
    return out


def final_configs(case: Case) -> list[dict]:
    legacy = case.legacy_setup()
    cfgs = [{"name": "source", "kind": "source", "target": legacy["model"], "seed": None, "version": 1, "setup": legacy}]
    eff = effort_choice(case)
    for t in targets():
        if t in eff:
            cfgs.append({"name": f"port:{t}", "kind": "port", "target": t, "seed": None, "version": 1,
                         "setup": requests.mechanical_port(case, legacy, t, eff[t]["effort"])})
    for r in loop_runs(case):
        cfgs.append({"name": f"opt:{r['run_id']}", "kind": "opt", "target": r["target"], "seed": r["seed"],
                     "version": r["version"], "setup": r["setup"]})
    return cfgs


def stability_set(cfg: dict) -> bool:
    return cfg["kind"] in ("source", "port") or (cfg["kind"] == "opt" and cfg["seed"] == 11 and cfg["version"] == 1)


async def run_final(cases: str | None = None, only: str | None = None) -> dict:
    if os.environ.get("BENCH_FINAL") != "1":
        raise RuntimeError("make final sets BENCH_FINAL=1; nothing else may read sealed data")
    lock_protocol()
    ids = [cases] if cases else [c for c in all_case_ids() if frozen_info(Case(c))]
    runner = Runner(phase="P6", purpose="final")
    log = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": {}, "skipped": []}
    plan = []
    for cid in ids:
        case = Case(cid)
        cfgs = final_configs(case)
        splits = {}
        for v in sorted({c["version"] for c in cfgs}):
            splits[v] = {s: data.load_split(case.folder, s, v) for s in ("test", "shift")}
        store = RunStore("P6", f"{case.folder}-final", {"case": case.folder, "kind": "final"}, fresh=False)
        done = {(e["eval_id"]) for e in store.manifest["evals"]}
        for cfg in cfgs:
            plan.append((0, case, cfg, "test", 0, splits, store, done))
            plan.append((1, case, cfg, "shift", 0, splits, store, done))
            if stability_set(cfg):
                for rep in (1, 2):
                    plan.append((2, case, cfg, "test", rep, splits, store, done))
        log["cases"][case.folder] = [c["name"] for c in cfgs]
    plan.sort(key=lambda x: x[0])  # all test runs first, then shift, then stability repeats
    for prio, case, cfg, split, rep, splits, store, done in plan:
        eid = f"{cfg['name']}|{split}|r{rep}"
        if eid in done:
            continue
        if only and only not in eid:
            continue
        try:
            ev = await evaluate(runner, case, cfg["setup"], splits[cfg["version"]][split], repeat=rep, eval_id=eid)
        except BudgetExceeded as e:
            log["skipped"].append({"eval_id": eid, "case": case.folder, "reason": str(e)})
            continue
        store.add_eval(ev, config_name=cfg["name"], kind=cfg["kind"], target=cfg["target"], seed=cfg["seed"],
                       dataset_version=cfg["version"], split=split)
        done.add(eid)
    log["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    log["spent_P6"] = runner.spent
    prev = config.RUNS / "P6" / "final_log.json"
    hist = json.loads(prev.read_text(encoding="utf-8")) if prev.exists() else []
    hist.append(log)
    prev.write_text(json.dumps(hist, indent=2), encoding="utf-8")
    res = analyse()
    return {"spent_P6": runner.spent, "skipped": log["skipped"], "overall": res["overall"]}


# --------------------------------------------------------------------------- analysis

def _evals(case_folder: str) -> tuple[dict, dict]:
    d = config.RUNS / "P6" / f"{case_folder}-final"
    if not (d / "manifest.json").exists():
        return {}, {}
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    rows: dict[str, dict[str, bool]] = {}
    for r in read_results(d):
        rows.setdefault(r["eval_id"], {})[r["item_id"]] = r["passed"]
    meta = {e["eval_id"]: e for e in man["evals"]}
    return meta, rows


def _vec(rows: dict, eid: str, ids: list[str]):
    m = rows.get(eid)
    if m is None:
        return None
    return np.array([m[i] for i in ids], dtype=bool)


def analyse() -> dict:
    S = config.sizes()
    margin = S["noninferiority_margin"]
    nres = S["bootstrap_resamples"]
    out = {"cases": {}, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    all_ids = all_case_ids()
    for cid in all_ids:
        case = Case(cid)
        fz = frozen_info(case)
        meta, rows = _evals(case.folder)
        if not fz or "source|test|r0" not in rows:
            out["cases"][case.folder] = {"status": "dropped" if not fz else "not evaluated"}
            continue
        ids = sorted(rows["source|test|r0"])
        src = _vec(rows, "source|test|r0", ids)
        src_s = meta["source|test|r0"]["summary"]
        c = {"status": "evaluated", "source": {"test": src_s["primary"], "test_ci": src_s["primary_ci"],
                                               "cost_per_correct": src_s["cost_per_correct"],
                                               "shift": (meta.get("source|shift|r0") or {}).get("summary", {}).get("primary")},
             "ports": {}, "opt": {}, "targets": {}}
        eff = effort_choice(case)
        for t in targets():
            eid = f"port:{t}|test|r0"
            if eid not in meta:
                continue
            v = _vec(rows, eid, ids)
            s = meta[eid]["summary"]
            dci = stats.diff_ci(v, src, nres, 0)
            c["ports"][t] = {"effort": eff.get(t, {}).get("effort"), "test": s["primary"], "test_ci": s["primary_ci"],
                             "zero_shot_drop": s["primary"] - src_s["primary"], "drop_ci": [dci["ci_low"], dci["ci_high"]],
                             "validity": s["validity"], "nonanswer_rate": s["nonanswer_rate"],
                             "cost_per_correct": s["cost_per_correct"], "cost_per_item": s["cost_per_item"],
                             "shift": (meta.get(f"port:{t}|shift|r0") or {}).get("summary", {}).get("primary"),
                             "latency_p50_s": s["latency_p50_s"], "latency_p95_s": s["latency_p95_s"],
                             "failure_categories": s["failure_categories"]}
        # optimised runs on dataset v1: non-inferiority with Holm within the case
        opt_ids = [e for e in meta if e.startswith("opt:") and e.endswith("|test|r0") and meta[e].get("dataset_version", 1) == 1]
        ni = {}
        for eid in opt_ids:
            v = _vec(rows, eid, ids)
            ni[eid] = stats.noninferiority(v, src, margin, nres, 0)
        adj = stats.holm([ni[e]["p_value"] for e in opt_ids]) if opt_ids else []
        for eid, p_adj in zip(opt_ids, adj):
            m = meta[eid]
            s = m["summary"]
            sh = (meta.get(eid.replace("|test|", "|shift|")) or {}).get("summary", {}).get("primary")
            name = eid.split("|")[0][4:]
            c["opt"][name] = {"target": m["target"], "seed": m["seed"], "test": s["primary"], "test_ci": s["primary_ci"],
                              "recovery": s["primary"] - src_s["primary"],
                              "ni_lower_bound": ni[eid]["lower_bound"], "ni_p": ni[eid]["p_value"], "ni_p_holm": p_adj,
                              "migrated": bool(p_adj < 0.05), "shift": sh,
                              "shift_gap": (s["primary"] - sh) if sh is not None else None,
                              "overfit_flag": (s["primary"] - sh) > 0.05 if sh is not None else None,
                              "cost_per_correct": s["cost_per_correct"], "cost_per_item": s["cost_per_item"],
                              "validity": s["validity"]}
        for t in LOOP_TARGETS:
            runs = [o for o in c["opt"].values() if o["target"] == t]
            if not runs:
                continue
            scores = [o["test"] for o in runs]
            verdicts = [o["migrated"] for o in runs]
            spread = max(scores) - min(scores)
            c["targets"][t] = {"seeds": sorted(o["seed"] for o in runs), "mean_test": float(np.mean(scores)),
                               "mean_recovery": float(np.mean([o["recovery"] for o in runs])),
                               "recovery_range": [min(o["recovery"] for o in runs), max(o["recovery"] for o in runs)],
                               "seed_spread": spread, "verdict_agreement": len(set(verdicts)) == 1,
                               "migrated_seeds": int(sum(verdicts)), "case_migrated": sum(verdicts) >= 2,
                               "seed_repeat_pass": len(runs) == 3 and spread <= 0.03 + 1e-9 and len(set(verdicts)) == 1}
        # stability (three repeats on test)
        stab = {}
        for base in [e[:-len("|test|r0")] for e in meta if e.endswith("|test|r0")]:
            bids = sorted(rows[f"{base}|test|r0"])  # dataset-v2 configs have their own item ids
            reps = [_vec(rows, f"{base}|test|r{r}", bids) for r in range(3)]
            if all(r is not None for r in reps):
                stab[base] = stats.flip_rate(np.vstack(reps))
        c["stability_flip_rate"] = stab
        # dataset v2 runs
        v2 = [e for e in meta if e.startswith("opt:") and e.endswith("|test|r0") and meta[e].get("dataset_version", 1) != 1]
        c["v2"] = {e.split("|")[0][4:]: {"test": meta[e]["summary"]["primary"], "target": meta[e]["target"],
                                         "seed": meta[e]["seed"]} for e in v2}
        out["cases"][case.folder] = c
    out["overall"] = overall(out)
    p = config.RUNS / "P6" / "final.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def overall(res: dict) -> dict:
    cases = res["cases"]
    n_cases = len(cases)
    o = {"n_cases": n_cases}
    for t in ("gpt-6-luna", "gpt-6.1-terra"):
        o[f"seed_repeat_pass_{t}"] = sum(1 for c in cases.values() if c.get("targets", {}).get(t, {}).get("seed_repeat_pass"))
        o[f"migrated_cases_{t}"] = sum(1 for c in cases.values() if c.get("targets", {}).get(t, {}).get("case_migrated"))
    o["across_cases_pass"] = o["migrated_cases_gpt-6-luna"] >= 6 and o["migrated_cases_gpt-6.1-terra"] >= 6
    mt = {}
    for cf, c in cases.items():
        sol = c.get("targets", {}).get("gpt-6.2-sol")
        ter = c.get("targets", {}).get("gpt-6.1-terra")
        if sol:
            mt[cf] = {"sol_case_migrated": sol["case_migrated"], "terra_case_migrated": (ter or {}).get("case_migrated"),
                      "sol_seed_spread": sol["seed_spread"],
                      "pass": bool(ter) and sol["case_migrated"] == ter["case_migrated"] and sol["seed_spread"] <= 0.03 + 1e-9}
    o["main_tier"] = mt
    o["main_tier_pass"] = bool(mt) and len(mt) == 3 and all(v["pass"] for v in mt.values())
    dv = {}
    for cf, c in cases.items():
        for name, r in (c.get("v2") or {}).items():
            v1 = c.get("targets", {}).get(r["target"], {})
            if v1:
                dv[cf] = {"v2_test": r["test"], "v1_seed_mean": v1["mean_test"], "diff": r["test"] - v1["mean_test"],
                          "pass": abs(r["test"] - v1["mean_test"]) <= 0.03 + 1e-9}
    o["data_version"] = dv
    o["data_version_pass"] = len(dv) == 2 and all(v["pass"] for v in dv.values())
    flags = [(cf, n, r["shift_gap"]) for cf, c in cases.items() for n, r in (c.get("opt") or {}).items() if r.get("overfit_flag")]
    o["shift_flags"] = flags
    o["shift_pass"] = not flags
    rp = config.RUNS / "P7" / "reproduce.json"
    if rp.exists():
        rr = json.loads(rp.read_text(encoding="utf-8"))
        o["clean_rerun"] = rr
        o["clean_rerun_pass"] = bool(rr.get("pass"))
    else:
        o["clean_rerun_pass"] = None
    lo = min(o["seed_repeat_pass_gpt-6-luna"], o["seed_repeat_pass_gpt-6.1-terra"])
    others = [o["data_version_pass"], o["clean_rerun_pass"]]
    fails = sum(1 for x in others if x is not True)
    if lo >= 6 and fails == 0:
        v = "Reproducible"
    elif (4 <= lo <= 5 and fails == 0) or (lo >= 6 and fails == 1):
        v = "Partly reproducible"
    else:
        v = "Not reproducible"
    o["verdict"] = v
    o["seed_repeat_pass_min"] = lo
    return o

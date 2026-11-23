"""`make recommend`: which model should each task move to?

Per case, from stored results only (no API calls):
  1. Candidates: every target's mechanical port (at its chosen effort) and every optimised prompt from the loop.
  2. Choose on dev: keep candidates that are non-inferior to the legacy setup on dev (lower end of the one-sided
     95% paired-bootstrap interval above -3 points), then pick the lowest cost per correct answer
     (ties: higher dev score).
  3. Confirm on test (only if `make final` has run): the pick must also be non-inferior on test. If it is not,
     the next cheapest dev-passing candidate that passes on test is recommended, and the fallback is reported.

This is an addition after the pre-registered protocol: it does not change any PROTOCOL.md verdict.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import config, stats
from .cases import Case, all_case_ids
from .evaluate import read_results
from .phases import effort_choice, targets


def _passes(rows, eval_id):
    m = {r["item_id"]: r["passed"] for r in rows if r["eval_id"] == eval_id}
    return m or None


def _cost(rows, eval_id):
    rs = [r for r in rows if r["eval_id"] == eval_id]
    k = sum(r["passed"] for r in rs)
    c = sum(r["cost_usd"] for r in rs)
    return (c / k if k else None), (k / len(rs) if rs else 0.0)


def _ni(cand: dict, ref: dict, margin: float) -> dict:
    ids = sorted(ref)
    a = np.array([cand[i] for i in ids], bool)
    b = np.array([ref[i] for i in ids], bool)
    return stats.noninferiority(a, b, margin, config.sizes()["bootstrap_resamples"], 0)


def recommend_case(case: Case) -> dict:
    margin = config.sizes()["noninferiority_margin"]
    sweep_dir = config.RUNS / "P4" / f"{case.folder}-sweep"
    if not (sweep_dir / "sweep.json").exists():
        return {"case": case.folder, "status": "no sweep yet"}
    sweep_rows = read_results(sweep_dir)
    legacy_dev = _passes(sweep_rows, "source")
    legacy_cpc, legacy_acc = _cost(sweep_rows, "source")
    eff = effort_choice(case)
    cands = []
    for t in targets():
        if t not in eff:
            continue
        eid = f"port-{t}-{eff[t]['effort']}"
        p = _passes(sweep_rows, eid)
        if p:
            cpc, acc = _cost(sweep_rows, eid)
            cands.append({"name": f"port:{t}", "label": f"{t} ({eff[t]['effort']}), legacy prompt ported",
                          "target": t, "dev_passes": p, "dev_acc": acc, "dev_cost_per_correct": cpc,
                          "final_eval": f"port:{t}|test|r0"})
    for man in sorted((config.RUNS / "P5").glob(f"{case.folder}-*/manifest.json")):
        m = json.loads(man.read_text(encoding="utf-8"))
        if not m.get("finished") or m.get("dataset_version", 1) != 1:
            continue
        rows = read_results(man.parent)
        accepted = [e for e in m["evals"] if e.get("role") == "dev-candidate" and
                    e["prompt_hash"] == m.get("final_prompt_hash")]
        eid = accepted[-1]["eval_id"] if accepted else "r0-dev"
        p = _passes(rows, eid)
        if p:
            cpc, acc = _cost(rows, eid)
            changed = bool(accepted)
            cands.append({"name": f"opt:{m['run_id']}", "label": f"{m['target']} ({m['effort']}), "
                          f"{'loop-optimised prompt' if changed else 'loop kept the ported prompt'} (seed {m['seed']})",
                          "target": m["target"], "dev_passes": p, "dev_acc": acc, "dev_cost_per_correct": cpc,
                          "final_eval": f"opt:{m['run_id']}|test|r0", "prompt_changed": changed})
    for c in cands:
        c["dev_ni"] = _ni(c["dev_passes"], legacy_dev, margin)
    passing = sorted([c for c in cands if c["dev_ni"]["noninferior"] and c["dev_cost_per_correct"]],
                     key=lambda c: (c["dev_cost_per_correct"], -c["dev_acc"]))
    out = {"case": case.folder, "status": "ok", "legacy_dev_acc": legacy_acc, "legacy_dev_cost_per_correct": legacy_cpc,
           "dev_passing": [c["label"] for c in passing], "candidates": len(cands)}
    if not passing:
        out["status"] = "no candidate is non-inferior on dev"
        return out
    # confirm on test
    final_dir = config.RUNS / "P6" / f"{case.folder}-final"
    test_rows = read_results(final_dir) if final_dir.exists() else []
    legacy_test = _passes(test_rows, "source|test|r0") if test_rows else None
    chosen, fallback = passing[0], False
    if legacy_test:
        for i, c in enumerate(passing):
            tp = _passes(test_rows, c["final_eval"])
            if not tp:
                continue
            c["test_ni"] = _ni(tp, legacy_test, margin)
            c["test_cost_per_correct"], c["test_acc"] = _cost(test_rows, c["final_eval"])
            if c["test_ni"]["noninferior"]:
                chosen, fallback = c, i > 0
                break
        else:
            out["status"] = "dev pick not confirmed on test"
        out["legacy_test_acc"] = _cost(test_rows, "source|test|r0")[1]
        out["legacy_test_cost_per_correct"] = _cost(test_rows, "source|test|r0")[0]
    out["recommended"] = {k: v for k, v in chosen.items() if k not in ("dev_passes",)}
    out["recommended"]["dev_ni_lower_bound"] = chosen["dev_ni"]["lower_bound"]
    out["fallback_used"] = fallback
    if fallback:
        out["dev_pick"] = passing[0]["label"]
    lc = out.get("legacy_test_cost_per_correct") or legacy_cpc
    rc = chosen.get("test_cost_per_correct") or chosen["dev_cost_per_correct"]
    out["cost_reduction_x"] = (lc / rc) if lc and rc else None
    return out


def recommend() -> dict:
    res = {"note": "Added after the pre-registered protocol; does not change PROTOCOL.md verdicts.",
           "cases": {c: recommend_case(Case(c)) for c in all_case_ids()}}
    for r in res["cases"].values():
        for k in ("recommended",):
            if k in r:
                r[k].pop("dev_ni", None)
                r[k].pop("test_ni", None)
    p = config.RUNS / "recommend.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    return res


def table(res: dict) -> str:
    L = ["| Case | Move to | Dev score | Test score (legacy) | Cost per correct (legacy) | Cheaper by |",
         "|---|---|---|---|---|---|"]
    for cf, r in res["cases"].items():
        rec = r.get("recommended")
        if not rec:
            L.append(f"| {cf} | {r['status']} | | | | |")
            continue
        ta = rec.get("test_acc")
        L.append(f"| {cf} | {rec['label']}{' (fallback)' if r.get('fallback_used') else ''} | {100 * rec['dev_acc']:.1f}% | "
                 + (f"{100 * ta:.1f}% ({100 * r['legacy_test_acc']:.1f}%)" if ta is not None else "not run") + " | "
                 + f"${(rec.get('test_cost_per_correct') or rec['dev_cost_per_correct']):.5f} "
                 + f"(${(r.get('legacy_test_cost_per_correct') or r['legacy_dev_cost_per_correct']):.5f}) | "
                 + (f"{r['cost_reduction_x']:.1f}x" if r.get("cost_reduction_x") else "–") + " |")
    return "\n".join(L)

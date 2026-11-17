"""Optimisation loop v2: one case, one target, one seed. Tunes on train, decides on dev.

Round: run current prompt on train -> diagnose (code diff + luna labels + rewritten examples) ->
propose 4 candidates (different edit kinds) -> leakage check -> screen on 60 train items ->
best survivor on 200 dev items -> accept only on McNemar p<0.05, no slice drop >2 points, validity >=99%.
"""
from __future__ import annotations

import json
import random
import time

import numpy as np

from . import config, data, requests, stats
from .cases import Case, prompt_hash
from .evaluate import RunStore, evaluate, save_setup
from .optimiser import EDIT_KINDS, check_leak, propose
from .phases import assert_frozen, effort_choice, lock_protocol
from .runner import Runner, normalise

LABEL_PROMPT = """You label why a model output failed a benchmark item. Pick exactly one category from: {taxonomy}.

Task spec (abridged):
{spec}

INPUT (may be truncated):
{input}

EXPECTED: {expected}
MODEL OUTPUT: {output}
CODE DIFF: {diff}

Return JSON {{"category": "<one of the categories>", "cause": "<one line: what the model did wrong>"}}."""

REWRITE_PROMPT = """Rewrite this failure example so it contains no real data from the original: replace every name, \
company, product, person, number, amount, date, place, email and phone with NEW invented values, consistently \
across input, expected and output. Keep the structure and keep the same mistake visible. Shorten the input to at \
most 100 words around the part that matters.

INPUT: {input}
EXPECTED: {expected}
OUTPUT: {output}

Return JSON {{"input": "...", "expected": "...", "output": "..."}}."""


def _obj_schema(keys, enum=None):
    props = {k: {"type": "string"} for k in keys}
    if enum:
        props[keys[0]] = {"type": "string", "enum": enum}
    return {"type": "object", "properties": props, "required": list(keys), "additionalProperties": False}


async def _llm_json(runner: Runner, role: str, prompt: str, schema: dict, purpose: str) -> dict | None:
    r = config.role(role)
    body = {"input": [{"role": "user", "content": prompt}], "reasoning": {"effort": r["effort"]},
            "text": {"format": {"type": "json_schema", "name": "out", "schema": schema, "strict": True}}}
    res = await runner.call(r["model"], "responses", body, purpose=purpose)
    if res["raw"] is None:
        return None
    try:
        return json.loads(normalise("responses", res["raw"])["text"])
    except Exception:
        return None


def _short(x, n):
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + " ..."


async def diagnose(runner: Runner, case: Case, items: dict, rows: list[dict], rng: random.Random, version: int) -> dict:
    import asyncio
    fails = [r for r in rows if not r["passed"]]
    tax = case.failure_taxonomy()
    spec = _short(case.spec_text, 3000)

    async def lab(r):
        it = items[r["item_id"]]
        out = await _llm_json(runner, "labeller", LABEL_PROMPT.format(
            taxonomy=", ".join(tax), spec=spec, input=_short(it["input"], 1500), expected=_short(it["expected"], 600),
            output=_short(r["raw_output"], 800), diff=_short(r["diff"], 600)), _obj_schema(["category", "cause"], tax),
            "label failure")
        return out or {"category": (r["categories"] or ["other"])[0] if (r["categories"] or ["other"])[0] in tax else tax[-1],
                       "cause": "labeller unavailable"}
    labels = await asyncio.gather(*[lab(r) for r in fails])
    by_cat: dict[str, list] = {}
    for r, l in zip(fails, labels):
        by_cat.setdefault(l["category"], []).append((r, l))
    by_slice: dict[str, int] = {}
    for r in fails:
        by_slice[r["slice"]] = by_slice.get(r["slice"], 0) + 1
    top = sorted(by_cat.items(), key=lambda kv: -len(kv[1]))[: config.sizes()["loop"]["top_patterns"]]
    patterns = []
    for cat, lst in top:
        picks = rng.sample(lst, min(config.sizes()["loop"]["examples_per_pattern"], len(lst)))
        exs = []
        for r, l in picks:
            it = items[r["item_id"]]
            rw = await _llm_json(runner, "labeller", REWRITE_PROMPT.format(
                input=_short(it["input"], 1500), expected=_short(it["expected"], 600), output=_short(r["raw_output"], 600)),
                _obj_schema(["input", "expected", "output"]), "rewrite example")
            if not rw:
                continue
            blob = " ".join(rw.values())
            if not check_leak(case, blob, version)["ok"]:
                continue  # a rewritten example that still carries data strings is dropped
            exs.append({**rw, "cause": l["cause"]})
        causes = [l["cause"] for _, l in lst]
        patterns.append({"category": cat, "count": len(lst), "sample_causes": causes[:5], "examples": exs})
    n = len(rows)
    lines = [f"Train items: {n}; passed {n - len(fails)} ({(n - len(fails)) / n:.1%}); failed {len(fails)}.",
             "Failures per category: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(by_cat.items(), key=lambda kv: -len(kv[1]))),
             "Failures per slice: " + ", ".join(f"{k} {v}" for k, v in sorted(by_slice.items(), key=lambda kv: -kv[1]))]
    for i, p in enumerate(patterns, 1):
        lines.append(f"\nPattern {i}: {p['category']} ({p['count']} items). Typical causes: " + " | ".join(p["sample_causes"]))
        for j, e in enumerate(p["examples"], 1):
            lines.append(f"  Example {i}.{j} (invented values): INPUT: {e['input']}\n    EXPECTED: {e['expected']}\n"
                         f"    OUTPUT: {e['output']}\n    WHY: {e['cause']}")
    return {"text": "\n".join(lines), "counts": {k: len(v) for k, v in by_cat.items()}, "by_slice": by_slice,
            "patterns": [{k: v for k, v in p.items() if k != "examples"} | {"n_examples": len(p["examples"])} for p in patterns]}


def stratified_sample(items: list[dict], k: int, rng: random.Random) -> list[dict]:
    by: dict[str, list] = {}
    for it in items:
        by.setdefault(it["slice"], []).append(it)
    out = []
    total = len(items)
    for sl in sorted(by):
        pool = by[sl][:]
        rng.shuffle(pool)
        out += pool[: max(1, round(k * len(pool) / total))]
    rng.shuffle(out)
    return out[:k]


def _passes(ev):
    return {r["item_id"]: r["passed"] for r in ev["rows"]}


def decide(case_cfg: dict, cand_ev: dict, cur_ev: dict) -> dict:
    a = _passes(cand_ev)
    b = _passes(cur_ev)
    ids = sorted(a)
    mc = stats.mcnemar_exact([a[i] for i in ids], [b[i] for i in ids])
    cs, us = cand_ev["summary"]["per_slice"], cur_ev["summary"]["per_slice"]
    drops = {s: cs[s]["primary"] - us[s]["primary"] for s in us if s in cs}
    worst = min(drops.values()) if drops else 0.0
    val = cand_ev["summary"]["validity"]
    reasons = []
    if not (mc["b"] > mc["c"] and mc["p_value"] < case_cfg["accept_alpha"]):
        reasons.append(f"McNemar not significant (b={mc['b']}, c={mc['c']}, p={mc['p_value']:.3f})")
    if worst < -case_cfg["accept_max_slice_drop"] - 1e-9:
        s = min(drops, key=drops.get)
        reasons.append(f"slice '{s}' drops {-worst * 100:.1f} points")
    if val < case_cfg["accept_min_validity"]:
        reasons.append(f"format validity {val:.1%} < {case_cfg['accept_min_validity']:.0%}")
    return {"accept": not reasons, "reasons": reasons, "mcnemar": mc, "worst_slice_drop": worst, "validity": val,
            "dev_primary": cand_ev["summary"]["primary"], "dev_primary_current": cur_ev["summary"]["primary"]}


def run_id_for(case: Case, target: str, seed: int, version: int) -> str:
    return f"{case.folder}-{target}-s{seed}" + ("" if version == 1 else f"-v{version}")


async def run_loop(case_id: str, target: str, seed: int, version: int = 1, phase: str = "P5") -> dict:
    lock_protocol()
    case = Case(case_id)
    assert_frozen(case)
    L = config.sizes()["loop"]
    effort = effort_choice(case)[target]["effort"]
    legacy = case.legacy_setup()
    port = requests.mechanical_port(case, legacy, target, effort)
    rng = random.Random(seed)
    train = data.load_split(case.folder, "train", version)
    dev = data.load_split(case.folder, "dev", version)
    rng.shuffle(train)  # the seed sets the order of train items
    items = {it["id"]: it for it in train}
    runner = Runner(phase=phase, purpose=f"loop {case.id} {target} s{seed}")
    rid = run_id_for(case, target, seed, version)
    store = RunStore(phase, rid, {"case": case.folder, "kind": "loop", "target": target, "effort": effort, "seed": seed,
                                  "dataset_version": version, "loop_params": L,
                                  "optimiser": config.role("optimiser"), "labeller": config.role("labeller")})
    current = port
    cur_dev = await evaluate(runner, case, current, dev, eval_id="r0-dev")
    store.add_eval(cur_dev, round=0, role="port-dev")
    round_log = [{"round": 0, "prompt_hash": prompt_hash(current), "dev_primary": cur_dev["summary"]["primary"],
                  "note": "mechanical port (starting prompt)"}]
    rejections: list[dict] = []
    empty = 0
    stop_reason = "round limit"
    for rnd in range(1, L["rounds"] + 1):
        t0 = time.time()
        tr = await evaluate(runner, case, current, train, eval_id=f"r{rnd}-train")
        store.add_eval(tr, round=rnd, role="train")
        report = await diagnose(runner, case, items, tr["rows"], rng, version)
        kinds = rng.sample(list(EDIT_KINDS), L["candidates"])
        cands = await propose(runner, case, current, report["text"], rejections, kinds, seed, rnd)
        screen = stratified_sample(train, L["screen_items"], rng)
        cur_screen = {r["item_id"]: r for r in tr["rows"]}
        cur_s_rows = [cur_screen[it["id"]] for it in screen]
        cur_s_primary = float(np.mean([r["passed"] for r in cur_s_rows]))
        entry = {"round": rnd, "kinds": kinds, "train_primary": tr["summary"]["primary"],
                 "failure_report": {k: report[k] for k in ("counts", "by_slice", "patterns")},
                 "screen_current": cur_s_primary, "candidates": []}
        survivors = []
        for c in cands:
            ce = {"edit_kind": c["edit_kind"], "rationale": c["rationale"], "prompt_hash": prompt_hash(c["setup"]),
                  "prompt_chars": len(c["setup"]["prompt"]), "settings": c["setup"]["settings"]}
            save_setup(c["setup"])
            leak = check_leak(case, c["setup"]["prompt"], version)
            ce["leak_check"] = leak
            if not leak["ok"]:
                ce["status"] = "rejected: leakage"
                rejections.append({"round": rnd, "edit_kind": c["edit_kind"], "rationale": c["rationale"],
                                   "reason": f"leakage check failed ({leak['ngram_hits']} six-word, {leak['answer_hits']} answer hits)"})
                entry["candidates"].append(ce)
                continue
            sev = await evaluate(runner, case, c["setup"], screen, eval_id=f"r{rnd}-screen-{c['edit_kind']}")
            store.add_eval(sev, round=rnd, role="screen", edit_kind=c["edit_kind"])
            sp, sv = sev["summary"]["primary"], sev["summary"]["validity"]
            ce.update(screen_primary=sp, screen_validity=sv)
            if sp < cur_s_primary - L["screen_max_trail"] - 1e-9:
                ce["status"] = "rejected: screening (trails current)"
                rejections.append({"round": rnd, "edit_kind": c["edit_kind"], "rationale": c["rationale"],
                                   "reason": f"screening {sp:.1%} vs current {cur_s_primary:.1%}"})
            elif sv < L["screen_min_validity"]:
                ce["status"] = "rejected: screening (format validity)"
                rejections.append({"round": rnd, "edit_kind": c["edit_kind"], "rationale": c["rationale"],
                                   "reason": f"format validity {sv:.1%} on screening"})
            else:
                ce["status"] = "survived screening"
                survivors.append((sp, -len(c["setup"]["prompt"]), c, ce))
            entry["candidates"].append(ce)
        accepted = False
        if survivors:
            survivors.sort(key=lambda x: (x[0], x[1]), reverse=True)
            _, _, best, bce = survivors[0]
            dev_ev = await evaluate(runner, case, best["setup"], dev, eval_id=f"r{rnd}-dev-{best['edit_kind']}")
            store.add_eval(dev_ev, round=rnd, role="dev-candidate", edit_kind=best["edit_kind"])
            d = decide(L, dev_ev, cur_dev)
            bce["dev"] = d
            entry["decision"] = {"edit_kind": best["edit_kind"], **d}
            if d["accept"]:
                bce["status"] = "accepted"
                current, cur_dev, accepted = best["setup"], dev_ev, True
            else:
                bce["status"] = "rejected: dev decision"
                rejections.append({"round": rnd, "edit_kind": best["edit_kind"], "rationale": best["rationale"],
                                   "reason": "; ".join(d["reasons"])})
        else:
            entry["decision"] = {"accept": False, "reasons": ["no candidate survived screening"]}
        entry.update(accepted=accepted, prompt_hash_after=prompt_hash(current), dev_primary_after=cur_dev["summary"]["primary"],
                     seconds=round(time.time() - t0), spent_phase=runner.spent)
        round_log.append(entry)
        (store.dir / "round_log.json").write_text(json.dumps(round_log, indent=2, ensure_ascii=False), encoding="utf-8")
        (store.dir / "rejection_log.json").write_text(json.dumps(rejections, indent=2, ensure_ascii=False), encoding="utf-8")
        empty = 0 if accepted else empty + 1
        if empty >= L["early_stop_empty_rounds"]:
            stop_reason = f"{empty} rounds in a row with nothing accepted"
            break
    final_leak = check_leak(case, current["prompt"], version)
    (store.dir / "final_setup.json").write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    (store.dir / "round_log.json").write_text(json.dumps(round_log, indent=2, ensure_ascii=False), encoding="utf-8")
    (store.dir / "rejection_log.json").write_text(json.dumps(rejections, indent=2, ensure_ascii=False), encoding="utf-8")
    store.set(finished=True, stop_reason=stop_reason, final_prompt_hash=save_setup(current),
              final_dev_primary=cur_dev["summary"]["primary"], port_dev_primary=round_log[0]["dev_primary"],
              accepted_rounds=[e["round"] for e in round_log[1:] if e.get("accepted")],
              final_leak_check=final_leak, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
              calls_made=runner.calls_made, calls_cached=runner.calls_cached)
    return {"run_id": rid, "effort": effort, "port_dev": round_log[0]["dev_primary"],
            "final_dev": cur_dev["summary"]["primary"], "accepted_rounds": store.manifest["accepted_rounds"],
            "stop_reason": stop_reason, "spent_phase": runner.spent}

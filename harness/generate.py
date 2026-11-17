"""Plan-first data building: plan -> generate -> verify (code, then LLM) -> label -> dedupe -> split -> seal.

Pilot mode (`make pilot CASE=01 N=20`) runs the same pipeline on a few plans with a different seed and
writes data/pilot/<case>/items.jsonl; pilot items are never part of any split.
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import math
import random
import re
import time

from . import config, data
from .cases import Case
from .runner import Runner, normalise

VERIFIER_PROMPT = """You are checking one synthetic test item before it enters a benchmark.

The item was written to have exactly this correct answer:
{brief}

TEXT:
<<<
{text}
>>>

Does the TEXT contain anything that would change the correct answer, make it ambiguous, or make it wrong?
Examples: an unplanned extra entity of the kind being asked for, a second conflicting value, a missing planned
element, or wording that makes a different answer equally defensible. Ignore style and fluency.
Answer in JSON: {{"changes_answer": true|false, "reason": "<one short sentence>"}}"""

VERIFIER_SCHEMA = {"type": "object", "properties": {"changes_answer": {"type": "boolean"}, "reason": {"type": "string"}},
                   "required": ["changes_answer", "reason"], "additionalProperties": False}


def _norm_words(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())


def ngram_hashes(text: str, n: int = 6) -> set[str]:
    w = _norm_words(text)
    return {hashlib.sha1(" ".join(w[i:i + n]).encode()).hexdigest()[:12] for i in range(len(w) - n + 1)}


def phrase_hash(s: str) -> str:
    return hashlib.sha1(" ".join(_norm_words(s)).encode()).hexdigest()[:12]


def all_phrase_hashes(text: str, max_n: int = 10) -> set[str]:
    w = _norm_words(text)
    out = set()
    for n in range(1, max_n + 1):
        for i in range(len(w) - n + 1):
            out.add(hashlib.sha1(" ".join(w[i:i + n]).encode()).hexdigest()[:12])
    return out


def char_ngrams(s: str, n: int = 5) -> set[str]:
    s = re.sub(r"\s+", " ", s.lower())
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def dedupe(items: list[dict], threshold: float) -> tuple[list[dict], int, int]:
    seen, out, exact, near = set(), [], 0, 0
    grams: list[set] = []
    for it in items:
        h = hashlib.sha256(it["input"].encode()).hexdigest()
        if h in seen:
            exact += 1
            continue
        g = char_ngrams(it["input"])
        dup = False
        for g2 in grams:
            small, big = (g, g2) if len(g) < len(g2) else (g2, g)
            if not small or len(small) / max(1, len(big)) < threshold:  # Jaccard can't exceed the size ratio
                continue
            inter = len(small & big)
            if inter / (len(small) + len(big) - inter) > threshold:
                dup = True
                break
        if dup:
            near += 1
            continue
        seen.add(h)
        grams.append(g)
        out.append(it)
    return out, exact, near


def stratified_split(items: list[dict], sizes: dict[str, int], seed: int) -> dict[str, list[dict]]:
    """Allocate items to splits in proportion within each slice; fill exact sizes from leftovers."""
    rng = random.Random(seed)
    by_slice: dict[str, list[dict]] = {}
    for it in items:
        by_slice.setdefault(it["slice"], []).append(it)
    for v in by_slice.values():
        rng.shuffle(v)
    total_needed = sum(sizes.values())
    n_avail = len(items)
    scale = min(1.0, n_avail / total_needed) if total_needed else 1.0
    out = {s: [] for s in sizes}
    leftovers = []
    for sl in sorted(by_slice):
        pool = by_slice[sl]
        share = len(pool) / n_avail
        pos = 0
        for split, size in sizes.items():
            k = int(math.floor(share * size * scale))
            out[split] += pool[pos:pos + k]
            pos += k
        leftovers += pool[pos:]
    rng.shuffle(leftovers)
    for split, size in sizes.items():
        while len(out[split]) < size and leftovers:
            out[split].append(leftovers.pop())
    return out


async def _gen_one(runner: Runner, case: Case, plan: dict, idx: int) -> dict:
    g = config.role("generator")
    body = {"input": [{"role": "user", "content": case.generator_prompt(plan)}], "reasoning": {"effort": g["effort"]}}
    r = await runner.call(g["model"], "responses", body, purpose="generate")
    if r["raw"] is None:
        return {"ok": False, "stage": "generate_error", "why": r["error_code"]}
    text = normalise("responses", r["raw"])["text"]
    try:
        inp = case.make_input(plan, text)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": "make_input", "why": str(e)[:200]}
    ok, why = case.verify(plan, inp)
    if not ok:
        return {"ok": False, "stage": "code_verify", "why": why, "input": inp}
    v = config.role("verifier")
    vbody = {"input": [{"role": "user", "content": VERIFIER_PROMPT.format(brief=case.verifier_brief(plan), text=inp)}],
             "reasoning": {"effort": v["effort"]},
             "text": {"format": {"type": "json_schema", "name": "verdict", "schema": VERIFIER_SCHEMA, "strict": True}}}
    vr = await runner.call(v["model"], "responses", vbody, purpose="verify")
    if vr["raw"] is None:
        return {"ok": False, "stage": "verify_error", "why": vr["error_code"], "input": inp}
    try:
        verdict = json.loads(normalise("responses", vr["raw"])["text"])
    except Exception:
        return {"ok": False, "stage": "verify_parse", "why": "unparseable verifier output", "input": inp}
    if verdict.get("changes_answer"):
        return {"ok": False, "stage": "llm_verify", "why": verdict.get("reason", ""), "input": inp}
    return {"ok": True, "input": inp}


def slice_sequence(case: Case, variant: str, n: int, seed: int) -> list[str]:
    """Deterministic slice assignment: equal shares, or the case's slice_weights(variant) if defined."""
    slices = case.slices() if variant == "main" else case.shift_slices()
    f = getattr(case.mod, "slice_weights", None)
    w = f(variant) if f else None
    if not w:
        return [slices[i % len(slices)] for i in range(n)]
    total = sum(w.get(s, 0) for s in slices)
    counts = {s: int(n * w.get(s, 0) / total) for s in slices}
    rest = n - sum(counts.values())
    for s in sorted(slices, key=lambda s: -w.get(s, 0))[:rest]:
        counts[s] += 1
    seq = [s for s in slices for _ in range(counts[s])]
    random.Random(seed).shuffle(seq)
    return seq


def make_plans(case: Case, variant: str, n: int, base_seed: int) -> list[tuple[int, dict]]:
    seq = slice_sequence(case, variant, n, base_seed)
    plans = []
    for i in range(n):
        sl = seq[i]
        seed = base_seed + i
        plans.append((seed, {**case.plan(random.Random(seed), sl, variant), "slice": sl, "variant": variant}))
    return plans


async def run_pipeline(runner: Runner, case: Case, plans: list[tuple[int, dict]]) -> tuple[list[dict], list[dict]]:
    results = await asyncio.gather(*[_gen_one(runner, case, p, i) for i, (_, p) in enumerate(plans)])
    kept, dropped = [], []
    for (seed, plan), res in zip(plans, results):
        if res["ok"]:
            kept.append({"plan": plan, "plan_seed": seed, "input": res["input"]})
        else:
            dropped.append({"plan_seed": seed, "slice": plan["slice"], "variant": plan["variant"], "stage": res["stage"],
                            "why": res["why"]})
    return kept, dropped


def _to_item(case: Case, k: dict, version: int, n: int) -> dict:
    plan = k["plan"]
    return {"case": case.id, "id": f"{case.id}-v{version}-{n:05d}", "slice": plan["slice"], "variant": plan["variant"],
            "input": k["input"], **case.item_extras(plan), "expected": case.label(plan), "plan": plan,
            "plan_seed": k["plan_seed"], "dataset_version": version}


async def pilot(case_id: str, n: int = 20, phase: str = "P2") -> dict:
    case = Case(case_id)
    runner = Runner(phase=phase, purpose=f"pilot {case.id}")
    plans = make_plans(case, "main", n, 900_000_000 + int(case.id) * 1000) + \
        make_plans(case, "shift", max(2, n // 4), 950_000_000 + int(case.id) * 1000)
    kept, dropped = await run_pipeline(runner, case, plans)
    items = [{**_to_item(case, k, 0, i), "split": "pilot"} for i, k in enumerate(kept)]
    out = config.DATA / "pilot" / case.folder
    data.write_jsonl(out / "items.jsonl", items)
    data.write_jsonl(out / "dropped.jsonl", dropped)
    return {"kept": len(kept), "dropped": len(dropped), "drop_rate": len(dropped) / max(1, len(plans)),
            "by_stage": _count(dropped, "stage"), "spent_phase": runner.spent}


def _count(rows, key):
    out: dict = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


async def build(case_id: str, version: int = 1, gen_seed: int | None = None, phase: str = "P2",
                force: bool = False) -> dict:
    case = Case(case_id)
    sz = config.sizes()
    splits = sz["splits"]
    if data.manifest_path(case.folder, version).exists() and not force:
        raise RuntimeError(f"{case.folder} v{version} is already sealed; bump the dataset version to rebuild")
    gen_seed = gen_seed if gen_seed is not None else version * 1000 + int(case.id)
    runner = Runner(phase=phase, purpose=f"data {case.id} v{version}")
    over = sz["overgenerate"]
    n_main = math.ceil((splits["train"] + splits["dev"] + splits["test"]) * over)
    n_shift = math.ceil(splits["shift"] * over)
    plans = make_plans(case, "main", n_main, gen_seed * 100_000) + make_plans(case, "shift", n_shift,
                                                                               gen_seed * 100_000 + 50_000)
    t0 = time.time()
    kept, dropped = await run_pipeline(runner, case, plans)
    drop_rate = len(dropped) / len(plans)
    report_dir = config.DATA / "stats"
    report_dir.mkdir(parents=True, exist_ok=True)
    vname = data.version_dir(case.folder, version)
    data.write_jsonl(report_dir / f"{vname}.dropped.jsonl", dropped)
    if drop_rate > sz["max_drop_rate"]:
        raise RuntimeError(f"{case.folder}: drop rate {drop_rate:.1%} exceeds {sz['max_drop_rate']:.0%}; "
                           f"fix the generator prompt (see data/stats/{vname}.dropped.jsonl)")
    items = [_to_item(case, k, version, i) for i, k in enumerate(kept)]
    main = [it for it in items if it["variant"] == "main"]
    shift = [it for it in items if it["variant"] == "shift"]
    main, ex1, nd1 = dedupe(main, sz["near_dup_threshold"])
    shift, ex2, nd2 = dedupe(shift, sz["near_dup_threshold"])
    parts = stratified_split(main, {"test": splits["test"], "dev": splits["dev"], "train": splits["train"]}, gen_seed)
    parts["shift"] = stratified_split(shift, {"shift": splits["shift"]}, gen_seed)["shift"]
    hashes = {}
    for split in ("train", "dev", "test", "shift"):
        rows = sorted(parts[split], key=lambda r: r["id"])
        for r in rows:
            r["split"] = split
        if split in data.SEALED_SPLITS:
            data.log_sealed_access(case.folder, split, version, "write(generate)")
        hashes[split] = data.write_jsonl(data.split_path(case.folder, split, version), rows)
    # leakage index: hashed 6-grams of every input and hashed answer phrases, all splits
    leak = {"ngrams": set(), "answers": set()}
    for split in ("train", "dev", "test", "shift"):
        for r in parts[split]:
            leak["ngrams"] |= ngram_hashes(r["input"])
            for a in case.answer_strings(r["expected"]):
                if len(a.strip()) >= 5:
                    leak["answers"].add(phrase_hash(a))
    lp = config.DATA / "leak" / f"{vname}.json.gz"
    lp.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(lp, "wt", encoding="utf-8") as f:
        json.dump({"ngrams": sorted(leak["ngrams"]), "answers": sorted(leak["answers"])}, f)
    stats = {"case": case.folder, "dataset_version": version, "gen_seed": gen_seed, "planned": len(plans),
             "kept": len(kept), "dropped": len(dropped), "drop_rate": drop_rate, "dropped_by_stage": _count(dropped, "stage"),
             "exact_duplicates": ex1 + ex2, "near_duplicates": nd1 + nd2,
             "items_per_split": {s: len(parts[s]) for s in parts},
             "items_per_slice_and_split": {s: _count(parts[s], "slice") for s in parts},
             "avg_input_chars": {s: (sum(len(r["input"]) for r in parts[s]) / max(1, len(parts[s]))) for s in parts},
             "avg_input_tokens_est": {s: (sum(len(r["input"]) for r in parts[s]) / max(1, len(parts[s])) / 4) for s in parts},
             "spent_usd_phase_total": runner.spent, "seconds": round(time.time() - t0)}
    (report_dir / f"{vname}.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    man = {"case": case.folder, "dataset_version": version, "gen_seed": gen_seed, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "generator": config.role("generator"), "verifier": config.role("verifier"),
           "generator_model_id": config.model_cfg(config.role("generator")["model"])["model_id"],
           "verifier_model_id": config.model_cfg(config.role("verifier")["model"])["model_id"],
           "sdk_version": config.sdk_version(), "git_commit": config.git_commit(),
           "sizes": {s: len(parts[s]) for s in parts}, "sha256": hashes,
           "frozen_files_sha256": {f: data.text_sha256(case.dir / f) for f in ("spec.md", "case.py")}}
    mp = data.manifest_path(case.folder, version)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    data.rebuild_manifest()
    return stats

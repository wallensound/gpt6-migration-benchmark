"""Run one setup over a list of items, score every output and summarise."""
from __future__ import annotations

import asyncio
import gzip
import json
import time
from pathlib import Path

import numpy as np

from . import config, requests, stats
from .cases import Case, prompt_hash
from .runner import Runner, normalise


async def _one(runner: Runner, case: Case, setup: dict, item: dict, repeat: int, purpose: str) -> dict:
    s = setup.get("settings") or {}
    samples = int(s.get("samples") or 1)
    model, api, body = requests.build(case, setup, item)
    res = await asyncio.gather(*[runner.call(model, api, body, repeat=repeat * 10 + k, purpose=purpose)
                                 for k in range(samples)])
    outs = [normalise(api, r["raw"]) for r in res]
    err = next((r["error_code"] for r in res if r["raw"] is None), None)
    if err:
        sc = {"passed": False, "valid": False, "nonanswer": False, "secondary": {}, "categories": ["api_error"],
              "diff": f"api error: {err}: {res[0].get('error_message')}"}
        parsed = None
    else:
        parsed = case.parse(outs if samples > 1 else outs[0], s, item)
        sc = case.score(item["expected"], parsed)
    raw_output = outs[0]["text"] if not outs[0]["tool_calls"] else json.dumps(outs[0]["tool_calls"], ensure_ascii=False)
    if samples > 1:
        raw_output = json.dumps([o["text"] for o in outs], ensure_ascii=False)
    tok = {k: sum(r[k] for r in res) for k in ("tokens_in", "tokens_cached", "tokens_cache_write", "tokens_out",
                                               "tokens_reasoning")}
    return {"item_id": item["id"], "split": item["split"], "slice": item["slice"], "raw_output": raw_output,
            "parsed": parsed, "valid": bool(sc.get("valid")), "passed": bool(sc.get("passed")),
            "nonanswer": bool(sc.get("nonanswer")), "secondary": sc.get("secondary") or {},
            "categories": sc.get("categories") or [], "diff": sc.get("diff", ""), **tok,
            "latency_ms": max(r["latency_ms"] for r in res), "cost_usd": sum(r["cost_usd"] for r in res),
            "error_code": err or next((r["error_code"] for r in res if r["error_code"]), None),
            "from_cache": all(r["from_cache"] for r in res)}


async def evaluate(runner: Runner, case: Case, setup: dict, items: list[dict], *, repeat: int = 0,
                   eval_id: str = "", purpose: str = "eval", guard: bool = True) -> dict:
    if guard:
        jobs = []
        samples = int((setup.get("settings") or {}).get("samples") or 1)
        for it in items:
            model, api, body = requests.build(case, setup, it)
            jobs += [(model, api, body, repeat * 10 + k) for k in range(samples)]
        runner.guard(jobs, label=f"{case.id} {eval_id}")
    rows = await asyncio.gather(*[_one(runner, case, setup, it, repeat, purpose) for it in items])
    return {"eval_id": eval_id, "setup": setup, "prompt_hash": prompt_hash(setup), "repeat": repeat,
            "rows": list(rows), "summary": summarise(case, list(rows))}


def summarise(case: Case, rows: list[dict]) -> dict:
    n = len(rows)
    passed = np.array([r["passed"] for r in rows], dtype=bool)
    k = int(passed.sum())
    lat = np.array([r["latency_ms"] for r in rows if r["latency_ms"]] or [0.0])
    cost = float(sum(r["cost_usd"] for r in rows))
    per_slice = {}
    for r in rows:
        d = per_slice.setdefault(r["slice"], [0, 0])
        d[0] += 1
        d[1] += int(r["passed"])
    out = {
        "n": n, "passed": k, "primary": k / n if n else 0.0,
        "primary_ci": list(stats.wilson(k, n)) if n else [0.0, 0.0],
        "validity": float(np.mean([r["valid"] for r in rows])) if n else 0.0,
        "nonanswer_rate": float(np.mean([r["nonanswer"] for r in rows])) if n else 0.0,
        "error_rate": float(np.mean([bool(r["error_code"]) and r["parsed"] is None for r in rows])) if n else 0.0,
        "per_slice": {s: {"n": a, "primary": b / a} for s, (a, b) in sorted(per_slice.items())},
        "cost_usd": cost, "cost_per_item": cost / n if n else 0.0,
        "cost_per_correct": cost / k if k else None,
        "latency_p50_s": float(np.percentile(lat, 50)) / 1000, "latency_p95_s": float(np.percentile(lat, 95)) / 1000,
    }
    for t in ("tokens_in", "tokens_cached", "tokens_cache_write", "tokens_out", "tokens_reasoning"):
        out[t] = int(sum(r[t] for r in rows))
        out[t + "_mean"] = out[t] / n if n else 0.0
    cats: dict[str, int] = {}
    for r in rows:
        if not r["passed"]:
            for c in r["categories"] or ["other"]:
                cats[c] = cats.get(c, 0) + 1
    out["failure_categories"] = dict(sorted(cats.items(), key=lambda x: -x[1]))
    try:
        out["secondary"] = case.aggregate(rows)
    except Exception as e:  # a broken aggregate must not lose the run
        out["secondary"] = {"aggregate_error": str(e)}
    return out


# --------------------------------------------------------------------------- run storage

class RunStore:
    """runs/<phase>/<run_id>/manifest.json + results.jsonl.gz (one row per item per eval)."""

    def __init__(self, phase: str, run_id: str, meta: dict, fresh: bool = True):
        self.dir = config.RUNS / phase / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.results = self.dir / "results.jsonl.gz"
        mpath = self.dir / "manifest.json"
        if fresh or not mpath.exists():
            if self.results.exists():
                self.results.unlink()
            self.manifest = {"run_id": run_id, "phase": phase, "git_commit": config.git_commit(),
                             "sdk_version": config.sdk_version(), "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "reference_date": config.REFERENCE_DATE, **meta, "evals": []}
        else:
            self.manifest = json.loads(mpath.read_text(encoding="utf-8"))
        self._write_manifest()

    def _write_manifest(self):
        (self.dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False),
                                                encoding="utf-8")

    def add_eval(self, ev: dict, **extra) -> None:
        save_setup(ev["setup"])
        with gzip.open(self.results, "at", encoding="utf-8") as f:
            for r in ev["rows"]:
                f.write(json.dumps({"run_id": self.manifest["run_id"], "eval_id": ev["eval_id"],
                                    "prompt_hash": ev["prompt_hash"], "repeat": ev["repeat"], **r},
                                   ensure_ascii=False) + "\n")
        st = ev["setup"]
        mid = config.model_cfg(st["model"])["model_id"]
        self.manifest["evals"].append({"eval_id": ev["eval_id"], "model": st["model"], "model_id": mid,
                                       "api": st["api"], "effort": st.get("effort"), "settings": st.get("settings"),
                                       "prompt_hash": ev["prompt_hash"], "repeat": ev["repeat"],
                                       "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                       "summary": ev["summary"], **extra})
        self._write_manifest()

    def set(self, **kw):
        self.manifest.update(kw)
        self._write_manifest()


def save_setup(setup: dict) -> str:
    h = prompt_hash(setup)
    p = config.RUNS / "prompts" / f"{h}.json"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(setup, indent=2, ensure_ascii=False), encoding="utf-8")
    return h


def read_results(run_dir: Path) -> list[dict]:
    p = Path(run_dir) / "results.jsonl.gz"
    if not p.exists():
        return []
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

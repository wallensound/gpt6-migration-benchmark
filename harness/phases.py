"""Phase commands: check-models (P0), calibrate (P3), sweep and mechanical port (P4)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import time

import yaml

from . import config, data, requests
from .cases import Case, prompt_hash
from .evaluate import RunStore, evaluate
from .runner import Runner, normalise

EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]


# --------------------------------------------------------------------------- P0 check-models

async def check_models() -> dict:
    runner = Runner(phase="P0", purpose="check-models")
    cfg = yaml.safe_load((config.CONFIG / "models.yaml").read_text(encoding="utf-8"))
    report = {}
    schema = {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"],
              "additionalProperties": False}
    for name, m in cfg["models"].items():
        api = m["api"]
        probed = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "supported_efforts": [], "rejected_efforts": {}}

        def body_for(effort, extra=None):
            if api == "chat":
                b = {"messages": [{"role": "user", "content": "Reply with the single word OK."}],
                     "reasoning_effort": effort}
            else:
                b = {"input": [{"role": "user", "content": "Reply with the single word OK."}],
                     "reasoning": {"effort": effort}}
            b.update(extra or {})
            return b

        res = await asyncio.gather(*[runner.call(name, api, body_for(e)) for e in EFFORTS])
        for e, r in zip(EFFORTS, res):
            if r["raw"] is not None:
                probed["supported_efforts"].append(e)
                probed["resolved_model"] = r["raw"].get("model")
            else:
                probed["rejected_efforts"][e] = (r["error_message"] or "")[:160]
        lo = probed["supported_efforts"][0] if probed["supported_efforts"] else "low"
        checks = {}
        if api == "chat":
            checks["temperature_0"] = body_for(lo, {"temperature": 0})
            checks["logprobs"] = body_for(lo, {"logprobs": True, "temperature": 0})
            checks["response_format_json_schema"] = body_for(lo, {"response_format": {"type": "json_schema", "json_schema": {"name": "w", "strict": True, "schema": schema}}})
        else:
            checks["temperature_0_at_lowest"] = body_for(lo, {"temperature": 0})
            if "low" in probed["supported_efforts"]:
                checks["temperature_0_at_low"] = body_for("low", {"temperature": 0})
            checks["text_format_json_schema"] = body_for(lo, {"text": {"format": {"type": "json_schema", "name": "w", "schema": schema, "strict": True}}})
            checks["text_verbosity_low"] = body_for(lo, {"text": {"verbosity": "low"}})
            checks["prompt_cache_options"] = body_for(lo, {"prompt_cache_options": {"ttl": "30m"}})
            checks["service_tier_flex"] = body_for(lo, {"service_tier": "flex"})
            checks["logprobs"] = body_for("none" if "none" in probed["supported_efforts"] else lo,
                                          {"include": ["message.output_text.logprobs"], "top_logprobs": 1})
        names = list(checks)
        cres = await asyncio.gather(*[runner.call(name, api, checks[k]) for k in names])
        for k, r in zip(names, cres):
            ok = r["raw"] is not None
            if k == "logprobs" and ok:
                lp = normalise(api, r["raw"])["logprobs"]
                ok = bool(lp)
                probed["logprobs_returned"] = ok
                continue
            if k == "service_tier_flex" and ok:
                probed["service_tier_returned"] = r["raw"].get("service_tier")
            probed[k] = ok
            if not ok and r["error_message"]:
                probed.setdefault("errors", {})[k] = r["error_message"][:160]
        missing = [e for e in m["efforts"] if e not in probed["supported_efforts"]]
        probed["brief_efforts_missing"] = missing
        m["probed"] = probed
        report[name] = probed
    (config.CONFIG / "models.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    config.models.cache_clear()
    return report


# --------------------------------------------------------------------------- P3 calibrate

def _cal_dir(case: Case):
    d = config.RUNS / "P3" / case.folder
    d.mkdir(parents=True, exist_ok=True)
    return d


def floor_for(case: Case) -> float:
    f = config.sizes()["calibration_floor"]
    return float(f.get(case.id, f["default"]))


def legacy_files_hash(case: Case) -> str:
    h = hashlib.sha256()
    for f in ("legacy_prompt.md", "legacy_config.yaml"):
        h.update((case.dir / f).read_bytes().replace(b"
", b"
"))
    return h.hexdigest()


def frozen_info(case: Case) -> dict | None:
    p = case.dir / "legacy_frozen.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def assert_frozen(case: Case) -> dict:
    fz = frozen_info(case)
    if not fz:
        raise RuntimeError(f"{case.folder}: legacy prompt not frozen (run make calibrate ... FREEZE=1)")
    if fz["legacy_files_sha256"] != legacy_files_hash(case):
        raise RuntimeError(f"{case.folder}: legacy prompt changed after freezing")
    return fz


async def calibrate(case_id: str, split: str = "train", freeze: bool = False, version: int = 1) -> dict:
    case = Case(case_id)
    if frozen_info(case) and not freeze:
        raise RuntimeError(f"{case.folder}: legacy prompt already frozen")
    missing = case.check_markers()
    log_path = _cal_dir(case) / "calibration_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {"rounds": []}
    setup = case.legacy_setup()
    h = prompt_hash(setup)
    if freeze:
        devs = [r for r in log["rounds"] if r["split"] == "dev" and r["prompt_hash"] == h]
        if not devs:
            raise RuntimeError("run the dev check on the current prompt before freezing")
        score = devs[-1]["primary"]
        floor = floor_for(case)
        if missing:
            raise RuntimeError(f"legacy markers missing: {missing}")
        if score < floor:
            raise RuntimeError(f"dev score {score:.3f} below floor {floor:.2f}; the case does not count")
        info = {"case": case.folder, "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "prompt_hash": h,
                "legacy_files_sha256": legacy_files_hash(case), "dev_primary": score, "floor": floor,
                "train_rounds": len({r["prompt_hash"] for r in log["rounds"] if r["split"] == "train"}),
                "source_model_id": config.model_cfg(setup["model"])["model_id"]}
        (case.dir / "legacy_frozen.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        return info
    if split not in ("train", "dev"):
        raise ValueError("calibration uses train (tuning) and dev (floor check) only")
    train_hashes = {r["prompt_hash"] for r in log["rounds"] if r["split"] == "train"}
    if split == "train" and h not in train_hashes and len(train_hashes) >= config.sizes()["calibration_max_rounds"]:
        raise RuntimeError("calibration is limited to four tuning rounds on train")
    items = data.load_split(case.folder, split, version)
    runner = Runner(phase="P3", purpose=f"calibrate {case.id}")
    ev = await evaluate(runner, case, setup, items, eval_id=f"calibrate-{split}-{h}")
    store = RunStore("P3", f"{case.folder}-calibrate-{split}-{h}",
                     {"case": case.folder, "kind": "calibrate", "dataset_version": version, "seed": None})
    store.add_eval(ev)
    s = ev["summary"]
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "split": split, "prompt_hash": h, "primary": s["primary"],
             "validity": s["validity"], "per_slice": s["per_slice"], "markers_missing": missing}
    log["rounds"].append(entry)
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    if split == "train":  # failures are visible for tuning; dev items never are
        fails = [{"item_id": r["item_id"], "slice": r["slice"], "diff": r["diff"], "raw_output": r["raw_output"][:1500],
                  "categories": r["categories"]} for r in ev["rows"] if not r["passed"]]
        data.write_jsonl(_cal_dir(case) / f"train-failures-{h}.jsonl", fails)
    return {"split": split, "prompt_hash": h, "primary": s["primary"], "primary_ci": s["primary_ci"],
            "validity": s["validity"], "nonanswer_rate": s["nonanswer_rate"], "per_slice": s["per_slice"],
            "failure_categories": s["failure_categories"], "secondary": s["secondary"], "cost_usd": s["cost_usd"],
            "markers_missing": missing, "floor": floor_for(case)}


# --------------------------------------------------------------------------- P4 sweep

PROTOCOL_LOCK = config.RUNS / "protocol_lock.json"


def lock_protocol() -> dict:
    """Before the first sweep call: PROTOCOL.md must be committed and unchanged; record its hash once."""
    p = config.ROOT / "PROTOCOL.md"
    if not p.exists():
        raise RuntimeError("PROTOCOL.md must exist and be committed before the sweep")
    st = subprocess.run(["git", "status", "--porcelain", "PROTOCOL.md"], cwd=config.ROOT, capture_output=True, text=True).stdout
    logged = subprocess.run(["git", "log", "--oneline", "--", "PROTOCOL.md"], cwd=config.ROOT, capture_output=True, text=True).stdout
    if st.strip() or not logged.strip():
        raise RuntimeError("PROTOCOL.md has uncommitted changes or was never committed")
    h = data.text_sha256(p)
    if PROTOCOL_LOCK.exists():
        lock = json.loads(PROTOCOL_LOCK.read_text(encoding="utf-8"))
        if lock["sha256"] != h:
            raise RuntimeError("PROTOCOL.md changed after the first sweep call; this is forbidden")
        return lock
    lock = {"sha256": h, "locked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "commit": subprocess.run(["git", "log", "-1", "--format=%h", "--", "PROTOCOL.md"], cwd=config.ROOT,
                                     capture_output=True, text=True).stdout.strip()}
    PROTOCOL_LOCK.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    return lock


def targets() -> list[str]:
    return [n for n, m in config.models()["models"].items() if m["role"] == "target"]


def target_efforts(name: str) -> list[str]:
    m = config.model_cfg(name)
    sup = (m.get("probed") or {}).get("supported_efforts")
    return [e for e in m["efforts"] if not sup or e in sup]


async def sweep(case_id: str, version: int = 1) -> dict:
    lock_protocol()
    case = Case(case_id)
    assert_frozen(case)
    dev = data.load_split(case.folder, "dev", version)
    runner = Runner(phase="P4", purpose=f"sweep {case.id}")
    legacy = case.legacy_setup()
    store = RunStore("P4", f"{case.folder}-sweep", {"case": case.folder, "kind": "sweep", "dataset_version": version})
    rows = []
    src = await evaluate(runner, case, legacy, dev, eval_id="source")
    store.add_eval(src, role="source")
    rows.append({"setting": f"{legacy['model']} / {legacy['effort']} (legacy, chat)", "model": legacy["model"],
                 "effort": legacy["effort"], **_brief(src["summary"])})
    probes = {}
    for t in targets():
        for e in target_efforts(t):
            # literal swap probe: one call with the legacy parameters unchanged
            lit = requests.literal_swap(legacy, t, e)
            model, api, body = requests.build(case, lit, dev[0])
            r = await runner.call(model, api, body, purpose="literal-swap probe")
            probes[f"{t}/{e}"] = {"accepted": r["raw"] is not None, "error": (r["error_message"] or "")[:200]}
            port = requests.mechanical_port(case, legacy, t, e)
            ev = await evaluate(runner, case, port, dev, eval_id=f"port-{t}-{e}")
            store.add_eval(ev, role="port", literal_swap=probes[f"{t}/{e}"])
            rows.append({"setting": f"{t} / {e}", "model": t, "effort": e, **_brief(ev["summary"])})
    choice = choose_efforts(rows)
    out = {"case": case.folder, "source": rows[0], "rows": rows, "literal_swap": probes, "effort_choice": choice,
           "spent_phase": runner.spent}
    store.set(effort_choice=choice, literal_swap=probes, finished=True)
    (config.RUNS / "P4" / f"{case.folder}-sweep" / "sweep.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def _brief(s: dict) -> dict:
    return {"primary": s["primary"], "primary_ci": s["primary_ci"], "validity": s["validity"],
            "nonanswer_rate": s["nonanswer_rate"], "error_rate": s["error_rate"], "cost_per_item": s["cost_per_item"],
            "cost_per_correct": s["cost_per_correct"], "latency_p50_s": s["latency_p50_s"],
            "latency_p95_s": s["latency_p95_s"], "tokens_in_mean": s["tokens_in_mean"],
            "tokens_out_mean": s["tokens_out_mean"], "tokens_reasoning_mean": s["tokens_reasoning_mean"],
            "failure_categories": s["failure_categories"], "per_slice": s["per_slice"]}


def choose_efforts(rows: list[dict]) -> dict:
    """Per target: the effort with the best primary score per dollar; on ties, the lower effort."""
    order = {e: i for i, e in enumerate(EFFORTS)}
    out = {}
    for t in targets():
        cands = [r for r in rows if r["model"] == t]
        if not cands:
            continue

        def spd(r):
            return r["primary"] / r["cost_per_item"] if r["cost_per_item"] > 0 else 0.0

        best = max(cands, key=lambda r: (round(spd(r), 9), -order[r["effort"]]))
        out[t] = {"effort": best["effort"], "score_per_dollar": spd(best),
                  "candidates": {r["effort"]: {"primary": r["primary"], "score_per_dollar": spd(r)} for r in cands}}
    return out


def effort_choice(case: Case) -> dict:
    p = config.RUNS / "P4" / f"{case.folder}-sweep" / "sweep.json"
    if not p.exists():
        raise RuntimeError(f"{case.folder}: run the sweep first")
    return json.loads(p.read_text(encoding="utf-8"))["effort_choice"]

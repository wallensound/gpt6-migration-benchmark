"""Offline end-to-end test of the optimisation loop on the stub case with a fake transport."""
import asyncio
import json
import random

import pytest

from harness import loop as LP
from harness import optimiser as OP
from harness import runner as R


def _resp(text):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": 100, "output_tokens": 10, "output_tokens_details": {"reasoning_tokens": 0},
                      "input_tokens_details": {"cached_tokens": 0}}, "status": "completed"}


def make_items(stub_case, n, split):
    rng = random.Random(split)
    out = []
    for i in range(n):
        c = rng.choice(["red", "green", "blue", "yellow", "purple"])
        out.append({"id": f"{split}-{i}", "split": split, "slice": "plain" if i % 2 else "distractor",
                    "input": f"The {c} kite number {i} flew.", "expected": c})
    return out


@pytest.fixture
def patched(monkeypatch, stub_case, tmp_path):
    train, dev = make_items(stub_case, 120, "train"), make_items(stub_case, 200, "dev")
    monkeypatch.setattr(LP.data, "load_split", lambda f, s, v=1: {"train": train, "dev": dev}[s])
    monkeypatch.setattr(LP, "effort_choice", lambda c: {"gpt-6-luna": {"effort": "low"}})
    monkeypatch.setattr(LP, "assert_frozen", lambda c: {})
    monkeypatch.setattr(LP, "lock_protocol", lambda: {})
    monkeypatch.setattr(LP, "Case", lambda cid: stub_case)
    monkeypatch.setattr(OP, "leak_index", lambda f, v: (frozenset(), frozenset()))
    monkeypatch.setattr(LP.config, "RUNS", tmp_path / "runs")
    import harness.evaluate as EV
    monkeypatch.setattr(EV.config, "RUNS", tmp_path / "runs")

    async def transport(provider, model_id, api, body):
        fmt = ((body.get("text") or {}).get("format") or {}).get("name")
        if fmt == "candidates":
            kinds = body["text"]["format"]["schema"]["properties"]["candidates"]["items"]["properties"]["edit_kind"]["enum"]
            return _resp(json.dumps({"candidates": [
                {"edit_kind": k, "rationale": f"try {k}", "settings": {"verbosity": None},
                 "prompt": "Reply with ONLY the colour word, lowercase." + (" GOOD" if k == kinds[0] else "")}
                for k in kinds]}))
        if fmt == "out":
            props = body["text"]["format"]["schema"]["properties"]
            if "category" in props:
                return _resp(json.dumps({"category": "wrong_value", "cause": "said a wrong colour"}))
            return _resp(json.dumps({"input": "A teal hat.", "expected": "teal", "output": "hat"}))
        prompt = body["input"][0]["content"]
        user = body["input"][1]["content"]
        colour = next(w for w in user.split() if w in ("red", "green", "blue", "yellow", "purple"))
        h = sum(map(ord, user)) % 10
        # the legacy/port prompt is right 70% of the time, the "GOOD" candidate 97%
        ok = h < (10 if "GOOD" in prompt and h != 3 else 7)
        return _resp(colour if ok else "orange")

    orig_init = R.Runner.__post_init__

    def init(self):
        self.transport = transport
        self.state_path = tmp_path / "s.sqlite"
        orig_init(self)
    monkeypatch.setattr(R.Runner, "__post_init__", init)
    return tmp_path


def test_loop_accepts_better_candidate(patched):
    out = asyncio.run(LP.run_loop("00", "gpt-6-luna", 11, phase="P5"))
    assert out["port_dev"] < 0.8 and out["final_dev"] > 0.85
    assert out["accepted_rounds"] and out["accepted_rounds"][0] == 1
    d = patched / "runs" / "P5" / out["run_id"]
    log = json.loads((d / "round_log.json").read_text())
    assert log[1]["accepted"] and log[1]["decision"]["mcnemar"]["p_value"] < 0.05
    rej = json.loads((d / "rejection_log.json").read_text())
    assert all("reason" in r for r in rej)
    assert json.loads((d / "final_setup.json").read_text())["prompt"].endswith("GOOD")


def test_decide_rejects_slice_drop():
    def ev(passes, slices):
        rows = [{"item_id": str(i), "passed": p, "slice": s} for i, (p, s) in enumerate(zip(passes, slices))]
        per = {}
        for r in rows:
            per.setdefault(r["slice"], []).append(r["passed"])
        return {"rows": rows, "summary": {"validity": 1.0, "primary": sum(passes) / len(passes),
                                          "per_slice": {k: {"primary": sum(v) / len(v)} for k, v in per.items()}}}
    slices = ["a"] * 100 + ["b"] * 100
    cur = ev([False] * 40 + [True] * 60 + [True] * 100, slices)
    cand = ev([True] * 100 + [True] * 95 + [False] * 5, slices)  # big gain on a, 5-point drop on b
    d = LP.decide({"accept_alpha": 0.05, "accept_max_slice_drop": 0.02, "accept_min_validity": 0.99}, cand, cur)
    assert not d["accept"] and any("slice 'b'" in r for r in d["reasons"])


def test_settings_schema_handles_null_and_bool():
    s = OP.settings_schema({"verbosity": [None, "low"], "structured_outputs": [False, True]})
    assert s["properties"]["verbosity"]["type"] == ["null", "string"]
    assert s["properties"]["structured_outputs"]["type"] == "boolean"

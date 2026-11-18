"""Bring-your-own-data import: CSV/JSONL -> sealed splits that the rest of the pipeline reads unchanged."""
import asyncio
import csv
import json
import shutil

import pytest

from harness import byod, data
from harness.cases import Case
from tests.conftest import ROOT

LABELS = ["billing", "technical", "shipping", "returns"]


@pytest.fixture
def byod_case(tmp_path, monkeypatch):
    folder = tmp_path / "97-demo"
    shutil.copytree(ROOT / "cases" / "_template-byod", folder)
    (folder / "legacy_prompt.md").write_text("Reply with ONLY one label: billing, technical, shipping or returns.")
    monkeypatch.setattr(byod.config, "DATA", tmp_path / "data")
    monkeypatch.setattr(data, "ACCESS_LOG", tmp_path / "sealed_access.log")
    return folder


def write_csv(path, n, start=0, slice_=True):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "input", "expected", "slice"] if slice_ else ["input", "expected"])
        for i in range(start, start + n):
            lab = LABELS[i % 4]
            text = f"Ticket {i}: customer number {i * 7} writes about {lab} issue with order {i * 13}."
            w.writerow([f"T{i}", text, lab, "short" if i % 3 else "long"] if slice_ else [text, lab])


def test_import_csv_full_size(byod_case, tmp_path):
    write_csv(tmp_path / "ex.csv", 700)
    write_csv(tmp_path / "later.csv", 160, start=5000)
    st = byod.import_examples(str(byod_case), tmp_path / "ex.csv", shift_file=tmp_path / "later.csv")
    assert st["items_per_split"] == {"test": 300, "dev": 200, "train": 120, "shift": 150}
    case = Case(str(byod_case))
    train = data.load_split(case.folder, "train")
    assert train[0]["expected"] in LABELS and train[0]["source"] == "imported" and "source_id" in train[0]
    assert {r["slice"] for r in train} == {"short", "long"}
    man = json.loads(data.manifest_path(case.folder, 1).read_text())
    assert data.verify_hashes(case.folder, 1) == [] and set(man["sha256"]) == {"train", "dev", "test", "shift"}
    with pytest.raises(data.SealedAccessError):
        data.load_split(case.folder, "test")
    with pytest.raises(RuntimeError):
        byod.import_examples(str(byod_case), tmp_path / "ex.csv")  # already sealed


def test_import_small_jsonl_scales_and_parses_json(byod_case, tmp_path):
    rows = [{"input": f"Invoice {i} from vendor {i * 3} total {i}.50", "expected": json.dumps({"total": f"{i}.50"})}
            for i in range(150)]
    (tmp_path / "ex.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    st = byod.import_examples(str(byod_case), tmp_path / "ex.jsonl")
    sz = st["items_per_split"]
    assert sz["shift"] == 0 and sum(sz.values()) == 150 and sz["test"] > sz["dev"] > sz["train"] >= 20
    item = data.load_split(Case(str(byod_case)).folder, "dev")[0]
    assert isinstance(item["expected"], dict)


def test_import_rejects_bad_files(byod_case, tmp_path):
    (tmp_path / "bad.csv").write_text("text,label\nhello,x\n")
    with pytest.raises(ValueError):
        byod.import_examples(str(byod_case), tmp_path / "bad.csv")
    write_csv(tmp_path / "tiny.csv", 30)
    with pytest.raises(RuntimeError):
        byod.import_examples(str(byod_case), tmp_path / "tiny.csv")


def test_imported_items_run_through_evaluate(byod_case, tmp_path):
    write_csv(tmp_path / "ex.csv", 200, slice_=False)
    byod.import_examples(str(byod_case), tmp_path / "ex.csv")
    case = Case(str(byod_case))
    dev = data.load_split(case.folder, "dev")
    from harness import runner as R
    from harness.evaluate import evaluate

    async def transport(provider, model_id, api, body):
        user = body["messages"][1]["content"]
        lab = next(l for l in LABELS if l in user)
        return {"choices": [{"message": {"content": lab}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 2}}
    r = R.Runner(phase="P3", transport=transport, state_path=tmp_path / "s.sqlite")
    ev = asyncio.run(evaluate(r, case, case.legacy_setup(), dev, eval_id="byod"))
    assert ev["summary"]["n"] == len(dev) and ev["summary"]["primary"] == 1.0

"""Bring your own data: import real examples instead of generating synthetic ones.

    python -m harness.cli import 09 --file my_examples.csv [--shift-file later_examples.csv]

The file has one example per row (CSV with a header, or JSONL):

    input      required  the text the model receives (the user message)
    expected   required  the known-good answer; JSON is parsed when it looks like JSON
                         (e.g. ["Acme", "Velmora"] or {"total": "12.50"}), otherwise kept as text
    slice      optional  a group name used for per-slice scores and stratified splits (default "all")
    id         optional  your own id (kept as source_id)
    any other column     copied onto the item, e.g. "context" (the default user message appends it)

This replaces the plan -> generate -> verify -> label steps of the synthetic pipeline. Everything after it
(dedupe, stratified split, sealing, MANIFEST hashes, stats, leakage index) is identical, so calibrate, sweep,
loop, final and report work unchanged. The case folder still needs spec.md, legacy_prompt.md,
legacy_config.yaml and a case.py with parse() and score(); see cases/_template-byod/.

Split sizes: config/sizes.yaml (train 120, dev 200, test 300, shift 150) when there are enough examples;
otherwise the main examples are split in the same proportions (train 19%, dev 32%, test 48%). The shift
split comes only from --shift-file (e.g. newer or harder examples); without it the shift set is empty and the
final phase skips it.
"""
from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path

from . import config, data
from .cases import Case
from .generate import _count, dedupe, ngram_hashes, phrase_hash, stratified_split

RESERVED = {"case", "id", "split", "slice", "variant", "input", "expected", "plan", "plan_seed", "dataset_version"}


def _parse_expected(v):
    if not isinstance(v, str):
        return v
    s = v.strip()
    if s[:1] in "[{\"" or s in ("null", "true", "false"):
        try:
            return json.loads(s)
        except ValueError:
            return v
    return v


def read_examples(path: str | Path) -> list[dict]:
    """Read a CSV (with header) or JSONL file into a list of dicts with at least input and expected."""
    path = Path(path)
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    elif path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
    else:
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    out = []
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict) or "input" not in r or "expected" not in r:
            raise ValueError(f"{path.name} row {i}: needs 'input' and 'expected' columns")
        if not str(r["input"]).strip():
            raise ValueError(f"{path.name} row {i}: empty input")
        out.append(r)
    return out


def _to_items(case: Case, rows: list[dict], variant: str, version: int, start: int) -> list[dict]:
    items = []
    for k, r in enumerate(rows):
        extras = {key: val for key, val in r.items() if key not in RESERVED and val not in (None, "")}
        if "id" in r and r["id"] not in (None, ""):
            extras["source_id"] = str(r["id"])
        items.append({"case": case.id, "id": f"{case.id}-v{version}-{start + k:05d}",
                      "slice": str(r.get("slice") or "all").strip() or "all", "variant": variant,
                      "input": str(r["input"]), **extras, "expected": _parse_expected(r["expected"]),
                      "plan": None, "plan_seed": None, "dataset_version": version, "source": "imported"})
    return items


def import_examples(case_id: str, file: str | Path, shift_file: str | Path | None = None, version: int = 1,
                    seed: int | None = None, force: bool = False) -> dict:
    case = Case(case_id)
    if data.manifest_path(case.folder, version).exists() and not force:
        raise RuntimeError(f"{case.folder} v{version} is already sealed; bump the dataset version to re-import")
    sz = config.sizes()
    seed = seed if seed is not None else version * 1000 + int(case.id)
    main_rows = read_examples(file)
    shift_rows = read_examples(shift_file) if shift_file else []
    main = _to_items(case, main_rows, "main", version, 0)
    shift = _to_items(case, shift_rows, "shift", version, len(main))
    main, ex1, nd1 = dedupe(main, sz["near_dup_threshold"])
    shift, ex2, nd2 = dedupe(shift, sz["near_dup_threshold"])
    target = {"test": sz["splits"]["test"], "dev": sz["splits"]["dev"], "train": sz["splits"]["train"]}
    need = sum(target.values())
    if len(main) < need:  # fewer examples than the default sizes: keep the same proportions
        scale = len(main) / need
        target = {s: int(math.floor(n * scale)) for s, n in target.items()}
        target["test"] += len(main) - sum(target.values())
    if min(target.values()) < 20:
        raise RuntimeError(f"only {len(main)} usable examples after dedupe; at least ~110 are needed "
                           "for train/dev/test splits of 20+ items each")
    parts = stratified_split(main, target, seed)
    parts["shift"] = stratified_split(shift, {"shift": min(len(shift), sz["splits"]["shift"])}, seed)["shift"] if shift else []
    hashes = {}
    for split in ("train", "dev", "test", "shift"):
        rows = sorted(parts[split], key=lambda r: r["id"])
        for r in rows:
            r["split"] = split
        if split in data.SEALED_SPLITS:
            data.log_sealed_access(case.folder, split, version, "write(import)")
        hashes[split] = data.write_jsonl(data.split_path(case.folder, split, version), rows)
    vname = data.version_dir(case.folder, version)
    leak = {"ngrams": set(), "answers": set()}
    for split in parts:
        for r in parts[split]:
            leak["ngrams"] |= ngram_hashes(r["input"])
            for a in case.answer_strings(r["expected"]):
                if len(a.strip()) >= 5:
                    leak["answers"].add(phrase_hash(a))
    import gzip
    lp = config.DATA / "leak" / f"{vname}.json.gz"
    lp.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(lp, "wt", encoding="utf-8") as f:
        json.dump({"ngrams": sorted(leak["ngrams"]), "answers": sorted(leak["answers"])}, f)
    stats = {"case": case.folder, "dataset_version": version, "source": "imported", "file": Path(file).name,
             "shift_file": Path(shift_file).name if shift_file else None, "rows_read": len(main_rows) + len(shift_rows),
             "exact_duplicates": ex1 + ex2, "near_duplicates": nd1 + nd2,
             "unused_examples": len(main) - sum(len(parts[s]) for s in ("train", "dev", "test")),
             "items_per_split": {s: len(parts[s]) for s in parts},
             "items_per_slice_and_split": {s: _count(parts[s], "slice") for s in parts},
             "avg_input_tokens_est": {s: (sum(len(r["input"]) for r in parts[s]) / max(1, len(parts[s])) / 4) for s in parts}}
    sd = config.DATA / "stats"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / f"{vname}.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    man = {"case": case.folder, "dataset_version": version, "source": "imported", "split_seed": seed,
           "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": stats["file"], "shift_file": stats["shift_file"],
           "git_commit": config.git_commit(), "sizes": stats["items_per_split"], "sha256": hashes,
           "frozen_files_sha256": {f: data.text_sha256(case.dir / f) for f in ("spec.md", "case.py") if (case.dir / f).exists()}}
    mp = data.manifest_path(case.folder, version)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    data.rebuild_manifest()
    return stats

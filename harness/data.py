"""Dataset paths, loading and the sealed-data gate.

Sealed splits (test, shift) can only be read when BENCH_FINAL=1, which only `make final` and
`make reproduce` set. Every sealed read or write is appended to runs/sealed_access.log.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

from . import config

OPEN_SPLITS = ("train", "dev")
SEALED_SPLITS = ("test", "shift")
ACCESS_LOG = config.RUNS / "sealed_access.log"


class SealedAccessError(PermissionError):
    pass


def version_dir(case_folder: str, version: int) -> str:
    return case_folder if version == 1 else f"{case_folder}-v{version}"


def split_path(case_folder: str, split: str, version: int = 1) -> Path:
    base = config.DATA / ("open" if split in OPEN_SPLITS else "sealed")
    return base / version_dir(case_folder, version) / f"{split}.jsonl"


def log_sealed_access(case_folder: str, split: str, version: int, action: str) -> None:
    ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    cmd = " ".join(os.path.basename(a) for a in sys.argv[:4])
    with ACCESS_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{action}\t{version_dir(case_folder, version)}/{split}"
                f"\tpid={os.getpid()}\tcmd={cmd}\tBENCH_FINAL={os.environ.get('BENCH_FINAL', '0')}\n")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_split(case_folder: str, split: str, version: int = 1) -> list[dict]:
    path = split_path(case_folder, split, version)
    if split in SEALED_SPLITS:
        if os.environ.get("BENCH_FINAL") != "1":
            log_sealed_access(case_folder, split, version, "DENIED")
            raise SealedAccessError(f"{split} is sealed; only `make final` may read it")
        log_sealed_access(case_folder, split, version, "read")
    return read_jsonl(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_path(case_folder: str, version: int) -> Path:
    return config.DATA / "manifests" / f"{version_dir(case_folder, version)}.json"


def rebuild_manifest() -> dict:
    """MANIFEST.json is rebuilt from per-case manifests so parallel case builds never clash."""
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "datasets": {}}
    for p in sorted((config.DATA / "manifests").glob("*.json")):
        out["datasets"][p.stem] = json.loads(p.read_text(encoding="utf-8"))
    (config.DATA / "MANIFEST.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def verify_hashes(case_folder: str, version: int = 1) -> list[str]:
    """Check sealed files still match the manifest hashes without reading their content into memory."""
    m = json.loads(manifest_path(case_folder, version).read_text(encoding="utf-8"))
    bad = []
    for split, h in m["sha256"].items():
        p = split_path(case_folder, split, version)
        if not p.exists() or sha256_file(p) != h:
            bad.append(split)
    return bad

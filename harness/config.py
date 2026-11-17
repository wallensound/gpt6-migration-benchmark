"""Paths and config loading shared by the whole harness."""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
CASES = ROOT / "cases"
DATA = ROOT / "data"
RUNS = ROOT / "runs"
STATE_DB = RUNS / "state.sqlite"
REFERENCE_DATE = "2026-11-17"


def load_dotenv() -> None:
    """Load KEY=VALUE lines from the git-ignored .env without overriding the environment."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


@lru_cache(maxsize=1)
def models() -> dict:
    return yaml.safe_load((CONFIG / "models.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def sizes() -> dict:
    return yaml.safe_load((CONFIG / "sizes.yaml").read_text(encoding="utf-8"))


def budget() -> dict:
    return json.loads((ROOT / "budget.json").read_text(encoding="utf-8"))


def model_cfg(name: str) -> dict:
    m = models()["models"].get(name)
    if m is None:
        raise KeyError(f"unknown model {name!r}; see config/models.yaml")
    return m


def role(name: str) -> dict:
    return models()["roles"][name]


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or "uncommitted"
    except Exception:
        return "unknown"


def sdk_version() -> str:
    import openai
    return openai.__version__

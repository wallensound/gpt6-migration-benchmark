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


def _env_key(name: str) -> str:
    return name.upper().replace("-", "_").replace(".", "_")


def model_provider(name: str) -> str:
    """BENCH_PROVIDER_<MODEL>, else BENCH_PROVIDER, else openai."""
    load_dotenv()
    sel = models().get("provider_selection") or {}
    default = os.environ.get(sel.get("default_env", "BENCH_PROVIDER")) or sel.get("default", "openai")
    return os.environ.get(f"BENCH_PROVIDER_{_env_key(name)}") or default


def model_cfg(name: str) -> dict:
    """The model's config with `provider` and `model_id` resolved from the environment."""
    m = models()["models"].get(name)
    if m is None:
        raise KeyError(f"unknown model {name!r}; see config/models.yaml")
    provider = model_provider(name)
    if provider not in models()["providers"]:
        raise KeyError(f"unknown provider {provider!r} for {name}; choose one of {list(models()['providers'])}")
    ids = m.get("ids") or {}
    model_id = os.environ.get(f"BENCH_MODEL_ID_{_env_key(name)}") or ids.get(provider) or ids.get("openai") or name
    return {**m, "provider": provider, "model_id": model_id}


def provider_cfg(provider: str) -> dict:
    """The provider's base URL (env override first) and key variable."""
    load_dotenv()
    p = dict(models()["providers"][provider])
    url = os.environ.get(p.get("base_url_env") or "") or p.get("base_url")
    if not url:
        raise RuntimeError(f"provider {provider!r} needs a base URL: set {p.get('base_url_env')} (see .env.example)")
    p["base_url"] = url.rstrip("/")
    return p


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

"""Load a case module and fill in default implementations of optional interface functions.

Required in every cases/<nn-name>/case.py:
    CASE_ID, NAME
    slices() -> list[str]
    plan(rng, slice, variant) -> dict            variant is "main" or "shift"
    generator_prompt(plan) -> str
    verify(plan, text) -> (ok, why)
    verifier_brief(plan) -> str                  what the answer is and what would change it
    label(plan) -> expected                      deterministic expected output (JSON-serialisable)
    parse(output, settings, item) -> parsed      output is runner.normalise(...) (a list when samples > 1)
    score(expected, parsed) -> dict              {passed, valid, nonanswer, secondary, categories, diff}
    legacy_markers() -> list[str]                regexes the legacy prompt must match

Optional (defaults below): shift_slices, make_input, user_message, tools, schema, schema_name,
aggregate, answer_strings, settings_space, port_settings, failure_taxonomy, item_extras.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import yaml

from . import config


def case_dir(case: str) -> Path:
    if Path(str(case)).is_dir():  # tests pass a folder path (the stub case)
        return Path(str(case))
    case = str(case).zfill(2)
    hits = sorted(config.CASES.glob(f"{case}-*"))
    hits = [h for h in hits if h.is_dir()]
    if not hits:
        raise FileNotFoundError(f"no case folder cases/{case}-*")
    return hits[0]


def all_case_ids() -> list[str]:
    return sorted(p.name[:2] for p in config.CASES.glob("[0-9][0-9]-*") if (p / "case.py").exists())


def flatten_strings(x) -> list[str]:
    out = []
    if isinstance(x, str):
        out.append(x)
    elif isinstance(x, dict):
        for v in x.values():
            out += flatten_strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            out += flatten_strings(v)
    elif isinstance(x, (int, float)) and not isinstance(x, bool):
        out.append(str(x))
    return out


class Case:
    """Thin wrapper giving every case the same interface."""

    def __init__(self, case: str):
        self.dir = case_dir(case)
        self.id = self.dir.name[:2]
        self.folder = self.dir.name
        spec = importlib.util.spec_from_file_location(f"case_{self.id}", self.dir / "case.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        self.mod: ModuleType = mod
        self.name = getattr(mod, "NAME", self.folder)

    def __getattr__(self, item):
        return getattr(self.mod, item)

    # ---- files
    @property
    def spec_text(self) -> str:
        return (self.dir / "spec.md").read_text(encoding="utf-8")

    @property
    def legacy_prompt(self) -> str:
        return (self.dir / "legacy_prompt.md").read_text(encoding="utf-8")

    @property
    def legacy_config(self) -> dict:
        return yaml.safe_load((self.dir / "legacy_config.yaml").read_text(encoding="utf-8"))

    def legacy_setup(self) -> dict:
        cfg = self.legacy_config
        return {"model": cfg["model"], "api": cfg.get("api", "chat"), "effort": cfg.get("effort", "none"),
                "prompt": self.legacy_prompt, "settings": dict(cfg.get("settings") or {})}

    # ---- optional functions with defaults
    def shift_slices(self):
        f = getattr(self.mod, "shift_slices", None)
        return f() if f else self.mod.slices()

    def make_input(self, plan, text):
        f = getattr(self.mod, "make_input", None)
        return f(plan, text) if f else text.strip()

    def item_extras(self, plan) -> dict:
        f = getattr(self.mod, "item_extras", None)
        return f(plan) if f else {}

    def user_message(self, item, settings):
        f = getattr(self.mod, "user_message", None)
        if f:
            return f(item, settings)
        if item.get("context"):
            return item["input"] + "\n\n" + item["context"]
        return item["input"]

    def tools(self, item, settings):
        f = getattr(self.mod, "tools", None)
        return f(item, settings) if f else None

    def schema(self, settings):
        f = getattr(self.mod, "schema", None)
        return f(settings) if f else None

    def schema_name(self):
        return getattr(self.mod, "SCHEMA_NAME", "output")

    def aggregate(self, rows) -> dict:
        f = getattr(self.mod, "aggregate", None)
        return f(rows) if f else {}

    def answer_strings(self, expected) -> list[str]:
        f = getattr(self.mod, "answer_strings", None)
        return f(expected) if f else [s for s in flatten_strings(expected) if len(s) >= 5]

    def settings_space(self) -> dict:
        f = getattr(self.mod, "settings_space", None)
        if f:
            return f()
        space = {"verbosity": [None, "low", "medium", "high"]}
        if getattr(self.mod, "schema", None):
            space["structured_outputs"] = [False, True]
        return space

    def port_settings(self, settings: dict) -> dict:
        f = getattr(self.mod, "port_settings", None)
        return f(dict(settings)) if f else dict(settings)

    def failure_taxonomy(self) -> list[str]:
        f = getattr(self.mod, "failure_taxonomy", None)
        return f() if f else ["format", "wrong_value", "missing", "extra", "nonanswer", "other"]

    def check_markers(self, prompt: str | None = None) -> list[str]:
        """Return the legacy markers missing from the prompt (empty list means all present)."""
        prompt = self.legacy_prompt if prompt is None else prompt
        return [m for m in self.mod.legacy_markers() if not re.search(m, prompt, flags=re.MULTILINE)]


def prompt_hash(setup: dict) -> str:
    import hashlib
    blob = json.dumps({"prompt": setup["prompt"], "settings": setup.get("settings", {})}, sort_keys=True,
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

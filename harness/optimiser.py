"""Candidate generation (gpt-6.2-sol at effort high) and the leakage checks."""
from __future__ import annotations

import gzip
import json
from functools import lru_cache

from . import config, data
from .cases import Case
from .generate import all_phrase_hashes, ngram_hashes
from .runner import Runner, normalise

EDIT_KINDS = {
    "targeted_fix": "Targeted fix: one rule change aimed at the top failure pattern. Change as little as possible.",
    "example_swap": "Example swap: add or replace exactly one worked example, using invented values that appear nowhere in the data.",
    "simplify": "Simplify: merge or delete rules and shorten the prompt, keeping every requirement of the spec.",
    "restructure": "Restructure: reorder sections, or move the core requirement and the output contract to the top.",
    "rewrite": "Rewrite: a fresh prompt written from the spec alone, in the style that suits this model.",
    "settings_change": "Settings change: change one or more of the allowed settings (and the prompt only if the setting requires it).",
}

OPTIMISER_PROMPT = """You are improving a production prompt after a model migration. The prompt must work on {model} \
(Responses API, reasoning effort `{effort}`). The model and the effort are fixed; you cannot change them.

## Task spec (the single source of truth; you may rephrase it but never change it)
{spec}

## Current prompt (developer message)
<<<PROMPT
{prompt}
PROMPT>>>

## Current settings
{settings}

Settings you may change, with their allowed values: {space}

## Failure report on the training items (the current prompt on {model})
{report}

## Rejected earlier candidates (do not repeat these)
{rejections}

## Your job
Return exactly {n} candidate prompts, one for each of these edit kinds, in this order:
{kinds}

Rules:
- Keep the output contract of the spec exactly (format, labels, field names, special values).
- Never include any string taken from the data: no names, numbers, dates or sentences from the examples above. Any example you write must use freshly invented values.
- The user message will contain only the task input, exactly as before.
- Each candidate is a complete prompt (not a diff), plus the full settings object, plus a one-line rationale.
Run tag (ignore): seed {seed}, round {round}."""


def settings_schema(space: dict) -> dict:
    props = {}
    for k, vals in space.items():
        types = sorted({{bool: "boolean", int: "integer", float: "number", str: "string", type(None): "null"}[type(v)]
                        for v in vals})
        props[k] = {"type": types if len(types) > 1 else types[0], "enum": list(vals)}
    return {"type": "object", "properties": props, "required": list(space), "additionalProperties": False}


def candidates_schema(case: Case, kinds: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["candidates"],
            "properties": {"candidates": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["edit_kind", "rationale", "prompt", "settings"],
                "properties": {"edit_kind": {"type": "string", "enum": kinds},
                               "rationale": {"type": "string"}, "prompt": {"type": "string"},
                               "settings": settings_schema(case.settings_space())}}}}}


async def propose(runner: Runner, case: Case, current: dict, report: str, rejections: list[dict], kinds: list[str],
                  seed: int, rnd: int) -> list[dict]:
    o = config.role("optimiser")
    space = case.settings_space()
    cur_settings = {k: (current.get("settings") or {}).get(k) for k in space}
    rej = "\n".join(f"- round {r['round']} {r['edit_kind']}: {r['reason']} (rationale was: {r.get('rationale', '')[:160]})"
                    for r in rejections[-12:]) or "(none yet)"
    text = OPTIMISER_PROMPT.format(model=current["model"], effort=current["effort"], spec=case.spec_text,
                                   prompt=current["prompt"], settings=json.dumps(cur_settings),
                                   space=json.dumps(space), report=report, rejections=rej, n=len(kinds),
                                   kinds="\n".join(f"{i + 1}. {k}: {EDIT_KINDS[k]}" for i, k in enumerate(kinds)),
                                   seed=seed, round=rnd)
    body = {"input": [{"role": "user", "content": text}], "reasoning": {"effort": o["effort"]},
            "text": {"format": {"type": "json_schema", "name": "candidates", "schema": candidates_schema(case, kinds),
                                "strict": True}}}
    for attempt in range(2):
        r = await runner.call(o["model"], "responses", body, repeat=attempt, purpose="optimiser")
        if r["raw"] is None:
            continue
        try:
            cands = json.loads(normalise("responses", r["raw"])["text"])["candidates"]
        except Exception:
            continue
        out, seen = [], set()
        for c in cands:
            if c["edit_kind"] in seen or c["edit_kind"] not in kinds or not c["prompt"].strip():
                continue
            seen.add(c["edit_kind"])
            settings = {**(current.get("settings") or {}), **{k: c["settings"].get(k) for k in space}}
            norm = getattr(case.mod, "normalise_settings", None)
            if norm:
                settings = norm(settings)
            out.append({"edit_kind": c["edit_kind"], "rationale": c["rationale"].strip(),
                        "setup": {**current, "prompt": c["prompt"].strip(), "settings": settings},
                        "optimiser_cost": r["cost_usd"]})
        if out:
            return out
    return []


# --------------------------------------------------------------------------- leakage

@lru_cache(maxsize=None)
def leak_index(case_folder: str, version: int) -> tuple[frozenset, frozenset]:
    p = config.DATA / "leak" / f"{data.version_dir(case_folder, version)}.json.gz"
    with gzip.open(p, "rt", encoding="utf-8") as f:
        d = json.load(f)
    return frozenset(d["ngrams"]), frozenset(d["answers"])


def base_text(case: Case) -> str:
    parts = [case.spec_text, case.legacy_prompt]
    tools = getattr(case.mod, "TOOLS", None)
    if tools:
        parts.append(json.dumps(tools, ensure_ascii=False))
    return "\n".join(parts)


@lru_cache(maxsize=None)
def _base_hashes(case_folder: str, text: str) -> tuple[frozenset, frozenset]:
    return frozenset(ngram_hashes(text)), frozenset(all_phrase_hashes(text))


def check_leak(case: Case, text: str, version: int = 1) -> dict:
    """Six-word sequences from any split input, or expected-answer strings, not already in spec/legacy/tools."""
    grams, answers = leak_index(case.folder, version)
    bg, ba = _base_hashes(case.folder, base_text(case))
    hit_grams = (ngram_hashes(text) - bg) & grams
    hit_ans = (all_phrase_hashes(text) - ba) & answers
    return {"ok": not hit_grams and not hit_ans, "ngram_hits": len(hit_grams), "answer_hits": len(hit_ans)}

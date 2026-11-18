"""Template for a case built from your own examples (no synthetic generation).

Copy this folder to cases/<nn>-<name>/ (e.g. cases/09-my-task/), then:
  1. edit spec.md, legacy_prompt.md (your current production prompt) and legacy_config.yaml;
  2. adjust parse() / score() below if exact matching is not what "correct" means for your task;
  3. run:  python -m harness.cli import 09 --file my_examples.csv
     then calibrate, freeze, sweep, loop, final and report as for any other case (see cases/README.md).

The default scorer works for two common shapes:
  - a text answer (label, short answer): exact match after trimming whitespace;
  - a JSON answer (object or list): the output must be valid JSON equal to the expected value.
"""
import json
import re

CASE_ID = "99"
NAME = "my task (imported examples)"
SCHEMA_NAME = "output"


def slices():
    # Only used by the synthetic generator; imported examples carry their own "slice" column.
    return ["all"]


def legacy_markers():
    # Regexes your legacy prompt must contain. Imported prompts are real, so nothing is required by default.
    return []


def parse(output, settings, item):
    """Turn the model's raw output into something score() can compare. Must never raise."""
    text = (output.get("text") or "").strip()
    if output.get("tool_calls"):
        return {"tool_calls": output["tool_calls"], "text": text}
    return {"text": text}


def _as_json(text):
    try:
        return json.loads(text), True
    except (TypeError, ValueError):
        return None, False


def score(expected, parsed):
    """Return pass/fail plus diagnostics. Edit the normalisation rules to match your spec."""
    text = (parsed or {}).get("text", "") if isinstance(parsed, dict) else ""
    nonanswer = (not text) or text.rstrip().endswith("?")
    if isinstance(expected, (dict, list)):
        got, ok = _as_json(text)
        fenced = bool(re.match(r"^```", text))
        valid = ok and not fenced
        passed = valid and got == expected
        cats = [] if passed else (["format"] if not valid else ["wrong_value"])
        diff = "" if passed else f"expected {json.dumps(expected, ensure_ascii=False)[:300]}, got {text[:300]!r}"
        return {"passed": passed, "valid": valid, "nonanswer": nonanswer and not ok, "secondary": {},
                "categories": cats if not nonanswer else ["nonanswer"], "diff": diff}
    exp = str(expected).strip()
    passed = text == exp
    return {"passed": passed, "valid": bool(text) and "\n" not in text, "nonanswer": nonanswer,
            "secondary": {}, "categories": [] if passed else (["nonanswer"] if nonanswer else ["wrong_value"]),
            "diff": "" if passed else f"expected {exp!r}, got {text[:300]!r}"}


def failure_taxonomy():
    return ["format", "wrong_value", "nonanswer", "other"]

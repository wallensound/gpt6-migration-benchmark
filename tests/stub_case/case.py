"""Stub case used by the harness tests and the five-item dry run: name the colour mentioned in a sentence."""
import re

CASE_ID = "00"
NAME = "stub colour naming"
COLOURS = ["red", "green", "blue", "yellow", "purple"]


def slices():
    return ["plain", "distractor"]


def plan(rng, slice, variant="main"):
    return {"colour": rng.choice(COLOURS), "noun": rng.choice(["car", "kite", "door", "scarf"])}


def generator_prompt(plan):
    return (f"Write one short sentence (under 20 words) about a {plan['colour']} {plan['noun']}. "
            f"It must contain the exact words '{plan['colour']} {plan['noun']}' and no other colour words. "
            "Output only the sentence.")


def verify(plan, text):
    if f"{plan['colour']} {plan['noun']}" not in text.lower():
        return False, "planned phrase missing"
    others = [c for c in COLOURS if c != plan["colour"] and re.search(rf"\b{c}\b", text.lower())]
    return (not others), ("extra colour " + ",".join(others) if others else "")


def verifier_brief(plan):
    return f"The only colour mentioned is '{plan['colour']}'. Another colour word would change the answer."


def label(plan):
    return plan["colour"]


def parse(output, settings, item):
    return (output.get("text") or "").strip()


def score(expected, parsed):
    p = (parsed or "").strip().lower().rstrip(".")
    valid = p in COLOURS
    return {"passed": p == expected, "valid": valid, "nonanswer": not p or p.endswith("?"),
            "secondary": {}, "categories": [] if p == expected else (["format"] if not valid else ["wrong_value"]),
            "diff": "" if p == expected else f"expected {expected!r}, got {parsed!r}"}


def legacy_markers():
    return [r"ONLY"]

import json
import random
from pathlib import Path

import pytest

from harness.cases import Case

CASE = Case(str(Path(__file__).resolve().parents[1]))
M = CASE.mod


def co(name, *mentions, cid="X"):
    return {"id": cid, "name": name, "sector": "software", "country": "Sweden", "domain": name.lower() + ".se",
            "mentions": [{"form": f, "text": t} for f, t in mentions]}


def out(text, refusal=None):
    return {"text": text, "tool_calls": [], "logprobs": None, "status": "stop", "refusal": refusal}


def run(expected, text, structured=False):
    p = M.parse(out(text), {"structured_outputs": structured}, {})
    return M.score(expected, p)


# ---------------------------------------------------------------- labeller fixtures (one or more per slice)

LABEL_FIXTURES = [
    ("legal_suffix", [co("Bohera", ("legal", "Bohera AB")), co("Maglik Freight", ("legal", "Maglik Freight Ltd"))],
     ["Bohera", "Maglik Freight"]),
    ("legal_suffix", [co("Pezum", ("legal", "Pezum B.V."), ("plain", "Pezum"))], ["Pezum"]),
    ("parent_present", [co("Holum", ("plain", "Holum"), ("product", "Holum Pay")), co("Zevia", ("plain", "Zevia"))],
     ["Holum", "Zevia"]),
    ("parent_absent", [co("Romix", ("product", "Romix Mail"))], ["Romix"]),
    ("sibling_products", [co("Jonix", ("product", "Jonix Mail"), ("product", "Jonix Cloud"))], ["Jonix"]),
    ("domain_forms", [co("Kubon", ("domain", "press@kubon.se")), co("Famyn", ("legal", "Famyn AB"),
                                                                    ("domain", "famyn.se"))], ["Kubon", "Famyn"]),
    ("domain_forms", [co("Tovyn", ("domain", "www.tovyn.de"))], ["Tovyn"]),
    ("diacritics", [co("Vömdivex", ("plain", "Vömdivex"), ("domain", "vomdivex.se"))], ["Vömdivex"]),
    ("diacritics", [co("Glösflard", ("legal", "Glösflard AB"))], ["Glösflard"]),
    ("distractors", [co("Canis", ("possessive", "Canis's"))], ["Canis"]),
    ("no_companies", [], []),
    ("dense", [co(f"Name{i}x", ("plain", f"Name{i}x"), cid=str(i)) for i in range(11)],
     [f"Name{i}x" for i in range(11)]),
    ("swedish", [co("Gacar", ("legal", "Gacar AB")), co("Hugis", ("product", "Hugis Pay"))], ["Gacar", "Hugis"]),
    ("german", [co("Ginon", ("legal", "Ginon GmbH")), co("Gilia", ("domain", "gilia.de"))], ["Ginon", "Gilia"]),
    ("dedupe", [co("Vomar", ("plain", "Vomar")), co("Vomar", ("legal", "Vomar AG"))], ["Vomar"]),
]


@pytest.mark.parametrize("sl,comps,expected", LABEL_FIXTURES)
def test_label(sl, comps, expected):
    assert M.label({"companies": comps}) == expected


# ---------------------------------------------------------------- scorer fixtures

SCORE_FIXTURES = [
    # (expected, output text, structured, passed, valid, category expected in categories or None)
    (["Bohera", "Maglik Freight"], '["Bohera", "Maglik Freight"]', False, True, True, None),
    (["Bohera", "Maglik Freight"], '["Maglik Freight", "Bohera"]', False, True, True, None),  # order not scored
    (["Bohera"], '["Bohera AB"]', False, False, True, "legal_suffix_kept"),
    (["Holum"], '["Holum", "Holum Pay"]', False, False, True, "product_not_mapped"),
    (["Romix"], '["Romix Mail"]', False, False, True, "product_not_mapped"),
    (["Jonix"], '["Jonix", "Jonix"]', False, False, True, "duplicate"),
    (["Kubon"], '["kubon.se"]', False, False, True, "domain_not_mapped"),
    (["Vömdivex"], '["Vomdivex"]', False, False, True, "diacritics_lost"),
    (["Vömdivex"], '["Vömdivex"]', False, True, True, None),  # NFD input is NFC-normalised
    (["Canis"], '["Canis\'s"]', False, False, True, "possessive_kept"),
    (["Canis"], '["Canis", "Ebba Brumtreoez"]', False, False, True, "extra_company"),
    ([], "[]", False, True, True, None),
    ([], '["Stockholm"]', False, False, True, "extra_company"),
    (["Gacar", "Hugis"], '```json\n["Gacar", "Hugis"]\n```', False, False, False, "format_fence"),
    (["Ginon"], 'Here are the companies: ["Ginon"]', False, False, False, "prose_around"),
    (["Ginon"], '{"companies": ["Ginon"]}', False, False, False, "wrong_shape"),
    (["Ginon"], '{"companies": ["Ginon"]}', True, True, True, None),
    (["Ginon"], '["Ginon"]', True, True, True, None),
    (["Ginon"], "Could you clarify which entities you need?", False, False, False, "nonanswer"),
    (["Ginon"], "", False, False, False, "nonanswer"),
    (["Ginon", "Gilia"], '["Ginon"]', False, False, True, "missing_company"),
    (["Bohera"], '["bohera"]', False, False, True, "case_changed"),
    (["Ginon"], '[1, 2]', False, False, False, "wrong_shape"),
]


@pytest.mark.parametrize("expected,text,structured,passed,valid,cat", SCORE_FIXTURES)
def test_score(expected, text, structured, passed, valid, cat):
    s = run(expected, text, structured)
    assert s["passed"] is passed
    assert s["valid"] is valid
    if cat:
        assert cat in s["categories"], s["categories"]
        assert cat in M.failure_taxonomy()
    if passed:
        assert s["categories"] == [] and s["diff"] == ""


def test_nonanswer_flags():
    assert run(["A"], "")["nonanswer"]
    assert M.score(["A"], M.parse(out("", refusal="no"), {}, {}))["nonanswer"]
    assert not run(["A"], '["A"]')["nonanswer"]


def test_secondary_counts_and_aggregate():
    rows = []
    for exp, txt in [(["A", "B"], '["A", "C"]'), (["A"], "```\n[\"A\"]\n```"), ([], "[]")]:
        s = run(exp, txt)
        rows.append({**s, "slice": "x"})
    assert rows[0]["secondary"] == {"tp": 1, "fp": 1, "fn": 1, "valid": 1, "duplicates": 0}
    assert rows[1]["secondary"]["fn"] == 1 and rows[1]["secondary"]["tp"] == 0
    agg = M.aggregate(rows + [{"passed": False, "valid": False, "secondary": {}}])
    assert agg["micro_precision"] == pytest.approx(0.5)
    assert agg["micro_recall"] == pytest.approx(1 / 3)
    assert agg["micro_f1"] == pytest.approx(0.4)
    assert agg["format_validity"] == pytest.approx(2 / 4)


def test_parse_never_raises():
    for o in [None, {}, [], [out('["A"]')], {"text": None}, out("{"), out("null"), out('"x"')]:
        p = M.parse(o, {}, {})
        M.score(["A"], p)
    M.score(["A"], None)


# ---------------------------------------------------------------- plan / verify / generator

@pytest.mark.parametrize("sl", M.slices())
@pytest.mark.parametrize("variant", ["main", "shift"])
def test_plan_every_slice(sl, variant):
    for seed in range(15):
        p = M.plan(random.Random(seed), sl, variant)
        json.dumps(p)
        assert p == M.plan(random.Random(seed), sl, variant)  # deterministic
        exp = M.label(p)
        n = len(p["companies"])
        assert len(exp) == n
        pool = {c["name"] for c in M.entities.companies(pool="shift" if variant == "shift" else "main")}
        assert all(c["name"] in pool for c in p["companies"])
        forms = [m["form"] for c in p["companies"] for m in c["mentions"]]
        if sl == "no_companies":
            assert n == 0
        if sl == "dense":
            assert n >= 10
        assert n <= 12
        if sl == "legal_suffix":
            assert forms.count("legal") >= 2 or (n == 1 and "legal" in forms)
        if sl == "parent_present":
            assert any({m["form"] for m in c["mentions"]} >= {"product"} and len(c["mentions"]) > 1
                       for c in p["companies"])
        if sl == "parent_absent":
            assert any({m["form"] for m in c["mentions"]} == {"product"} for c in p["companies"])
        if sl == "sibling_products":
            assert any([m["form"] for m in c["mentions"]].count("product") == 2 for c in p["companies"])
        if sl == "domain_forms":
            assert any({m["form"] for m in c["mentions"]} == {"domain"} for c in p["companies"])
        if sl == "diacritics":
            assert any(M.fold(c["name"]) != c["name"].lower() for c in p["companies"])
        assert p["lang"] == {"swedish": "sv", "german": "de"}.get(sl, "en")
        if variant == "shift":
            assert p["words"][0] >= 300
        # canonical == entity name by construction (domain-only names are one-word ASCII)
        assert exp == [c["name"] for c in p["companies"]]
        assert "Output plain text only" in M.generator_prompt(p)
        assert M.verifier_brief(p)


def test_slice_weights_languages():
    w = M.slice_weights("main")
    tot = sum(w.values())
    assert w["swedish"] / tot == pytest.approx(0.2)
    assert w["german"] / tot == pytest.approx(0.1)


def _render(p):
    parts = []
    for c in p["companies"]:
        for m in c["mentions"]:
            parts.append(f"Officials pointed to {m['text']} in the report.")
    parts += [f"{x['name']}, {x['title']}, spoke." for x in p["people"]]
    parts += [f"In {c} the market grew." for c in p["cities"]]
    body = " ".join(parts)
    filler = " The market for these goods is changing quickly and nobody knows what comes next."
    while len(body.split()) < p["words"][0] + 5:
        body += filler
    return body


def test_verify_accepts_and_rejects():
    p = M.plan(random.Random(3), "domain_forms", "main")
    text = _render(p)
    assert M.verify(p, text) == (True, "")
    c = p["companies"][0]
    assert not M.verify(p, text.replace(c["mentions"][0]["text"], "something"))[0]
    assert not M.verify(p, text + " Shares of Orbvex Ltd rose.")[0]  # unplanned legal suffix
    assert not M.verify(p, text + " See also zzzexample.com today.")[0]  # unplanned domain
    other = next(x for x in M.entities.companies("main") if x["name"] not in [y["name"] for y in p["companies"]]
                 and " " not in x["name"])
    assert not M.verify(p, text + f" {other['name']} declined to comment.")[0]  # unplanned list company
    assert not M.verify(p, " ".join(text.split()[:40]))[0]  # too short


def test_verify_spelling_variants():
    p = M.plan(random.Random(1), "diacritics", "main")
    text = _render(p)
    assert M.verify(p, text)[0]
    d = next(c for c in p["companies"] if M.fold(c["name"]) != c["name"].lower())
    assert not M.verify(p, text + f" Later {M.entities.ascii_fold(d['name'])} said more.")[0]


# ---------------------------------------------------------------- legacy setup

def test_legacy_markers_present():
    assert CASE.check_markers() == []
    txt = CASE.legacy_prompt
    assert txt.count("NEVER") >= 10 and txt.count("ALWAYS") >= 5
    assert 3500 < len(txt) < 7000  # roughly 1,200 tokens of rules
    cfg = CASE.legacy_config
    assert cfg["api"] == "chat" and cfg["effort"] == "none" and cfg["settings"]["temperature"] == 0
    assert not cfg["settings"]["structured_outputs"]


def test_schema_strict_shape():
    s = M.schema({})
    assert s["type"] == "object" and s["required"] == ["companies"] and s["additionalProperties"] is False


def test_prompt_examples_not_in_entity_lists():
    keys = {M.fold(c["name"]) for c in M.entities.companies(None)}
    for n in ["Velmora", "Orsenta Energy", "Tralvik", "Draxen", "Pellor", "Dåskor", "Quillon Labs"]:
        assert M.fold(n) not in keys

"""Labeller and scorer fixtures for case 06 (no API calls)."""
import json
import random
from pathlib import Path

import pytest

from harness.cases import Case
from harness.generate import make_plans

CASE = Case(str(Path(__file__).resolve().parents[1]))
M = CASE.mod


def out(text, refusal=None):
    return M.parse({"text": text, "tool_calls": [], "logprobs": None, "status": "stop", "refusal": refusal}, {}, {})


def base_plan(**kw):
    p = {"lang": "en", "etype": "company", "name": "Kolvex", "desc": {"sector": "software"}, "attr": "founded_year",
         "numeric": True, "question": "In what year was Kolvex founded?", "answerable": True, "value": "1987",
         "fillers": [{"attr": "employees", "value": "430"}, {"attr": "hq_city", "value": "Malmö"}],
         "lookalikes": [], "unans_kind": None, "placement": "any", "words": 300, "length_bounds": [200, 600],
         "genre": "news article", "angle": "an award", "opening": "open with an anecdote", "slice": "plain",
         "variant": "main"}
    p.update(kw)
    return p


FILL = ("The firm has grown steadily over the years and the team is proud of the work done for customers "
        "across the region and beyond, with many new partners joining the network every single season. ") * 12

# (slice, plan overrides, model output, passed, category or None)
FIXTURES = [
    ("plain", {}, "1987", True, None),
    ("plain", {}, "Kolvex was founded in 1987.", True, None),
    ("plain", {}, "NOT_FOUND", False, "over_abstain"),
    ("plain", {}, "It was founded in 1988.", False, "wrong_value"),
    ("plain", {}, "**1987**", False, "format"),
    ("plain", {}, "According to the context provided, the company Kolvex was originally founded back in the year "
                  "1987 by two engineers.", False, "too_long"),
    ("lookalike_distractor", {"lookalikes": [{"name": "Kalvex", "value": "1991"}]}, "1987", True, None),
    ("lookalike_distractor", {"lookalikes": [{"name": "Kalvex", "value": "1991"}]}, "1991", False,
     "lookalike_confusion"),
    ("lookalike_distractor", {"lookalikes": [{"name": "Kalvex", "value": "1991"}]}, "1987 (Kalvex: 1991)", False,
     "lookalike_confusion"),
    ("numeric_answer", {"attr": "employees", "value": "430", "fillers": []}, "430 employees", True, None),
    ("numeric_answer", {"attr": "price", "value": "349", "etype": "product", "fillers": []}, "€349", True, None),
    ("numeric_answer", {"attr": "price", "value": "349", "etype": "product", "fillers": []}, "3490 euros", False,
     "wrong_value"),
    ("answer_last_sentence", {"attr": "hq_city", "numeric": False, "value": "Malmö", "placement": "last"},
     "Malmo", True, None),
    ("answer_last_sentence", {"attr": "birth_city", "numeric": False, "value": "Lund", "placement": "last"},
     "Lundberg", False, "wrong_value"),
    ("answer_two_sentences", {"attr": "ceo", "numeric": False, "value": "Anna Kolberg", "placement": "two"},
     "Anna Kolberg is the CEO.", True, None),
    ("answer_two_sentences", {"attr": "ceo", "numeric": False, "value": "Anna Kolberg", "placement": "two"},
     "Do you mean Kolvex AB or Kolvex Labs?", False, "clarifying_question"),
    ("unanswerable", {"answerable": False, "value": None, "unans_kind": "missing"}, "NOT_FOUND", True, None),
    ("unanswerable", {"answerable": False, "value": None, "unans_kind": "missing"}, "  NOT_FOUND.\n", True, None),
    ("unanswerable", {"answerable": False, "value": None, "unans_kind": "missing"}, "`NOT_FOUND`", False, "format"),
    ("unanswerable", {"answerable": False, "value": None, "unans_kind": "missing"}, "not_found", False, "format"),
    ("unanswerable", {"answerable": False, "value": None, "unans_kind": "missing"},
     "NOT_FOUND - the context does not say.", False, "format"),
    ("unanswerable", {"answerable": False, "value": None, "unans_kind": "missing"},
     "The context does not mention it.", False, "abstain_wrong_format"),
    ("unanswerable", {"answerable": False, "value": None, "unans_kind": "lookalike",
                      "lookalikes": [{"name": "Kalvex", "value": "1991"}]}, "1991", False, "answered_unanswerable"),
    ("unanswerable", {"answerable": False, "value": None, "unans_kind": "missing"}, "", False, "empty_or_refusal"),
]


@pytest.mark.parametrize("sl,over,text,passed,cat", FIXTURES)
def test_score_fixtures(sl, over, text, passed, cat):
    p = base_plan(slice=sl, **over)
    s = CASE.score(CASE.label(p), out(text))
    assert s["passed"] is passed, s
    if cat:
        assert cat in s["categories"], s
    else:
        assert s["categories"] == [] and s["diff"] == ""
    json.dumps(s)


def test_every_slice_has_fixtures():
    assert {f[0] for f in FIXTURES} == set(M.slices())


def test_validity_and_nonanswer():
    lab = CASE.label(base_plan())
    assert CASE.score(lab, out("NOT_FOUND"))["valid"] is True
    assert CASE.score(lab, out("Which company do you mean?"))["nonanswer"] is True
    assert CASE.score(lab, out("Which company do you mean?"))["valid"] is False
    assert CASE.score(lab, out("", refusal="I can't help"))["nonanswer"] is True
    assert CASE.score(lab, out("1987"))["nonanswer"] is False
    assert CASE.score(lab, None)["passed"] is False  # parse failures never raise


def test_parse_never_raises():
    for o in [None, {}, [], [{"text": "x"}], {"text": None}]:
        assert isinstance(CASE.parse(o, {}, {}), dict)


def test_label_from_plan():
    p = base_plan(lookalikes=[{"name": "Kalvex", "value": "1991"}])
    assert CASE.label(p) == {"answerable": True, "value": "1987", "numeric": True, "conflicting": ["1991"]}
    u = base_plan(answerable=False, value=None)
    assert CASE.label(u)["answerable"] is False and CASE.label(u)["value"] is None
    assert "NOT_FOUND" not in CASE.answer_strings(CASE.label(u))


def test_aggregate():
    lab_a, lab_u = CASE.label(base_plan()), CASE.label(base_plan(answerable=False, value=None))
    rows = []
    for lab, t in [(lab_a, "1987"), (lab_a, "NOT_FOUND"), (lab_u, "NOT_FOUND"), (lab_u, "1991"), (lab_a, "Which?")]:
        s = CASE.score(lab, out(t))
        rows.append({"passed": s["passed"], "secondary": s["secondary"], "slice": "x"})
    rows.append({"passed": False, "secondary": {}, "slice": "x"})  # api error row
    a = CASE.aggregate(rows)
    assert a["abstention_precision"] == 0.5 and a["abstention_recall"] == 0.5
    assert a["clarification_rate"] == pytest.approx(1 / 5)
    assert a["over_abstention_rate"] == pytest.approx(1 / 3)


def test_plans_deterministic_and_weighted():
    a = make_plans(CASE, "main", 200, 123)
    b = make_plans(CASE, "main", 200, 123)
    assert a == b
    un = sum(1 for _, p in a if p["slice"] == "unanswerable")
    assert 65 <= un <= 75
    langs = [p["lang"] for _, p in a]
    assert 0.1 < langs.count("sv") / 200 < 0.3 and 0.03 < langs.count("de") / 200 < 0.17
    for _, p in a:
        json.dumps(p)
        lab = CASE.label(p)
        assert lab["answerable"] == (p["slice"] != "unanswerable")
        if p["slice"] == "numeric_answer":
            assert p["numeric"]
        if p["slice"] == "lookalike_distractor":
            assert len(p["lookalikes"]) == 1 and p["lookalikes"][0]["value"] != p["value"]
        for lk in p["lookalikes"]:
            assert M._distinct(lk["name"], p["name"])
        nums = [v for v in [p["value"], *[f["value"] for f in p["fillers"]], *lab["conflicting"]] if v and v.isdigit()]
        assert len(nums) == len(set(nums))
        assert p["question"] and p["name"] in p["question"]
        assert not M.EXCLUSIVE <= {p["attr"], *[f["attr"] for f in p["fillers"]]}


def test_shift_plans_have_two_lookalikes_and_shift_pool():
    from harness import entities
    shift_names = {c["name"] for c in entities.companies("shift")}
    for _, p in make_plans(CASE, "shift", 60, 7):
        assert len(p["lookalikes"]) == 2
        assert p["length_bounds"] == [600, 1800]
        if p["etype"] == "company":
            assert p["name"] in shift_names


def test_every_entity_gets_two_lookalikes():
    from harness import entities
    rng = random.Random(1)
    for etype, ents in [("company", entities.companies(None)), ("person", entities.people()),
                        ("product", entities.products())]:
        for e in ents:
            assert len(M._lookalike_names(rng, etype, e["name"], 2, [])) == 2, e["name"]


def test_large_plan_batches_never_raise():
    make_plans(CASE, "main", 1100, 1000 * 100_000)
    make_plans(CASE, "shift", 250, 1000 * 100_000 + 50_000)


def test_verify_placement():
    p = base_plan(attr="hq_city", numeric=False, value="Malmö", placement="last", slice="answer_last_sentence",
                  fillers=[{"attr": "employees", "value": "430"}])
    good = f"Kolvex is a software firm with 430 employees. {FILL}Today Kolvex is headquartered in Malmö."
    assert CASE.verify(p, good) == (True, "")
    bad = f"Kolvex is in Malmö and has 430 employees. {FILL}The end of the story is near."
    assert CASE.verify(p, bad)[0] is False
    p2 = dict(p, placement="two", slice="answer_two_sentences")
    good2 = f"Kolvex has 430 employees. {FILL}Kolvex moved its main office last year. It is now in Malmö."
    assert CASE.verify(p2, good2) == (True, "")
    bad2 = f"Kolvex has 430 employees. {FILL}Kolvex moved its main office last year to Malmö. Good."
    assert CASE.verify(p2, bad2)[0] is False


def test_verify_counts_and_markdown():
    p = base_plan()
    text = f"Kolvex was founded in 1987 in Malmö and has 430 employees. {FILL}"
    assert CASE.verify(p, text) == (True, "")
    assert CASE.verify(p, text + " In 1987 it grew.")[0] is False  # number twice
    assert CASE.verify(p, "# Title\n" + text)[0] is False
    assert CASE.verify(p, text.replace("1987", "1990"))[0] is False


def test_user_message_and_extras():
    p = base_plan()
    ex = CASE.item_extras(p)
    msg = CASE.user_message({"input": "CTX", **ex}, {})
    assert msg.startswith("CONTEXT:\nCTX") and msg.endswith("QUESTION: In what year was Kolvex founded?")


def test_generator_prompt_contains_planned_strings():
    for seed, p in make_plans(CASE, "main", 30, 99) + make_plans(CASE, "shift", 10, 5):
        g = CASE.generator_prompt(p)
        assert p["name"] in g
        for v in [p["value"], *[f["value"] for f in p["fillers"]], *[lk["name"] for lk in p["lookalikes"]]]:
            if v:
                assert v in g
        if not p["answerable"]:
            assert "must NOT reveal" in g


def test_legacy_markers_present():
    assert CASE.check_markers() == []
    cfg = CASE.legacy_config
    assert cfg["api"] == "chat" and cfg["effort"] == "none" and cfg["settings"]["temperature"] == 0

"""Labeller, scorer and data-plan fixtures for case 03 (no API calls)."""
import random
import re
from pathlib import Path

import pytest
import yaml

from harness.cases import Case
from harness.generate import make_plans

DIR = Path(__file__).resolve().parent.parent
CASE = Case(str(DIR))
M = CASE.mod


def P(issues, cues, slice="clear", lang="en", length="normal", domain="home"):
    return {"issues": issues, "cues": cues, "slice": slice, "lang": lang, "length": length, "domain": domain,
            "difficulty": slice, "variant": "main" if domain == "home" else "shift"}


def out(text, refusal=None):
    return M.parse({"text": text, "tool_calls": [], "logprobs": None, "status": "stop", "refusal": refusal}, {}, {})


# ---------------------------------------------------------------- labeller fixtures, one or more per slice

LABEL_FIXTURES = [
    # clear
    (P(["shipping"], ["my order still hasn't arrived"]), "shipping"),
    (P(["feature_request"], ["could you add a vacation mode"]), "feature_request"),
    # tie_break: winner second and winner first, all three rules
    (P(["technical", "billing"], ["how do I set up a heating schedule", "a payment I don't recognise"],
       "tie_break"), "billing"),
    (P(["billing", "bug_report"], ["the invoice shows the wrong amount", "the thermostat display freezes"],
       "tie_break"), "billing"),
    (P(["billing", "cancellation"], ["charged twice for my Plus subscription", "stop the automatic renewal"],
       "tie_break"), "cancellation"),
    (P(["returns", "cancellation"], ["how do I get a return label", "cancel my Plus subscription"],
       "tie_break"), "cancellation"),
    (P(["account_access", "privacy"], ["locked out of my account", "delete all my personal data"],
       "tie_break"), "privacy"),
    (P(["privacy", "cancellation"], ["what personal data you store about me", "cancel my Plus subscription"],
       "tie_break"), "privacy"),
    # off_topic
    (P(["other"], ["who won the hockey game last night"], "off_topic"), "other"),
    # multi_issue: first issue wins
    (P(["shipping", "bug_report"], ["my order still hasn't arrived", "the hub reboots on its own every night"],
       "multi_issue"), "shipping"),
    (P(["feature_request", "account_access"], ["could you add a vacation mode", "can't log in to my account"],
       "multi_issue"), "feature_request"),
    # very_short
    (P(["account_access"], ["can't log in"], "very_short", length="very_short"), "account_access"),
    (P(["other"], ["best pizza in town"], "very_short", length="very_short"), "other"),
    # long
    (P(["bug_report", "billing"], ["error code E42 when I save settings", "a payment I don't recognise"], "long",
       length="long"), "billing"),
    # swedish
    (P(["cancellation", "returns"], ["säga upp mitt Plus-abonnemang", "hur får jag en returetikett"], "swedish",
       lang="sv"), "cancellation"),
    (P(["feedback"], ["installationen var enklare än jag trodde"], "swedish", lang="sv"), "feedback"),
    # german
    (P(["privacy"], ["alle meine personenbezogenen Daten löschen"], "german", lang="de"), "privacy"),
    (P(["shipping", "returns"], ["meine Bestellung ist immer noch nicht angekommen",
                                 "wie bekomme ich ein Rücksendeetikett"], "german", lang="de"), "shipping"),
    # shift domain
    (P(["partnership"], ["stock your bikes in our shop"], domain="bike"), "partnership"),
]


@pytest.mark.parametrize("plan,expected", LABEL_FIXTURES)
def test_label(plan, expected):
    assert M.label(plan) == expected


def test_fixtures_cover_every_slice():
    assert {p["slice"] for p, _ in LABEL_FIXTURES} >= set(M.slices())
    assert len(LABEL_FIXTURES) >= 15


# ---------------------------------------------------------------- scorer fixtures

SCORE_FIXTURES = [
    ("billing", "billing", dict(passed=True, valid=True, nonanswer=False, cats=[])),
    ("billing", "  billing\n", dict(passed=True, valid=True, nonanswer=False, cats=[])),
    ("billing", "Billing", dict(passed=False, valid=False, nonanswer=False, cats=["format"])),
    ("billing", "billing.", dict(passed=False, valid=False, nonanswer=False, cats=["format"])),
    ("account_access", "`account_access`", dict(passed=False, valid=False, nonanswer=False, cats=["format"])),
    ("account_access", "Label: account_access", dict(passed=False, valid=False, nonanswer=False, cats=["format"])),
    ("billing", "technical", dict(passed=False, valid=True, nonanswer=False, cats=["wrong_label"])),
    ("other", "feedback", dict(passed=False, valid=True, nonanswer=False, cats=["missed_other"])),
    ("shipping", "other", dict(passed=False, valid=True, nonanswer=False, cats=["false_other"])),
    ("billing", "", dict(passed=False, valid=False, nonanswer=True, cats=["nonanswer"])),
    ("billing", "Could you clarify whether", dict(passed=False, valid=False, nonanswer=True, cats=["nonanswer"])),
    ("billing", "billing or technical?", dict(passed=False, valid=False, nonanswer=True, cats=["nonanswer"])),
]


@pytest.mark.parametrize("expected,text,want", SCORE_FIXTURES)
def test_score(expected, text, want):
    s = M.score(expected, out(text))
    assert s["passed"] is want["passed"]
    assert s["valid"] is want["valid"]
    assert s["nonanswer"] is want["nonanswer"]
    assert s["categories"] == want["cats"]
    assert set(s["categories"]) <= set(M.failure_taxonomy())


def test_refusal_is_nonanswer():
    s = M.score("privacy", out("", refusal="I can't help with that"))
    assert s["nonanswer"] and not s["passed"]


def test_parse_never_raises():
    for o in [None, {}, [], [{"text": "billing"}], {"text": None}]:
        p = M.parse(o, {}, {})
        M.score("billing", p)
    assert M.score("billing", None)["passed"] is False


def test_aggregate_macro_f1():
    rows = []
    for e, p in [("billing", "billing"), ("billing", "technical"), ("technical", "technical"), ("other", "")]:
        s = M.score(e, out(p))
        rows.append({**s, "slice": "clear"})
    agg = M.aggregate(rows)
    # billing F1 = 2/3, technical F1 = 2/3, other F1 = 0 -> mean 4/9
    assert abs(agg["macro_f1"] - 4 / 9) < 1e-9
    assert agg["nonanswer_rate"] == 0.25
    rows.append({"passed": False, "valid": False, "nonanswer": False, "secondary": {}, "slice": "clear"})
    assert M.aggregate(rows)["rows_scored_for_f1"] == 4


# ---------------------------------------------------------------- verify

def test_verify_accepts_and_rejects():
    p = {**P(["technical", "billing"], ["how do I set up a heating schedule", "a payment I don't recognise"],
              "tie_break")}
    good = "Hi! How do I set up a heating schedule? Also there is a payment I don’t recognise on my statement."
    assert M.verify(p, good) == (True, "")
    assert not M.verify(p, "There is a payment I don't recognise. And how do I set up a heating schedule?")[0]
    assert not M.verify(p, "How do I set up a heating schedule?")[0]
    q = P(["shipping"], ["my order still hasn't arrived"])
    assert not M.verify(q, "My order still hasn't arrived even though I paid for express.")[0]
    assert not M.verify(q, "My order still hasn't arrived, so I might cancel.")[0]
    s = P(["account_access"], ["can't log in"], "very_short", length="very_short")
    assert M.verify(s, "Can't log in. Help!")[0]
    assert not M.verify(s, "Hi there, I can't log in to the app since this morning")[0]
    lg = P(["shipping"], ["my order still hasn't arrived"], "long", length="long")
    assert not M.verify(lg, "My order still hasn't arrived.")[0]
    assert M.verify(lg, "My order still hasn't arrived. " + "We waited all week long " * 30)[0]


def test_cues_do_not_trigger_other_labels():
    """No cue may contain a trigger word of a different rule label, nor another label's cue."""
    for domain, pools in M.CUES.items():
        all_cues = [(lb, c) for pool in pools.values() for lb, cs in pool.items() for c in cs]
        for lang_key, pool in pools.items():
            lang = "en" if lang_key == "short" else lang_key
            for lb, cs in pool.items():
                assert cs, (domain, lang_key, lb)
                for c in cs:
                    for blb, pats in M.BLACKLIST.items():
                        if blb == lb:
                            continue
                        for lg in {lang, "en"}:
                            assert not re.search(pats[lg], M._norm(c)), (domain, lb, c, blb)
                    for lb2, c2 in all_cues:
                        if lb2 != lb and len(c2) >= 12:
                            assert M._norm(c2) not in M._norm(c), (c, c2)
        assert set(pools["en"]) == set(M.LABELS)


def test_plans_deterministic_and_balanced():
    a = make_plans(CASE, "main", 400, 123)
    b = make_plans(CASE, "main", 400, 123)
    assert a == b
    sl = [p["slice"] for _, p in a]
    assert 0.17 < sl.count("swedish") / 400 < 0.23
    assert 0.07 < sl.count("german") / 400 < 0.13
    labels = {M.label(p) for _, p in a}
    assert labels == set(M.LABELS)
    for _, p in a:
        assert p["cues"] and len(p["cues"]) == len(p["issues"])
        prompt = M.generator_prompt(p)
        for c in p["cues"]:
            assert c in prompt
        if p["slice"] == "swedish":
            assert p["lang"] == "sv" and "Swedish" in prompt
    shift = make_plans(CASE, "shift", 100, 7)
    assert all(p["domain"] == "bike" for _, p in shift)
    brands_main = {p["brand"] for _, p in a}
    assert not brands_main & {p["brand"] for _, p in shift}


def test_multi_pairs_exclude_rules():
    for a, b in M.MULTI_PAIRS:
        assert frozenset((a, b)) not in M._RULE_WINNER
        assert "other" not in (a, b)


# ---------------------------------------------------------------- legacy

def test_legacy_markers_and_config():
    assert CASE.check_markers() == []
    cfg = yaml.safe_load((DIR / "legacy_config.yaml").read_text(encoding="utf-8"))
    assert cfg["model"] == "gpt-5.6-sol" and cfg["api"] == "chat" and cfg["effort"] == "none"
    assert cfg["settings"]["temperature"] == 0
    assert cfg["settings"]["max_output_tokens"] == 5
    prompt = CASE.legacy_prompt
    for lb in M.LABELS:
        assert re.search(rf"^- {lb}:", prompt, flags=re.MULTILINE), lb
    assert len(re.findall(r"^\d\. ", prompt, flags=re.MULTILINE)) == 3  # three tie-break rules


def test_port_settings_lifts_tiny_cap():
    assert M.port_settings({"max_output_tokens": 5})["max_output_tokens"] == 16
    assert M.port_settings({"max_output_tokens": None})["max_output_tokens"] is None

"""Labeller and scorer fixtures for case 05 (no API calls)."""
import random
import re
from pathlib import Path

import pytest

from harness.cases import Case

CASE = Case(str(Path(__file__).resolve().parents[1]))
M = CASE.mod

EXP = {"number": 1250, "number_text": "1,250", "entity": "Velmora Freight", "entity_kind": "company",
       "date": [2027, 3, 3], "date_text": "3 March 2027"}
EXP_PERSON = {"number": 340, "number_text": "340", "entity": "Anna Kröberg", "entity_kind": "person",
              "date": [2027, 9, 14], "date_text": "14 september 2027"}


def sc(text, exp=EXP, refusal=None):
    return M.score(exp, M.parse({"text": text, "tool_calls": [], "logprobs": None, "status": "stop",
                                 "refusal": refusal}, {}, {}))


GOOD = ("- Brannex will build a battery plant in Gävle, creating 1,250 new jobs.\n"
        "- The plant is built together with partner Velmora Freight.\n"
        "- Production starts on 3 March 2027.")


# ---------------------------------------------------------------- scorer fixtures

def test_plain_pass():
    r = sc(GOOD)
    assert r["passed"] and r["valid"] and r["secondary"]["facts_covered"] == 3 and r["categories"] == []


def test_trailing_newline_and_spaces_ok():
    assert sc("\n" + GOOD.replace("jobs.", "jobs.  ") + "\n")["passed"]


def test_number_formats_normalised():
    for form in ("1250", "1 250", "1 250", "1 250"):
        assert sc(GOOD.replace("1,250", form))["passed"], form


def test_number_rewritten_fails():
    r = sc(GOOD.replace("1,250 new jobs", "1.25 thousand new jobs"))
    assert not r["passed"] and "missing_number" in r["categories"] and r["valid"]


def test_number_inside_larger_number_not_matched():
    assert not sc(GOOD.replace("1,250", "11,250"))["passed"]


def test_date_formats_normalised():
    for form in ("March 3, 2027", "3rd of March 2027", "March 3rd", "3 Mar 2027", "2027-03-03", "3 mars 2027",
                 "3 March"):
        assert sc(GOOD.replace("3 March 2027", form))["passed"], form


def test_date_wrong_year_or_no_day_fails():
    assert "missing_date" in sc(GOOD.replace("3 March 2027", "3 March 2028"))["categories"]
    assert "missing_date" in sc(GOOD.replace("3 March 2027", "March 2027"))["categories"]
    assert "missing_date" in sc(GOOD.replace("3 March 2027", "03/03/2027"))["categories"]


def test_entity_casefold_and_possessive():
    assert sc(GOOD.replace("partner Velmora Freight.", "VELMORA FREIGHT's team."))["passed"]


def test_entity_partial_name_fails():
    r = sc(GOOD.replace("Velmora Freight", "Velmora"))
    assert not r["passed"] and r["categories"] == ["missing_entity"]


def test_person_diacritics_folded_and_swedish_date():
    text = ("- Anna Kroberg becomes chief executive of Brannex.\n"
            "- She must deliver savings of 340 million kronor.\n"
            "- She takes over on 14 September 2027.")
    assert sc(text, EXP_PERSON)["passed"]


def test_four_lines_fails_line_count():
    r = sc("Summary:\n" + GOOD)
    assert not r["passed"] and "format_line_count" in r["categories"] and not r["valid"]
    assert r["secondary"]["facts_covered"] == 3


def test_blank_lines_between_bullets_fail():
    assert "format_line_count" in sc(GOOD.replace("\n", "\n\n"))["categories"]


def test_other_bullet_marker_fails():
    assert "format_bullet_marker" in sc(GOOD.replace("- ", "* "))["categories"]
    assert "format_bullet_marker" in sc(GOOD.replace("- ", "• "))["categories"]
    numbered = "\n".join(f"{i}. {l[2:]}" for i, l in enumerate(GOOD.splitlines(), 1))
    assert "format_bullet_marker" in sc(numbered)["categories"]


def test_over_20_words_fails():
    long = GOOD.replace("Production starts on 3 March 2027.",
                        "Production at the new site is scheduled to start on 3 March 2027, after a long "
                        "construction period that began this autumn.")
    r = sc(long)
    assert not r["passed"] and "format_too_long" in r["categories"] and r["secondary"]["max_words"] > 20


def test_exactly_20_words_ok():
    line = "- " + " ".join(["word"] * 16) + " on 3 March 2027."
    text = GOOD.splitlines()[0] + "\n" + GOOD.splitlines()[1] + "\n" + line
    r = sc(text)
    assert r["secondary"]["max_words"] == 20 and r["passed"]


def test_markdown_bold_heading_fence_fail():
    assert "format_markdown" in sc(GOOD.replace("Velmora Freight", "**Velmora Freight**"))["categories"]
    assert "format_markdown" in sc(GOOD.replace("partner", "*partner*"))["categories"]
    assert not sc("```\n" + GOOD + "\n```")["passed"]
    assert not sc("## Summary\n" + GOOD)["passed"]


def test_swedish_summary_fails_language():
    text = ("- Brannex bygger en fabrik i Gävle och skapar 1 250 nya jobb.\n"
            "- Fabriken byggs tillsammans med Velmora Freight.\n"
            "- Produktionen startar den 3 mars 2027.")
    r = sc(text)
    assert not r["passed"] and "wrong_language" in r["categories"]


def test_nonanswers():
    assert sc("")["nonanswer"]
    assert sc("I can't help with that.", refusal="refused")["nonanswer"]
    r = sc("Could you paste the full article?")
    assert r["nonanswer"] and r["categories"] == ["nonanswer"] and not r["passed"]


def test_parse_never_raises():
    assert M.parse(None, {}, {}) == {"text": "", "refusal": None}
    assert M.parse([{"text": GOOD}], {}, {})["text"] == GOOD
    assert not M.score(EXP, None)["passed"]


def test_aggregate():
    rows = [{"secondary": sc(GOOD)["secondary"]}, {"secondary": sc("x")["secondary"]}]
    a = M.aggregate(rows)
    assert a["format_ok"] == 0.5 and a["facts_covered"] == 1.5


# ---------------------------------------------------------------- labeller and plan fixtures (every slice)

@pytest.mark.parametrize("variant,slice_", [("main", s) for s in M.slices()] + [("shift", s) for s in M.shift_slices()])
def test_plan_and_label_per_slice(variant, slice_):
    for seed in range(40):
        p = M.plan(random.Random(seed), slice_, variant)
        lab = M.label(p)
        k = p["key"]
        assert lab["number"] == k["number"]["value"] and lab["entity"] == k["entity"]["name"]
        assert 40 <= lab["number"] and not 2000 <= lab["number"] <= 2100
        assert lab["date"][2] <= 28
        assert lab["entity"] != p["subject"]
        assert len(p["distractors"]) == 3
        nums = [d["value"] for d in p["distractors"] if d["kind"] == "number"]
        assert lab["number"] not in nums and len(set(nums)) == len(nums)
        for d in p["distractors"]:
            if d["kind"] == "date":
                assert (d["ymd"][1], d["ymd"][2]) != (lab["date"][1], lab["date"][2])
            if d["kind"] == "name":
                assert d["name"] != lab["entity"]
        if slice_ == "numbers_heavy":
            assert [d["kind"] for d in p["distractors"]] == ["number"] * 3
        if slice_ == "swedish_source":
            assert p["lang"] == "sv" and re.search(r"[a-zåäö]+ \d{4}$", lab["date_text"])
            assert lab["date_text"].split()[1] in M.MONTHS_SV
            if lab["number"] >= 1000:
                assert " " in lab["number_text"]
        else:
            assert p["lang"] == "en"
        if variant == "shift":
            assert p["words"][2:] == [1500, 2000]
            shift_names = {c["name"] for c in M.entities.companies("shift")}
            assert p["subject"] in shift_names
        elif slice_ == "long_articles":
            assert p["words"][2:] == [700, 900]
        # the plan's own anchors are recognised by the scorer's normalisers
        assert M.has_number(lab["number_text"], lab["number"])
        assert M.has_date(lab["date_text"], lab["date"])
        assert M.has_name(lab["entity"], lab["entity"])
        prompt = M.generator_prompt(p)
        for a in [lab["number_text"], lab["entity"], lab["date_text"]] + [M._anchor(d) for d in p["distractors"]]:
            assert f'"{a}"' in prompt


def test_plan_deterministic():
    a = M.plan(random.Random(7), "plain", "main")
    b = M.plan(random.Random(7), "plain", "main")
    assert a == b


def _article(p, near_end=False, filler=60):
    k = p["key"]
    head = "Big news for the company\n\n"
    key = (f"The project brings {k['number']['text']} {k['number']['unit']}. The partner is {k['entity']['name']}. "
           f"It starts on {k['date']['text']}. ")
    minor = " ".join(f"A detail: {M._anchor(d)}." for d in p["distractors"]) + " "
    word = "och detta är som det har varit " if p["lang"] == "sv" else "the company said it was pleased with progress "
    body = word * filler
    return head + (minor + body + key if near_end else key + minor + body)


def test_verify_accepts_and_rejects():
    p = M.plan(random.Random(1), "plain", "main")
    t = M.make_input(p, _article(p))
    assert M.verify(p, t) == (True, "")
    assert not M.verify(p, t.replace(p["key"]["entity"]["name"], "Someone"))[0]
    assert not M.verify(p, t + " Also on 9 July 2027 something happened.")[0] or (7, 9) in \
        {(d["ymd"][1], d["ymd"][2]) for d in p["distractors"] if d["kind"] == "date"}
    assert not M.verify(p, M.make_input(p, _article(p, filler=5)))[0]  # too short


def test_verify_near_end_and_swedish():
    p = M.plan(random.Random(3), "facts_near_end", "main")
    assert M.verify(p, M.make_input(p, _article(p, near_end=True)))[0]
    assert "first half" in M.verify(p, M.make_input(p, _article(p, near_end=False)))[1]
    sv = M.plan(random.Random(3), "swedish_source", "main")
    assert M.verify(sv, M.make_input(sv, _article(sv)))[0]


def test_make_input_strips_markdown_and_nbsp():
    p = M.plan(random.Random(1), "plain", "main")
    t = M.make_input(p, "# **Headline**\r\n\r\n\r\n\r\nText 1 250.")
    assert t == "Headline\n\nText 1 250."


def test_legacy_markers_present():
    assert CASE.check_markers() == []
    assert CASE.legacy_config["model"] == "gpt-5.6-sol" and CASE.legacy_config["settings"]["temperature"] == 0

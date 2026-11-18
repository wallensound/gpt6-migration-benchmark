import random
import re
from pathlib import Path

import pytest

from harness.cases import Case

CASE = Case(str(Path(__file__).resolve().parents[1]))
M = CASE.mod


def item_for(plan, text):
    return {"input": text, **M.item_extras(plan)}


def run(expected, out_text, src_text):
    parsed = M.parse({"text": out_text, "tool_calls": [], "logprobs": None, "status": "completed", "refusal": None},
                     {}, {"input": src_text})
    return M.score(expected, parsed)


def exp(*terms, twice=()):
    return {"terms": [{"sv": s, "en": M.BY_SV[s]["en"], "forbidden": M.BY_SV[s]["forbidden"],
                       "min_count": 2 if s in twice else 1} for s in terms],
            "length_ratio": M.LENGTH_RATIO, "length_bounds": list(M.LENGTH_BOUNDS)}


def src(n):  # a Swedish source of n words
    return " ".join(["ord"] * n)


def en(core, n_total):  # pad an English output to n_total words
    k = M.word_count(core)
    return core + (" " + " ".join(["filler"] * (n_total - k)) if n_total > k else "")


N_SRC = 100
REF = N_SRC * M.LENGTH_RATIO


# ---------------------------------------------------------------- glossary integrity

def test_glossary_sizes_and_uniqueness():
    assert len(M.GLOSSARY) == 40 and len(M.EXTENSION) == 20
    assert len({t["sv"] for t in M.ALL_TERMS}) == 60
    assert all(len(t["forbidden"]) == 2 for t in M.ALL_TERMS)


def test_no_conflicts_inside_a_term():
    for t in M.ALL_TERMS:
        for s in M.sv_strings(t):
            assert not M.avoid_hits(t, s), (t["sv"], s)
        for f in t["forbidden"]:
            assert not M.en_count(f, t["en"]), t["sv"]
        for comp, gloss in t["compounds"]:
            assert M.en_count(t["en"], gloss), comp
            assert comp.lower().endswith(t["sv"].lower()) or t["sv"].lower() in comp.lower()
        for f in t["forms"]:
            assert f != t["sv"]


def test_spec_and_legacy_prompt_list_every_term():
    spec = CASE.spec_text
    for t in M.ALL_TERMS:
        row = f"| {t['sv']} | {t['en']} | {', '.join(t['forbidden'])} |"
        assert row in spec, row
    for t in M.GLOSSARY:
        assert f"- {t['sv']} -> {t['en']} (NEVER: {', '.join(t['forbidden'])})" in CASE.legacy_prompt
    for t in M.EXTENSION:  # the extension is unseen by the prompt
        assert f"- {t['sv']} ->" not in CASE.legacy_prompt
    assert f"LENGTH_RATIO = {M.LENGTH_RATIO}" in spec


def test_legacy_markers_present():
    assert CASE.check_markers() == []
    assert CASE.legacy_config["settings"]["temperature"] == 0
    assert CASE.legacy_config["api"] == "chat" and CASE.legacy_config["effort"] == "none"


# ---------------------------------------------------------------- plans

@pytest.mark.parametrize("variant", ["main", "shift"])
@pytest.mark.parametrize("sl", M.slices())
def test_plans_are_valid(sl, variant):
    for seed in range(40):
        p = M.plan(random.Random(seed), sl, variant)
        assert p == M.plan(random.Random(seed), sl, variant)  # deterministic
        terms = p["terms"]
        assert 3 <= len(terms) <= 8
        for i, a in enumerate(terms):
            for b in terms[i + 1:]:
                assert M.compatible(M.BY_SV[a["sv"]], M.BY_SV[b["sv"]])
        modes = [t["mode"] for t in terms]
        want = {"plain": None, "inflected_forms": "form", "compound_words": "compound", "terms_in_lists": "list",
                "terms_used_twice": "twice"}[sl]
        if want is None:
            assert set(modes) == {"lemma"}
        else:
            assert want in modes
        if sl == "terms_in_lists":
            assert modes.count("list") >= 3
        if variant == "shift":
            assert sum(t["glossary"] == "extension" for t in terms) >= 3
            assert all(t["glossary"] == "extension" for t in terms if t["mode"] != "lemma")
            assert M.item_extras({**p, "variant": "shift"})["context"].startswith("Additional glossary")
        else:
            assert all(t["glossary"] == "main" for t in terms)
            assert M.item_extras({**p, "variant": "main"}) == {}
        lab = M.label(p)
        assert [t["sv"] for t in lab["terms"]] == [t["sv"] for t in terms]
        assert all(t["min_count"] == (2 if t["sv"] in [x["sv"] for x in terms if x["mode"] == "twice"] else 1)
                   for t in lab["terms"])


def _fixed_plan(terms, **kw):
    return {"domain": "electronics", "product_type": "portable speaker", "brand": "Velmora", "product": "Kastrix",
            "style": "s", "opening": "o", "paragraphs": 1, "length": [85, 120], "variant": "main",
            "slice": kw.get("slice", "plain"), "terms": terms}


BASE = ("Velmora presenterar Kastrix, en högtalare för hemmet och resan. Den har ett rent formspråk och ett ljud "
        "som fyller rummet utan att bli skarpt. Du styr allt med appen och ljudet är fylligt även på låg volym. ")
PAD = "Den passar lika bra i köket som på balkongen och tar liten plats i väskan när du ska iväg. " * 4


def test_verify_inflected_form_must_be_exact():
    p = _fixed_plan([{"sv": "laddare", "glossary": "main", "mode": "form", "surface": "laddaren", "min_count": 1},
                     {"sv": "garanti", "glossary": "main", "mode": "lemma", "surface": "garanti", "min_count": 1},
                     {"sv": "batteri", "glossary": "main", "mode": "lemma", "surface": "batteri", "min_count": 1}],
                    slice="inflected_forms")
    ok_text = BASE + "Laddaren ingår och ett batteri räcker hela dagen. Två års garanti ingår. " + PAD
    assert M.verify(p, ok_text) == (True, "")
    bad = ok_text.replace("Laddaren", "En laddare")
    assert M.verify(p, bad)[0] is False


def test_verify_compound_and_avoid_words():
    p = _fixed_plan([{"sv": "batteri", "glossary": "main", "mode": "compound", "surface": "batteritid",
                      "min_count": 1},
                     {"sv": "fodral", "glossary": "main", "mode": "lemma", "surface": "fodral", "min_count": 1},
                     {"sv": "vikt", "glossary": "main", "mode": "lemma", "surface": "vikt", "min_count": 1}],
                    slice="compound_words")
    t = BASE + "Batteritiden är lång, ett fodral ingår och den låga vikt gör den lätt att bära. " + PAD
    assert M.verify(p, t) == (True, "")
    assert "avoid word" in M.verify(p, t + " Den levereras i en påse.")[1]  # påse -> pouch (forbidden for fodral)
    assert M.verify(p, t.replace("Batteritiden", "Tiden"))[0] is False


def test_verify_list_and_twice():
    p = _fixed_plan([{"sv": "laddare", "glossary": "main", "mode": "list", "surface": "laddare", "min_count": 1},
                     {"sv": "fodral", "glossary": "main", "mode": "list", "surface": "fodral", "min_count": 1},
                     {"sv": "bruksanvisning", "glossary": "main", "mode": "list", "surface": "bruksanvisning",
                      "min_count": 1},
                     {"sv": "sladd", "glossary": "main", "mode": "twice", "surface": "sladd", "min_count": 2}],
                    slice="terms_in_lists")
    t = (BASE + "I köpet ingår en laddare, ett fodral och en bruksanvisning. Sladden är flätad. "
         "En extra sladd kan köpas till. " + PAD)
    assert M.verify(p, t) == (True, "")
    split = t.replace("en laddare, ett fodral och en bruksanvisning", "en laddare och ett fodral. Där finns en "
                      "bruksanvisning")
    assert M.verify(p, split)[0] is False
    assert M.verify(p, t.replace("En extra sladd kan köpas till. ", ""))[0] is False


def test_verify_rejects_markdown_and_length():
    p = _fixed_plan([{"sv": "laddare", "glossary": "main", "mode": "lemma", "surface": "laddare", "min_count": 1}])
    t = BASE + "En laddare ingår. " + PAD
    assert M.verify(p, t)[0]
    assert M.verify(p, "- " + t)[0] is False
    assert M.verify(p, "Velmora Kastrix laddare.")[0] is False


def test_generator_prompt_demands_planned_strings():
    p = M.plan(random.Random(5), "compound_words", "main")
    g = M.generator_prompt(p)
    for t in p["terms"]:
        assert f'"{t["surface"]}"' in g
    assert p["brand"] in g and p["product"] in g and "Markdown" in g


# ---------------------------------------------------------------- scorer

def test_score_plain_pass():
    e = exp("laddare", "garanti", "vikt")
    out = en("The charger is included. A two-year warranty applies. Its low weight helps.", 115)
    r = run(e, out, src(N_SRC))
    assert r["passed"] and r["valid"] and not r["categories"], r


def test_score_inflected_plural_and_possessive():
    e = exp("batteri", "tillbehör", "leverans")
    out = en("Both batteries last long. All accessories fit. The battery's cells and deliveries are fast.", 115)
    assert run(e, out, src(N_SRC))["passed"]


def test_score_compound_rendering():
    e = exp("batteri", "läge", "laddare")
    out = en("Battery life is ten hours, the night mode dims the light and a fast charger is included.", 115)
    assert run(e, out, src(N_SRC))["passed"]
    out2 = en("Runtime is ten hours, the night mode dims the light and a fast charger is included.", 115)
    r = run(e, out2, src(N_SRC))
    assert not r["passed"] and "missing_term" in r["categories"]


def test_score_hyphen_and_space_equivalent():
    e = exp("slitstark", "strömbrytare", "laddare")
    out = en("The hard wearing shell, a power-switch and the charger.", 115)
    assert run(e, out, src(N_SRC))["passed"]


def test_score_forbidden_alternative_fails():
    e = exp("laddare", "skärm", "garanti")
    out = en("The charger and display come with a warranty. The screen is bright.", 115)
    r = run(e, out, src(N_SRC))
    assert not r["passed"] and r["valid"] and r["categories"] == ["forbidden_term"]


def test_score_forbidden_of_unplanned_term_is_ignored():
    e = exp("laddare", "garanti", "vikt")
    out = en("The charger, the warranty and the weight. The screen is bright.", 115)  # screen: skärm not planned
    assert run(e, out, src(N_SRC))["passed"]


def test_score_word_boundaries():
    e = exp("lampa", "fläkt", "garanti")
    out = en("A headlamp, a fanatic warranty.", 115)  # neither 'lamp' nor 'fan' as words
    r = run(e, out, src(N_SRC))
    assert not r["passed"] and r["diff"].count("missing") == 2


def test_score_terms_used_twice():
    e = exp("sladd", "laddare", "fodral", twice=("sladd",))
    once = en("The cord is braided. The charger and case are included. It can be replaced.", 115)
    r = run(e, once, src(N_SRC))
    assert not r["passed"] and r["categories"] == ["repeat_not_kept"]
    twice = en("The cord is braided. The charger and case are included. A spare cord can be bought.", 115)
    assert run(e, twice, src(N_SRC))["passed"]


def test_score_terms_in_list_forbidden():
    e = exp("laddare", "fodral", "bruksanvisning", "sladd")
    out = en("You get a charger, a pouch, a user manual and a cord.", 115)
    r = run(e, out, src(N_SRC))
    assert not r["passed"] and r["valid"] and set(r["categories"]) == {"missing_term", "forbidden_term"}


def test_score_terms_in_list_pass():
    e = exp("laddare", "fodral", "bruksanvisning", "sladd")
    out = en("You get a charger, a case, a user manual and a cord.", 115)
    assert run(e, out, src(N_SRC))["passed"]


def test_score_markdown_is_invalid():
    e = exp("laddare", "garanti", "vikt")
    body = "The charger, the warranty and the weight."
    for out in ["**Kastrix**\n" + body, "# Kastrix\n" + body, body + "\n- charger\n- warranty", "1. " + body]:
        r = run(e, en(out, 115), src(N_SRC))
        assert not r["passed"] and not r["valid"] and "markdown" in r["categories"], out


def test_score_preamble_and_notes_are_invalid():
    e = exp("laddare", "garanti", "vikt")
    body = "The charger, the warranty and the weight."
    for out in ["Here is the translation:\n" + body, body + "\n\nNote: 'laddare' was translated as charger."]:
        r = run(e, en(out, 115), src(N_SRC))
        assert not r["passed"] and not r["valid"] and "preamble" in r["categories"]


def test_score_length_window():
    e = exp("laddare", "garanti", "vikt")
    body = "The charger, the warranty and the weight."
    lo, hi = M.LENGTH_BOUNDS
    assert run(e, en(body, int(REF * lo) + 1), src(N_SRC))["passed"]
    assert run(e, en(body, int(REF * hi)), src(N_SRC))["passed"]
    r = run(e, en(body, int(REF * lo) - 2), src(N_SRC))
    assert r["categories"] == ["too_short"] and r["valid"]
    r = run(e, en(body, int(REF * hi) + 3), src(N_SRC))
    assert r["categories"] == ["too_long"]


def test_score_nonanswer_and_parse_robustness():
    e = exp("laddare", "garanti", "vikt")
    r = run(e, "", src(N_SRC))
    assert r["nonanswer"] and not r["valid"] and not r["passed"]
    r = run(e, "Could you please provide the full text? I'm sorry, I cannot translate this.", src(N_SRC))
    assert r["nonanswer"]
    p = M.parse(None, {}, None)
    assert M.score(e, p)["nonanswer"]
    p = M.parse([{"text": "x"}], {}, {"input": "a b"})
    assert p["text"] == "x" and p["src_words"] == 2


def test_word_count_rules():
    assert M.word_count("USB-C-kontakt, 5 000 mAh och 2,5 kg!") == 8
    assert M.word_count("it's a well-made charger's case") == 5


def test_answer_strings_only_extension():
    assert M.answer_strings(exp("laddare", "garanti")) == []
    e = {"terms": [{"sv": "termos", "en": "vacuum flask", "forbidden": [], "min_count": 1},
                   {"sv": "luva", "en": "hood", "forbidden": [], "min_count": 1}]}
    assert M.answer_strings(e) == ["vacuum flask"]


def test_extension_context_lists_all_extension_terms():
    ctx = M.extension_glossary_text()
    assert len(re.findall(r"^- ", ctx, flags=re.MULTILINE)) == 20
    assert CASE.user_message({"input": "X", "context": ctx}, {}).endswith(ctx)

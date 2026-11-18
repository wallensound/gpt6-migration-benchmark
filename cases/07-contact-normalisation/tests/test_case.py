"""Case 07 tests: normaliser fixtures per slice, plan/label consistency, verify, scorer and legacy markers."""
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from harness.cases import Case  # noqa: E402

CASE = Case(str(Path(__file__).resolve().parents[1]))
M = CASE.mod


def rec(*lines):
    """lines: (field, value) pairs; label text and separator are fixed."""
    return [[f, f.capitalize(), ": ", v] for f, v in lines]


FIXTURES = [
    # (slice, record lines, expected)
    ("plain", rec(("name", "  anna   BERG "), ("phone", "070-123 45 67"), ("email", "Anna.Berg@Bohera.SE"),
                  ("company", "BOHERA AB"), ("country", "Sverige")),
     {"name": "Anna Berg", "phone": "+46701234567", "email": "anna.berg@bohera.se", "company": "Bohera",
      "country": "SE"}),
    ("plain", rec(("name", "Mr Paul Kramson"), ("phone", "(415) 555 0132"), ("email", "paul@semplarlabs.com"),
                  ("company", "semplar labs, Corp."), ("country", "USA")),
     {"name": "Paul Kramson", "phone": "+14155550132", "email": "paul@semplarlabs.com", "company": "Semplar Labs",
      "country": "US"}),
    ("plain", rec(("name", "Nertrent, Maria"), ("phone", "0151 2345 6789"), ("email", "m.nertrent@gmail.com"),
                  ("company", "Velmora GmbH"), ("country", "Deutschland")),
     {"name": "Maria Nertrent", "phone": "+4915123456789", "email": "m.nertrent@gmail.com", "company": "Velmora",
      "country": "DE"}),
    ("plain", rec(("name", "lena tras"), ("phone", "+44 7700 900123"), ("email", "<LENA@TRAS.CO.UK>"),
                  ("company", "Glorix"), ("country", "uk")),
     {"name": "Lena Tras", "phone": "+447700900123", "email": "lena@tras.co.uk", "company": "Glorix",
      "country": "GB"}),
    ("precedence_conflict", rec(("name", "Erik Domar"), ("phone", "+46 70 123 45 67"), ("email", "erik@domar.se"),
                                ("company", "Domar AB")),
     {"name": "Erik Domar", "phone": "+46701234567", "email": "erik@domar.se", "company": "Domar", "country": "SE"}),
    ("precedence_conflict", rec(("name", "Ida Kesh"), ("phone", "0049 30 1234 5678"), ("email", "ida@kesh.de"),
                                ("company", "Kesh"), ("country", "n/a")),
     {"name": "Ida Kesh", "phone": "+493012345678", "email": "ida@kesh.de", "company": "Kesh", "country": "DE"}),
    ("precedence_conflict", rec(("name", "Max Tolle"), ("phone", "+1 415 555 0132"), ("email", "max@tolle.com"),
                                ("company", "Tolle"), ("country", "-")),
     {"name": "Max Tolle", "phone": "+14155550132", "email": "max@tolle.com", "company": "Tolle", "country": None}),
    ("international_phone", rec(("name", "Nils Ora"), ("phone", "+44 (0)20 7946 0018"), ("email", "n@ora.co.uk"),
                                ("company", "Ora Ltd"), ("country", "Storbritannien")),
     {"name": "Nils Ora", "phone": "+442079460018", "email": "n@ora.co.uk", "company": "Ora", "country": "GB"}),
    ("international_phone", rec(("name", "Sara Lind"), ("phone", "+49 151 2345 6789 ext. 204"),
                                ("email", "sara@lind.se"), ("company", "Lind"), ("country", "Schweden")),
     {"name": "Sara Lind", "phone": "+4915123456789", "email": "sara@lind.se", "company": "Lind", "country": "SE"}),
    ("international_phone", rec(("name", "Karl Mo"), ("phone", "00358.40.123.4567 x123"), ("email", "karl@mo.fi"),
                                ("company", "Mo Oyj"), ("country", "FIN")),
     {"name": "Karl Mo", "phone": "+358401234567", "email": "karl@mo.fi", "company": "Mo", "country": "FI"}),
    ("missing_fields", rec(("name", "Hugo Pefentez"), ("phone", "unknown"), ("email", ""), ("company", "Bohera AB"),
                           ("country", "Frankrike")),
     {"name": "Hugo Pefentez", "phone": None, "email": None, "company": "Bohera", "country": "FR"}),
    ("missing_fields", rec(("name", "Priya Jesha"), ("email", "priya@jesha.nl")),
     {"name": "Priya Jesha", "phone": None, "email": "priya@jesha.nl", "company": None, "country": None}),
    ("missing_fields", rec(("name", "Omar Fel"), ("phone", "612 345 678"), ("email", "omar@fel.es"),
                           ("company", "TBD")),
     {"name": "Omar Fel", "phone": None, "email": "omar@fel.es", "company": None, "country": None}),
    ("unicode_names", rec(("name", "ÅSA KRÖNBERG"), ("phone", "+46701234567"), ("email", "asa@kronberg.se"),
                          ("company", "Vömdivex AB"), ("country", "SE")),
     {"name": "Åsa Krönberg", "phone": "+46701234567", "email": "asa@kronberg.se", "company": "Vömdivex",
      "country": "SE"}),
    ("unicode_names", rec(("name", "cusdrovaström, marie-hélène"), ("phone", "06 12 34 56 78"),
                          ("email", "mh@x.fr"), ("company", "x"), ("country", "france")),
     {"name": "Marie-Hélène Cusdrovaström", "phone": "+33612345678", "email": "mh@x.fr", "company": "X",
      "country": "FR"}),
    ("unicode_names", rec(("name", "Prof. łukasz żelno"), ("phone", "512 345 678"), ("email", "l@z.pl"),
                          ("company", "Zel Sp. z o.o."), ("country", "Polen")),
     {"name": "Łukasz Żelno", "phone": "+48512345678", "email": "l@z.pl", "company": "Zel", "country": "PL"}),
    ("swapped_fields", rec(("name", "Jonas Brik"), ("phone", "JONAS@BRIK.DK"), ("email", "20 12 34 56"),
                           ("company", "Brik ApS"), ("country", "Dänemark")),
     {"name": "Jonas Brik", "phone": "+4520123456", "email": "jonas@brik.dk", "company": "Brik", "country": "DK"}),
    ("swapped_fields", rec(("name", "Trelvo Systems AG"), ("phone", "+41 76 123 45 67"), ("email", "f@trelvo.ch"),
                           ("company", "felix STROM"), ("country", "Schweiz")),
     {"name": "Felix Strom", "phone": "+41761234567", "email": "f@trelvo.ch", "company": "Trelvo Systems",
      "country": "CH"}),
    ("swapped_fields", rec(("name", "Kalix, S.p.A."), ("phone", "emma@kalix.it"), ("email", "333 123 4567"),
                           ("company", "Rossi, Emma"), ("country", "Italien")),
     {"name": "Emma Rossi", "phone": "+393331234567", "email": "emma@kalix.it", "company": "Kalix",
      "country": "IT"}),
    ("shift", rec(("name", "Kenji Sato"), ("phone", "tel:090-1234-5678"), ("email", "kenji@sato.co.jp"),
                  ("company", "Sato K.K."), ("country", "Japan")),
     {"name": "Kenji Sato", "phone": "+819012345678", "email": "kenji@sato.co.jp", "company": "Sato",
      "country": "JP"}),
    ("shift", rec(("name", "Mateo Lima"), ("phone", "(+55) 11 91234 5678"), ("email", "m@lima.com.br"),
                  ("company", "Lima Ltda."), ("country", "Brasilien")),
     {"name": "Mateo Lima", "phone": "+5511912345678", "email": "m@lima.com.br", "company": "Lima",
      "country": "BR"}),
    ("shift", rec(("name", "Zara Ince"), ("phone", "0532 / 1234567"), ("email", "z@ince.com.tr"),
                  ("company", "Ince"), ("country", "Türkiye")),
     {"name": "Zara Ince", "phone": "+905321234567", "email": "z@ince.com.tr", "company": "Ince", "country": "TR"}),
]


@pytest.mark.parametrize("sl,lines,expected", FIXTURES, ids=[f"{i}-{f[0]}" for i, f in enumerate(FIXTURES)])
def test_normaliser_fixtures(sl, lines, expected):
    assert M.normalise_record(lines) == expected


def test_fixtures_cover_every_slice():
    covered = {f[0] for f in FIXTURES}
    assert set(M.slices()) <= covered and "shift" in covered
    assert len(FIXTURES) >= 15


@pytest.mark.parametrize("variant", ["main", "shift"])
def test_label_reproduces_clean_record(variant):
    for i in range(1500):
        sl = M.slices()[i % len(M.slices())]
        p = {**M.plan(random.Random(i), sl, variant), "slice": sl, "variant": variant}
        assert M.label(p) == p["clean"], (sl, p["record_lines"])
        json.dumps(p)


def test_slice_properties():
    for i in range(300):
        p = {**M.plan(random.Random(i), "precedence_conflict", "main"), "slice": "precedence_conflict"}
        assert M.label(p)["country"] is not None and "country" in p["missing"]
        p = {**M.plan(random.Random(i), "unicode_names", "main"), "slice": "unicode_names"}
        assert not M.label(p)["name"].isascii()
        p = {**M.plan(random.Random(i), "swapped_fields", "main"), "slice": "swapped_fields"}
        assert p["swap"]
        p = M.plan(random.Random(i), "plain", "shift")
        assert p["country_iso"] in M.SHIFT_COUNTRIES


def _plan(sl="plain", seed=3):
    return {**M.plan(random.Random(seed), sl, "main"), "slice": sl, "variant": "main"}


def test_make_input_and_verify():
    p = _plan()
    p["mention_first"] = False
    text = M.make_input(p, "Hi team, please add this one.\n<<RECORD>>\nThanks, Sales ops")
    assert M.record_text(p) in text
    assert M.verify(p, text) == (True, "")
    assert not M.verify(p, M.make_input(p, "No record here."))[0]
    assert not M.verify(p, M.make_input(p, "Add <<RECORD>> please"))[0]
    assert not M.verify(p, text + "\nAlso call 070 123 45 67.")[0]
    assert not M.verify(p, text + "\nShe moved to Germany.")[0]
    assert not M.verify(p, text + "\nCC x@y.com")[0]
    assert not M.verify(p, text + f"\nSurname is {p['last_name']}.")[0]


def _out(text):
    return {"text": text, "tool_calls": [], "logprobs": None, "status": "stop", "refusal": None}


EXP = {"name": "Anna Berg", "phone": "+46701234567", "email": "anna@b.se", "company": "Bohera", "country": "SE"}


def test_score_pass_and_fail():
    s = CASE.score(EXP, CASE.parse(_out(json.dumps(EXP)), {}, {}))
    assert s["passed"] and s["valid"] and s["secondary"]["field_accuracy"] == 1.0
    bad = {**EXP, "country": None}
    s = CASE.score(EXP, CASE.parse(_out(json.dumps(bad)), {}, {}))
    assert not s["passed"] and s["valid"] and "dropped_value" in s["categories"]
    assert s["secondary"]["fields_correct"] == 4
    s = CASE.score({**EXP, "email": None}, CASE.parse(_out(json.dumps(EXP)), {}, {}))
    assert "invented_value" in s["categories"]
    s = CASE.score(EXP, CASE.parse(_out(json.dumps({**EXP, "phone": "+46 70 123 45 67"})), {}, {}))
    assert "phone_wrong" in s["categories"] and s["secondary"]["format_valid_fields"] == 4


def test_score_format_failures():
    s = CASE.score(EXP, CASE.parse(_out("```json\n" + json.dumps(EXP) + "\n```"), {}, {}))
    assert not s["passed"] and not s["valid"] and "format" in s["categories"]
    assert s["secondary"]["fields_correct"] == 5  # salvaged for diagnostics
    s = CASE.score(EXP, CASE.parse(_out("Here you go: " + json.dumps(EXP)), {}, {}))
    assert not s["passed"] and not s["valid"]
    s = CASE.score(EXP, CASE.parse(_out(json.dumps({**EXP, "notes": "x"})), {}, {}))
    assert not s["passed"] and not s["valid"]
    s = CASE.score({**EXP, "email": None}, CASE.parse(_out(json.dumps({**EXP, "email": ""})), {}, {}))
    assert not s["passed"]
    s = CASE.score(EXP, CASE.parse(_out("Which country should I use?"), {}, {}))
    assert s["nonanswer"] and not s["passed"]
    s = CASE.score(EXP, CASE.parse(_out(""), {}, {}))
    assert s["nonanswer"]
    s = CASE.score(EXP, CASE.parse({"text": "", "tool_calls": [], "refusal": "no", "status": "stop"}, {}, {}))
    assert s["nonanswer"]


def test_score_unicode_nfc():
    import unicodedata
    exp = {**EXP, "name": "Åsa Krönberg"}
    got = {**exp, "name": unicodedata.normalize("NFD", "Åsa Krönberg")}
    assert CASE.score(exp, CASE.parse(_out(json.dumps(got, ensure_ascii=False)), {}, {}))["passed"]


def test_aggregate_and_schema():
    rows = [{"passed": True, "valid": True, "secondary": CASE.score(EXP, CASE.parse(_out(json.dumps(EXP)), {}, {}))[
        "secondary"]}, {"passed": False, "valid": False, "secondary": {}}]
    a = CASE.aggregate(rows)
    assert a["field_accuracy"] == 0.5 and a["json_validity"] == 0.5
    sch = CASE.schema({})
    assert sch["additionalProperties"] is False and set(sch["required"]) == set(M.FIELDS)
    assert "structured_outputs" in CASE.settings_space()


def test_generator_prompt_mentions_placeholder():
    p = _plan("missing_fields")
    g = M.generator_prompt(p)
    assert M.PLACEHOLDER in g and p["last_name"] not in g
    assert "deliberately absent" in M.verifier_brief(p)


def test_legacy_markers_present():
    assert CASE.check_markers() == []
    cfg = CASE.legacy_config
    assert cfg["model"] == "gpt-5.6-sol" and cfg["settings"]["temperature"] == 0 and cfg["effort"] == "none"
    lp = CASE.legacy_prompt
    assert "IMPORTANT" in lp and "PRECEDENCE" in lp and lp.count("E.164") >= 3

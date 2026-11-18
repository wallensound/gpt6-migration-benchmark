"""Labeller, scorer, parser and verifier fixtures for case 02 (no API calls)."""
import json
import random
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from harness.cases import Case  # noqa: E402

CASE = Case("02")
M = CASE.mod
SLICES = CASE.slices()


def mk(slice_, seed, variant="main"):
    return {**M.plan(random.Random(seed), slice_, variant), "slice": slice_, "variant": variant}


def out(obj, logprobs=None):
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return {"text": text, "tool_calls": [], "logprobs": logprobs, "status": "stop", "refusal": None}


LEGACY = {"flag_method": "logprob", "flag_threshold": -0.1, "structured_outputs": True, "logprobs": True}


def run(expected, obj, settings=None, logprobs=None):
    parsed = M.parse(out(obj, logprobs) if not isinstance(obj, list) else obj, settings or {"flag_method": "none"}, {})
    return parsed, M.score(expected, parsed)


# --------------------------------------------------------------------------- independent surface readers

MONTHS = {m.lower(): i + 1 for i, m in enumerate(M.EN_MONTHS)}
MONTHS.update({m.lower(): i + 1 for i, m in enumerate(M.EN_MON)})
MONTHS.update({m.lower(): i + 1 for i, m in enumerate(M.SV_MONTHS)})
MONTHS.update({m.lower(): i + 1 for i, m in enumerate(M.DE_MONTHS)})


def read_date(s):
    """Day-first reading of every date form the spec lists, written independently of the case code."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        y, m, d = map(int, s.split("-"))
        return date(y, m, d)
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        return date(y + 2000 if y < 100 else y, mo, d)
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\.?[ -]([A-Za-zäÄ]+)[ -](\d{2,4})", s)
    if m:
        y = int(m.group(3))
        return date(y + 2000 if y < 100 else y, MONTHS[m.group(2).lower()], int(m.group(1)))
    m = re.fullmatch(r"([A-Za-z]+) (\d{1,2}), (\d{4})", s)
    if m:
        return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
    raise ValueError(s)


def read_amount(s):
    s = s.strip()
    dec = s[-3]
    assert dec in ".,"
    ip = re.sub(r"[ .,]", "", s[:-3])
    return Decimal(f"{ip}.{s[-2:]}")


# --------------------------------------------------------------------------- labeller fixtures (every slice)

@pytest.mark.parametrize("variant", ["main", "shift"])
@pytest.mark.parametrize("slice_", SLICES)
def test_label_matches_planned_surfaces(slice_, variant):
    for seed in range(40):
        p = mk(slice_, seed, variant)
        e = M.label(p)
        assert set(e) == set(M.FIELDS)
        miss = set(p["missing"])
        for f in miss:
            assert e[f] is None
        if "issue_date" not in miss:
            assert read_date(p["issue_surface"]).isoformat() == e["issue_date"]
        if "due_date" not in miss:
            assert read_date(p["due_surface"]).isoformat() == e["due_date"]
            if e["issue_date"]:
                assert e["due_date"] > e["issue_date"]
        for f in ("net", "vat", "total"):
            if e[f] is not None:
                assert re.fullmatch(r"\d+\.\d{2}", e[f])
                assert read_amount(p[f + "_surface"]) == Decimal(e[f])
        if e["net"] and e["vat"]:
            assert Decimal(e["net"]) + Decimal(e["vat"]) == Decimal(e["total"])
        assert e["currency"] in M.CURRENCY_CODES
        assert e["vendor"] != p["buyer"]
        # the rendered draft itself satisfies the code verifier (renderer and verifier agree)
        ok, why = M.verify(p, M.make_input(p, M.render_draft(p)))
        assert ok, why


def test_slice_specific_properties():
    for seed in range(60):
        p = mk("swedish", seed)
        assert p["lang"] == "sv" and p["vendor_country"] == "Sweden" and "Förfallodatum" in M.render_draft(p)
        p = mk("german", seed)
        assert p["lang"] == "de" and "MwSt." in M.render_draft(p) and p["currency"] == "EUR"
        p = mk("decimal_comma", seed)
        assert "," in p["total_surface"] and p["total_surface"].index(",") == len(p["total_surface"]) - 3
        p = mk("subtotal_vs_total", seed)
        assert p["subtotal_surface"] and Decimal(M.label(p)["net"]) < read_amount(p["subtotal_surface"])
        p = mk("mixed_currencies", seed)
        assert p["info"] and p["info"]["currency"] != p["currency"]
        p = mk("missing_field", seed)
        assert p["missing"] and all(M.label(p)[f] is None for f in p["missing"])
        p = mk("date_formats", seed, "shift")
        assert p["template"] in M.SHIFT_TEMPLATES and p["noise_seed"] is not None


def test_slice_weights_and_shift_pool():
    w = M.slice_weights("main")
    assert abs(w["swedish"] / sum(w.values()) - 0.2) < 0.01 and abs(w["german"] / sum(w.values()) - 0.1) < 0.01
    from harness import entities
    shift_names = {c["legal_name"] for c in entities.companies("shift")}
    assert all(mk(s, i, "shift")["vendor"] in shift_names for s in SLICES for i in range(5))
    assert all(mk(s, i)["template"] in M.MAIN_TEMPLATES for s in SLICES for i in range(5))


def test_hand_written_label_fixture():
    p = mk("date_formats", 1)
    p.update(issue_surface="03/04/26", issue_date="2026-04-03", due_surface="May 3, 2026", due_date="2026-05-03",
             missing=[])
    assert M.label(p)["issue_date"] == "2026-04-03" and M.label(p)["due_date"] == "2026-05-03"
    p["missing"] = ["due_date", "invoice_number"]
    assert M.label(p)["due_date"] is None and M.label(p)["invoice_number"] is None


def test_amount_and_date_formatters():
    assert M.fmt_amount(Decimal("1234.5"), "en") == "1,234.50"
    assert M.fmt_amount(Decimal("1234567.5"), "de") == "1.234.567,50"
    assert M.fmt_amount(Decimal("1234.5"), "sv") == "1 234,50"
    assert M.fmt_amount(Decimal("999.05"), "sv") == "999,05"
    assert M.fmt_amount(Decimal("1234.5"), "plain_comma") == "1234,50"
    d = date(2026, 3, 4)
    assert M.fmt_date(d, "dmy_slash_short") == "04/03/26"
    assert M.fmt_date(d, "ordinal") == "4th March 2026"
    assert M.fmt_date(date(2026, 3, 12), "ordinal") == "12th March 2026"
    assert M.fmt_date(d, "de_d_month_y") == "4. März 2026"
    assert M.fmt_date(d, "sv_d_month_y") == "4 mars 2026"


# --------------------------------------------------------------------------- verifier

def test_verify_rejects_unplanned_values():
    p = mk("subtotal_vs_total", 3)
    t = M.make_input(p, M.render_draft(p))
    assert M.verify(p, t)[0]
    assert not M.verify(p, t + "\nShipping 49.00")[0]
    assert not M.verify(p, t + "\nOrder date 01.02.2026")[0]
    assert not M.verify(p, t + "\nPayment terms: 30 days net")[0]
    assert not M.verify(p, t + "\nAlso payable in JPY")[0]
    assert not M.verify(p, t.replace(p["net_surface"], "X"))[0]
    assert not M.verify(p, "```\n" + t + "\n```")[0]
    other = next(c for c in __import__("harness.entities", fromlist=["x"]).companies("main")
                 if c["name"] not in (p["vendor_name"], p["buyer_name"]) and c["name"] not in M._CITY_NAMES)
    assert not M.verify(p, t + f"\nPowered by {other['name']}")[0]


def test_verify_missing_field_labels():
    for seed in range(80):
        p = mk("missing_field", seed)
        if p["missing"] == ["due_date"]:
            t = M.make_input(p, M.render_draft(p))
            assert M.verify(p, t)[0]
            assert not M.verify(p, t + "\nDue date: on receipt")[0]
            return
    pytest.fail("no due_date-missing plan found")


def test_shift_noise_keeps_planned_strings():
    for seed in range(40):
        p = mk("swedish", seed, "shift")
        clean = M.render_draft(p)
        noisy = M.make_input(p, clean)
        for _, s in M.verbatim_strings(p):
            assert s in noisy
        assert M.verify(p, noisy)[0]
    assert any(M.make_input(mk("german", s, "shift"), M.render_draft(mk("german", s, "shift")))
               != M.render_draft(mk("german", s, "shift")) for s in range(10))


def test_make_input_strips_fences_and_nbsp():
    p = mk("swedish", 2)
    assert M.make_input(p, "```\n1 234,50\n```") == "1 234,50"


# --------------------------------------------------------------------------- scorer fixtures

EXP = {"vendor": "Velmora AB", "invoice_number": "INV-2026-0412", "issue_date": "2026-04-03",
       "due_date": "2026-05-03", "currency": "SEK", "net": "1234.50", "vat": "308.63", "total": "1543.13"}


def test_score_exact_pass():
    parsed, sc = run(EXP, dict(EXP))
    assert sc["passed"] and sc["valid"] and sc["secondary"]["fields_correct"] == 8


def test_score_amounts_as_numbers_and_short_decimals_pass():
    _, sc = run(EXP, {**EXP, "net": 1234.5, "vat": "308.63", "total": "1543.13"})
    assert sc["passed"]
    _, sc = run(EXP, {**EXP, "net": "1234.5"})
    assert sc["passed"]


def test_score_amount_with_separators_fails():
    _, sc = run(EXP, {**EXP, "net": "1,234.50"})
    assert not sc["passed"] and sc["valid"] and "amount_format" in sc["categories"]
    _, sc = run(EXP, {**EXP, "total": "SEK 1543.13"})
    assert not sc["passed"] and "amount_format" in sc["categories"]


def test_score_day_month_swap_fails():
    _, sc = run(EXP, {**EXP, "issue_date": "2026-03-04"})
    assert not sc["passed"] and sc["categories"] == ["wrong_date"]
    _, sc = run(EXP, {**EXP, "issue_date": "03.04.2026"})
    assert not sc["passed"]


def test_score_nulls():
    exp = {**EXP, "due_date": None}
    _, sc = run(exp, {**EXP, "due_date": None})
    assert sc["passed"]
    _, sc = run(exp, dict(EXP))
    assert not sc["passed"] and "hallucinated_value" in sc["categories"]
    _, sc = run(exp, {**EXP, "due_date": ""})
    assert not sc["passed"]
    _, sc = run(EXP, {**EXP, "vat": None})
    assert not sc["passed"] and "missed_value" in sc["categories"]


def test_score_vendor_and_currency_normalisation():
    _, sc = run(EXP, {**EXP, "vendor": "  velmora   ab ", "currency": "sek", "invoice_number": "inv-2026-0412"})
    assert sc["passed"]
    _, sc = run(EXP, {**EXP, "vendor": "Velmora"})
    assert not sc["passed"] and "wrong_vendor" in sc["categories"]
    _, sc = run(EXP, {**EXP, "currency": "kr"})
    assert not sc["passed"] and "wrong_currency" in sc["categories"]


def test_score_subtotal_as_net_fails():
    _, sc = run(EXP, {**EXP, "net": "1371.67"})
    assert not sc["passed"] and sc["secondary"]["fields_correct"] == 7


def test_score_format_failures():
    _, sc = run(EXP, "```json\n" + json.dumps(EXP) + "\n```")
    assert not sc["valid"] and sc["categories"] == ["format"]
    _, sc = run(EXP, "Here is the result: " + json.dumps(EXP))
    assert not sc["valid"]
    _, sc = run(EXP, {**EXP, "buyer": "X AB"})
    assert not sc["valid"]
    e = dict(EXP)
    del e["vat"]
    _, sc = run(EXP, e)
    assert not sc["valid"]
    _, sc = run(EXP, {**EXP, "net": ["1234.50"]})
    assert not sc["valid"]
    _, sc = run(EXP, "")
    assert sc["nonanswer"] and not sc["passed"]
    _, sc = run(EXP, "Which invoice do you mean?")
    assert sc["nonanswer"]
    parsed = M.parse({"text": "", "refusal": "I can't", "logprobs": None}, LEGACY, {})
    assert M.score(EXP, parsed)["nonanswer"]
    assert M.score(EXP, None)["valid"] is False


def test_parse_never_raises():
    for bad in [None, {}, {"text": None}, {"text": "{"}, {"text": "[1,2]"}, {"text": '{"a":1} x'}]:
        p = M.parse(bad, LEGACY, {})
        assert p["valid"] is False
    assert M.parse([out(EXP)], {"flag_method": "two_run_agreement"}, {})["flags"] == list(M.FIELDS)


# --------------------------------------------------------------------------- flag methods

def tokens_for(text, low_values=()):
    """Tokenise text into small chunks; chunks inside any of low_values get logprob -2, others -0.001."""
    spans = []
    for v in low_values:
        i = text.index(v)
        spans.append((i, i + len(v)))
    toks, i = [], 0
    while i < len(text):
        n = 3
        t = text[i:i + n]
        low = any(a < i + len(t) and i < b for a, b in spans)
        toks.append({"token": t, "logprob": -2.0 if low else -0.001})
        i += len(t)
    return toks


def test_logprob_flags_low_confidence_field():
    text = json.dumps(EXP, ensure_ascii=False, separators=(",", ":"))
    parsed, sc = run(EXP, text, LEGACY, logprobs=tokens_for(text, ["2026-04-03"]))
    assert parsed["flags"] == ["issue_date"]
    assert parsed["field_logprobs"]["issue_date"] < -0.1 and parsed["field_logprobs"]["vendor"] > -0.1
    assert sc["passed"] and sc["secondary"]["flagged"] == 1 and sc["secondary"]["flag_tp"] == 0


def test_logprob_flag_true_positive_and_null_value():
    exp = {**EXP, "due_date": None}
    got = {**EXP, "due_date": None, "net": "1243.50"}
    text = json.dumps(got, indent=1)
    parsed, sc = run(exp, text, LEGACY, logprobs=tokens_for(text, ["1243.50"]))
    assert parsed["flags"] == ["net"] and sc["secondary"]["flag_tp"] == 1 and sc["secondary"]["wrong"] == 1
    assert parsed["field_logprobs"]["due_date"] is not None  # the bare null literal has tokens too


def test_logprob_with_partial_byte_tokens():
    got = {**EXP, "vendor": "Bröd Äpple AB"}
    text = json.dumps(got, ensure_ascii=False, separators=(",", ":"))
    i = text.index("ö")
    toks = [{"token": text[:i], "logprob": -0.001}, {"token": "\\xc3", "logprob": -3.0},
            {"token": "\\xb6", "logprob": -3.0}, {"token": text[i + 1:], "logprob": -0.001}]
    offs = M.token_offsets([t["token"] for t in toks], text)
    assert offs[1] == (i, i + 1) and offs[2] == (i, i + 1) and offs[3][0] == i + 1
    parsed = M.parse(out(text, toks), LEGACY, {})
    assert "vendor" in parsed["flags"]


def test_logprob_threshold_setting():
    text = json.dumps(EXP)
    toks = tokens_for(text, ["SEK"])
    assert M.parse(out(text, toks), {**LEGACY, "flag_threshold": -3.0}, {})["flags"] == []


def test_null_when_unsure_flags_nulls():
    parsed, sc = run(EXP, {**EXP, "vat": None}, {"flag_method": "null_when_unsure"})
    assert parsed["flags"] == ["vat"] and sc["secondary"]["flag_tp"] == 1


def test_confidence_field():
    conf = {f: "high" for f in M.FIELDS}
    conf["total"] = "low"
    parsed, sc = run(EXP, {**EXP, "total": "1543.31", "confidence": conf}, {"flag_method": "confidence_field"})
    assert sc["valid"] and parsed["flags"] == ["total"] and sc["secondary"]["flag_tp"] == 1
    _, sc = run(EXP, {**EXP, "confidence": conf}, {"flag_method": "none"})
    assert not sc["valid"]
    parsed, sc = run(EXP, dict(EXP), {"flag_method": "confidence_field"})
    assert sc["passed"] and parsed["flags"] == []


def test_two_run_agreement():
    s = {"flag_method": "two_run_agreement", "samples": 2}
    parsed, sc = run(EXP, [out(EXP), out({**EXP, "vat": 308.63, "due_date": "2026-03-05"})], s)
    assert parsed["flags"] == ["due_date"] and sc["passed"]
    parsed, _ = run(EXP, [out(EXP), out("oops")], s)
    assert parsed["flags"] == list(M.FIELDS)


def test_aggregate_pools_flags():
    rows = []
    for exp, got, s in [(EXP, {**EXP, "vat": None}, {"flag_method": "null_when_unsure"}),
                        (EXP, {**EXP, "net": "1.00"}, {"flag_method": "none"}),
                        (EXP, "not json", {"flag_method": "none"})]:
        rows.append({"secondary": M.score(exp, M.parse(out(got), s, {}))["secondary"]})
    a = M.aggregate(rows)
    assert a["field_accuracy"] == pytest.approx((7 + 7 + 0) / 24)
    assert a["flag_precision"] == 1.0 and a["flag_recall"] == 0.5 and a["wrong_fields"] == 2


# --------------------------------------------------------------------------- settings, schema, legacy

def test_schema_strict_and_confidence_variant():
    s = M.schema({"flag_method": "logprob"})
    assert s["required"] == M.FIELDS and s["additionalProperties"] is False
    c = M.schema({"flag_method": "confidence_field"})
    assert c["required"] == M.FIELDS + ["confidence"]
    assert c["properties"]["confidence"]["required"] == M.FIELDS
    assert c["properties"]["confidence"]["additionalProperties"] is False


def test_port_and_normalise_settings():
    legacy = CASE.legacy_config["settings"]
    assert legacy["flag_method"] == "logprob" and legacy["logprobs"] is True and legacy["structured_outputs"]
    from harness import requests
    port = requests.mechanical_port(CASE, CASE.legacy_setup(), "gpt-6-luna", "low")
    assert port["settings"]["flag_method"] == "none" and port["settings"]["logprobs"] is False
    assert "samples" not in port["settings"]
    assert M.normalise_settings({"flag_method": "two_run_agreement"})["samples"] == 2
    assert "samples" not in M.normalise_settings({"flag_method": "none", "samples": 2})
    space = M.settings_space()
    assert "logprob" not in space["flag_method"] and set(space["flag_method"]) == set(M.FLAG_METHODS) - {"logprob"}


def test_legacy_request_shape():
    from harness import requests
    item = {"input": "INVOICE ...", "id": "x"}
    model, api, body = requests.build(CASE, CASE.legacy_setup(), item)
    assert api == "chat" and body["logprobs"] is True and body["temperature"] == 0
    assert body["response_format"]["json_schema"]["schema"]["required"] == M.FIELDS


def test_legacy_markers_present():
    assert CASE.check_markers() == []
    assert CASE.check_markers("a plain prompt") != []

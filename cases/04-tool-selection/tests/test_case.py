"""Labeller, scorer and verifier fixtures for case 04 (no API calls)."""
import json
import random
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from harness.cases import Case  # noqa: E402

C = Case("04")
M = C.mod


def mk(slice_, variant="main", seed=1, **want):
    """First plan (by seed) in the slice matching every key=value in want (looked up in plan or plan['args'])."""
    for s in range(seed, seed + 5000):
        p = {**M.plan(random.Random(s), slice_, variant), "slice": slice_, "variant": variant}
        ok = all((p.get(k) if k in p else p["args"].get(k)) == v for k, v in want.items())
        if ok:
            return p
    raise AssertionError(f"no plan for {slice_} {want}")


def out_call(name, args, text=""):
    return {"text": text, "tool_calls": [{"name": name, "arguments": json.dumps(args)}], "logprobs": None,
            "status": "tool_calls", "refusal": None}


def out_text(text):
    return {"text": text, "tool_calls": [], "logprobs": None, "status": "stop", "refusal": None}


def run(plan, output):
    exp = M.label(plan)
    return M.score(exp, M.parse(output, {}, {}))


# ---------------------------------------------------------------- relative dates

REL = {"tomorrow": "2026-11-18", "the day after tomorrow": "2026-11-19", "in three days": "2026-11-20",
       "in a week": "2026-11-24", "in two weeks": "2026-12-01", "on Friday": "2026-11-20", "this Friday": "2026-11-20",
       "on Monday": "2026-11-23", "next Monday": "2026-11-23", "next Tuesday": "2026-11-24",
       "next Friday": "2026-11-27", "yesterday": "2026-11-16", "last Friday": "2026-11-13",
       "a week ago": "2026-11-10", "three days ago": "2026-11-14", "i morgon": "2026-11-18",
       "i övermorgon": "2026-11-19", "nästa tisdag": "2026-11-24", "på fredag": "2026-11-20",
       "i fredags": "2026-11-13", "i går": "2026-11-16", "om tre dagar": "2026-11-20"}


def test_relative_date_table_matches_spec():
    seen = set()
    for lang in ("en", "sv"):
        for s in range(3000):
            rng = random.Random(s)
            for surf, iso in (M.rel_future(rng, lang), M.rel_past(rng, lang)):
                if surf in REL:
                    assert iso == REL[surf], surf
                    seen.add(surf)
    assert seen == set(REL)


def test_relative_dates_label_uses_iso():
    p = mk("relative_dates", tool="create_task")
    exp = M.label(p)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", exp["args"]["due_date"])
    assert exp["tool"] == "create_task"


def test_relative_date_wrong_resolution_category():
    p = mk("relative_dates", tool="create_event")
    args = dict(p["args"])
    args["date"] = "2026-11-17"
    r = run(p, out_call("create_event", args))
    assert not r["passed"] and "date_resolution" in r["categories"]


# ---------------------------------------------------------------- plain

def test_plain_event_passes_with_normalised_forms():
    p = mk("plain", tool="create_event")
    a = dict(p["args"])
    a["title"] = '"' + a["title"].upper() + '."'
    a["start_time"] = a["start_time"] + ":00"
    a["date"] = a["date"] + "T00:00:00"
    if "attendees" in a:
        a["attendees"] = [n.lower() for n in reversed(a["attendees"])]
    if "location" in a:
        a["location"] = a["location"] + ", Somewhere"
    r = run(p, out_call("create_event", a))
    assert r["passed"], r["diff"]
    assert r["secondary"]["arg_accuracy"] == 1.0


def test_plain_currency_number_and_code_normalisation():
    p = mk("plain", tool="convert_currency")
    a = dict(p["args"])
    a["amount"] = f"{a['amount']:,}"
    a["from_currency"] = a["from_currency"].lower()
    assert run(p, out_call("convert_currency", a))["passed"]
    a["amount"] = p["args"]["amount"] + 1
    r = run(p, out_call("convert_currency", a))
    assert not r["passed"] and "wrong_value" in r["categories"]


def test_company_suffix_and_name_diacritics():
    exp = {"tool": "find_contact", "args": {"name": "Lisa Krumoraström", "company": "Velmora"},
           "types": M.TYPES["find_contact"], "defaults": {}}
    r = M.score(exp, M.parse(out_call("find_contact", {"name": "lisa krumorastrom", "company": "Velmora AB"}), {}, {}))
    assert r["passed"], r["diff"]


def test_missing_required_arg():
    p = mk("plain", tool="send_email")
    a = {k: v for k, v in p["args"].items() if k != "subject"}
    r = run(p, out_call("send_email", a))
    assert not r["passed"] and "missing_arg" in r["categories"]


def test_free_body_not_scored():
    p = mk("optional_omitted", tool="send_email")
    a = dict(p["args"], body="Anything at all, with 42 numbers.")
    assert run(p, out_call("send_email", a))["passed"]


# ---------------------------------------------------------------- optional_omitted

def test_optional_omitted_plan_has_only_required():
    for t in M.TOOL_NAMES:
        p = mk("optional_omitted", tool=t)
        assert set(p["args"]) == set(M.REQUIRED[t]), t


def test_invented_optional_fails_but_default_tolerated():
    p = mk("optional_omitted", tool="get_weather")
    r = run(p, out_call("get_weather", dict(p["args"], units="celsius")))
    assert r["passed"]
    r = run(p, out_call("get_weather", dict(p["args"], date="2026-11-17")))
    assert not r["passed"] and "extra_arg" in r["categories"]
    r = run(p, out_call("get_weather", dict(p["args"], date=None, units="")))
    assert r["passed"]
    p = mk("optional_omitted", tool="create_event")
    r = run(p, out_call("create_event", dict(p["args"], duration_minutes=60)))
    assert not r["passed"] and "extra_arg" in r["categories"]


# ---------------------------------------------------------------- lookalike_tools

def test_lookalike_task_vs_event():
    p = mk("lookalike_tools", kind="task_event_wording")
    assert M.label(p)["tool"] == "create_task"
    r = run(p, out_call("create_event", {"title": p["args"]["title"], "date": p["args"]["due_date"],
                                         "start_time": "09:00"}))
    assert not r["passed"] and r["categories"] == ["wrong_tool"] and r["valid"]
    p = mk("lookalike_tools", kind="event_task_wording")
    assert M.label(p)["tool"] == "create_event" and "start_time" in p["args"]


def test_lookalike_future_call_is_event_with_attendee():
    p = mk("lookalike_tools", kind="future_call")
    exp = M.label(p)
    assert exp["tool"] == "create_event" and len(exp["args"]["attendees"]) == 1
    r = run(p, out_call("create_event", dict(p["args"], attendees=p["args"]["attendees"][0])))
    assert not r["passed"]  # names must be an array
    p = mk("lookalike_tools", kind="past_call")
    assert M.label(p)["tool"] == "log_call"


# ---------------------------------------------------------------- multi_candidate

def test_correction_last_value_wins():
    p = mk("multi_candidate", corrected_arg="start_time")
    old, new = p["corrections"][0]
    assert new in p["must"] and old in p["must"]
    rest = [m for m in p["must"] if m not in (old, new)]
    filler = "Book " + ", ".join(f'"{m}"' if m in p["quoted"] else m for m in rest)
    ok, why = M.verify(p, f"{filler}, at {old}, no wait, {new}.")
    assert ok, why
    assert not M.verify(p, f"{filler}, at {new}, no wait, {old}.")[0]


def test_webmail_rule_picks_company_domain():
    p = mk("multi_candidate", corrected_arg="webmail")
    exp = M.label(p)
    assert exp["args"]["to"].split("@")[1] not in M.WEBMAIL
    r = run(p, out_call("send_email", dict(p["args"], to=p["webmail"])))
    assert not r["passed"] and "wrong_value" in r["categories"]


# ---------------------------------------------------------------- no_tool

def test_no_tool_text_passes_and_call_is_false_call():
    p = mk("no_tool")
    assert M.label(p)["tool"] is None
    r = run(p, out_text("EBITDA stands for earnings before interest, taxes, depreciation and amortisation."))
    assert r["passed"] and r["secondary"]["false_call"] == 0
    r = run(p, out_call("search_docs", {"query": "EBITDA"}))
    assert not r["passed"] and r["categories"] == ["false_call"] and r["secondary"]["false_call"] == 1


def test_missed_call_and_nonanswer():
    p = mk("plain", tool="find_contact")
    r = run(p, out_text("Which company does she work for?"))
    assert not r["passed"] and r["nonanswer"] and r["categories"] == ["nonanswer"]
    r = run(p, out_text("Here are the details you asked for."))
    assert not r["passed"] and not r["nonanswer"] and r["categories"] == ["missed_call"]


# ---------------------------------------------------------------- output contract

def test_multiple_calls_and_bad_json():
    p = mk("plain", tool="search_docs")
    two = {"text": "", "tool_calls": [{"name": "search_docs", "arguments": json.dumps(p["args"])},
                                      {"name": "find_contact", "arguments": "{}"}]}
    r = run(p, two)
    assert not r["passed"] and not r["valid"] and r["categories"] == ["multiple_calls"]
    bad = {"text": "", "tool_calls": [{"name": "search_docs", "arguments": "{query: oops"}]}
    r = run(p, bad)
    assert not r["passed"] and not r["valid"] and r["categories"] == ["bad_arguments"]


def test_parse_never_raises():
    for junk in (None, {}, [], "x", {"tool_calls": [{"name": None, "arguments": None}]}, [{"text": "a"}],
                 {"tool_calls": [{"name": "x", "arguments": "[1,2]"}]}):
        parsed = M.parse(junk, {}, {})
        M.score({"tool": "search_docs", "args": {"query": "a"}, "types": M.TYPES["search_docs"], "defaults": {}},
                parsed)


# ---------------------------------------------------------------- shift

def test_shift_renamed_tools_and_swedish():
    p = mk("plain", "shift", tool="create_task")
    exp = M.label(p)
    assert exp["tool"] == "add_todo" and p["lang"] == "sv"
    item = {"input": "x", **M.item_extras(p)}
    names = [t["name"] for t in M.tools(item, {})]
    assert "add_todo" in names and "query_knowledge_base" in names and "create_task" not in names
    assert [t["name"] for t in M.tools({"input": "x"}, {})] == M.TOOL_NAMES
    assert run(p, out_call("add_todo", p["args"]))["passed"]
    assert not run(p, out_call("create_task", p["args"]))["passed"]


def test_shift_uses_unseen_companies():
    shift_names = {c["name"] for c in M.entities.companies("shift")}
    p = mk("plain", "shift", tool="find_contact", seed=1)
    for s in range(1, 400):
        p = {**M.plan(random.Random(s), "plain", "shift"), "slice": "plain", "variant": "shift"}
        for c in p["companies"]:
            assert c in shift_names


# ---------------------------------------------------------------- verify

def test_verify_rejects_unplanned_values():
    p = mk("optional_omitted", tool="search_docs")
    q = p["args"]["query"]
    assert M.verify(p, f'Could you search our docs for "{q}"?')[0]
    assert not M.verify(p, f'Could you search our docs for "{q}" and show 5 results?')[0]
    assert not M.verify(p, f'Could you search our docs for {q} please?')[0]  # not quoted
    assert not M.verify(p, f'Search "{q}" before tomorrow.')[0]
    assert not M.verify(p, f'Search "{q}" and send it to Anna.')[0]


def test_label_deterministic_and_serialisable():
    for sl in M.slices():
        for v in ("main", "shift"):
            p = {**M.plan(random.Random(42), sl, v), "slice": sl, "variant": v}
            assert json.dumps(M.label(p)) == json.dumps(M.label(json.loads(json.dumps(p))))


def test_aggregate():
    rows = [{"secondary": {"tool_correct": 1.0, "missed_call": 0.0, "arg_accuracy": 1.0}},
            {"secondary": {"tool_correct": 0.0, "missed_call": 1.0, "arg_accuracy": 0.0}},
            {"secondary": {"tool_correct": 0.0, "false_call": 1.0}},
            {"secondary": {"tool_correct": 1.0, "false_call": 0.0}}]
    a = M.aggregate(rows)
    assert a["tool_name_accuracy"] == 0.5 and a["false_call_rate"] == 0.5 and a["missed_call_rate"] == 0.5
    assert a["argument_accuracy"] == 1.0


def test_answer_strings_exclude_tool_names_and_dates():
    p = mk("plain", tool="create_event")
    s = M.answer_strings(M.label(p))
    assert "create_event" not in s and p["args"]["date"] not in s


# ---------------------------------------------------------------- legacy

def test_legacy_markers_present():
    assert C.check_markers() == []
    assert "Today is Tuesday, 17 November 2026" in C.legacy_prompt
    cfg = C.legacy_config
    assert cfg["api"] == "chat" and cfg["effort"] == "none" and cfg["settings"]["temperature"] == 0

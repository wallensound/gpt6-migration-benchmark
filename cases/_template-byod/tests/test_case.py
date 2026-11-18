"""Add fixtures for your scorer here: pairs of (expected, model output, should pass?)."""
from pathlib import Path

from harness.cases import Case

CASE = Case(str(Path(__file__).resolve().parents[1]))


def check(expected, text, passed):
    assert CASE.score(expected, CASE.parse({"text": text, "tool_calls": []}, {}, {}))["passed"] is passed


def test_text_exact():
    check("billing", "billing", True)
    check("billing", " billing\n", True)
    check("billing", "Billing", False)
    check("billing", "Is this about billing?", False)


def test_json_equality():
    check({"total": "12.50"}, '{"total": "12.50"}', True)
    check({"total": "12.50"}, '```json\n{"total": "12.50"}\n```', False)
    check(["Acme"], '["Acme"]', True)

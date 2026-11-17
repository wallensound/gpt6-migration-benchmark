import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = ROOT / "tests" / "fixtures"


@pytest.fixture
def recorded():
    return {p.stem: json.loads(p.read_text()) for p in FIX.glob("*.json")}


@pytest.fixture
def stub_case():
    from harness.cases import Case
    return Case(str(ROOT / "tests" / "stub_case"))


class FakeAPIError(Exception):
    def __init__(self, status, code, msg="err", retry_after=None):
        super().__init__(msg)
        self.status_code = status
        self.body = {"code": code, "message": msg}
        headers = {"retry-after": str(retry_after)} if retry_after else {}
        self.response = type("R", (), {"headers": headers})()

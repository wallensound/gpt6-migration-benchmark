import asyncio

import pytest

from harness import runner as R
from tests.conftest import FakeAPIError


def make(tmp_path, transport, phase="P1"):
    return R.Runner(phase=phase, transport=transport, state_path=tmp_path / "s.sqlite")


def test_normalise_recorded(recorded):
    out = R.normalise("chat", recorded["chat"]["raw"])
    assert out["text"] and out["logprobs"] and out["logprobs"][0]["token"]
    r = R.normalise("responses", recorded["responses_text"]["raw"])
    assert r["text"].strip()
    j = R.normalise("responses", recorded["responses_json"]["raw"])
    assert '"word"' in j["text"]


def test_usage_and_cost(recorded):
    tok = R.usage_tokens("responses", recorded["responses_text"]["raw"])
    assert tok["tokens_out"] >= tok["tokens_reasoning"] > 0
    z = {"tokens_in": 0, "tokens_cached": 0, "tokens_cache_write": 0, "tokens_out": 0, "tokens_reasoning": 0}
    assert R.cost_usd("gpt-6.2-astra", {**z, "tokens_in": 10**6, "tokens_out": 10**6}) == pytest.approx(48.0)
    assert R.cost_usd("gpt-6.2-astra", {**z, "tokens_in": 10**6, "tokens_cached": 10**6}) == pytest.approx(0.8)
    assert R.cost_usd("gpt-6.2-astra", {**z, "tokens_in": 10**6, "tokens_cache_write": 10**6}) == pytest.approx(10.0)


def test_cache_hit_costs_nothing(tmp_path, recorded):
    calls = []

    async def t(p, m, api, body):
        calls.append(1)
        return recorded["responses_text"]["raw"]
    r = make(tmp_path, t)
    a = asyncio.run(r.call("gpt-6-luna", "responses", {"input": "x"}))
    b = asyncio.run(r.call("gpt-6-luna", "responses", {"input": "x"}))
    assert len(calls) == 1 and not a["from_cache"] and b["from_cache"]
    assert r.calls_made == 1 and r.calls_cached == 1
    c = asyncio.run(r.call("gpt-6-luna", "responses", {"input": "x"}, repeat=1))
    assert len(calls) == 2 and not c["from_cache"]  # repeats are distinct calls


def test_retry_on_overload_then_success(tmp_path, recorded, monkeypatch):
    seq = [FakeAPIError(503, "server_is_overloaded", retry_after=0.01), FakeAPIError(429, "slow_down"),
           recorded["responses_text"]["raw"]]
    sleeps = []

    async def fake_sleep(d):
        sleeps.append(d)
    monkeypatch.setattr(R.asyncio, "sleep", fake_sleep)

    async def t(p, m, api, body):
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    r = make(tmp_path, t)
    out = asyncio.run(r.call("gpt-6-luna", "responses", {"input": "y"}))
    assert out["raw"] is not None and len(sleeps) == 2
    assert sleeps[0] < 0.1  # Retry-After honoured
    assert r._limiters["gpt-6-luna"].limit < 20  # slowed down after slow_down


def test_billing_error_stops(tmp_path):
    async def t(p, m, api, body):
        raise FakeAPIError(429, "insufficient_quota", "You exceeded your current quota")
    with pytest.raises(R.BillingError):
        asyncio.run(make(tmp_path, t).call("gpt-6-luna", "responses", {"input": "z"}))


def test_bad_request_is_final_and_cached(tmp_path):
    n = []

    async def t(p, m, api, body):
        n.append(1)
        raise FakeAPIError(400, "unsupported_parameter", "temperature not supported")
    r = make(tmp_path, t)
    a = asyncio.run(r.call("gpt-6-luna", "responses", {"input": "q"}))
    b = asyncio.run(r.call("gpt-6-luna", "responses", {"input": "q"}))
    assert a["raw"] is None and a["error_code"] == "unsupported_parameter" and b["from_cache"] and len(n) == 1


def test_budget_guard_refuses(tmp_path):
    async def t(p, m, api, body):
        raise AssertionError("must not be called")
    r = make(tmp_path, t, phase="P0")  # cap $2
    jobs = [("gpt-6.2-astra", "responses", {"input": str(i)}, 0) for i in range(200)]  # ~$0.024 each
    with pytest.raises(R.BudgetExceeded):
        r.guard(jobs, "test")
    assert r.guard(jobs[:10], "ok") < 2


def test_budget_stops_mid_run(tmp_path, recorded):
    async def t(p, m, api, body):
        return recorded["responses_text"]["raw"]
    r = make(tmp_path, t, phase="P0")
    r._spent_phase = 2.0  # at the cap
    with pytest.raises(R.BudgetExceeded):
        asyncio.run(r.call("gpt-6-luna", "responses", {"input": "new"}))


def test_classify():
    assert R.classify(429, "slow_down", "") == "rate_limit"
    assert R.classify(429, "insufficient_quota", "") == "billing"
    assert R.classify(503, "server_is_overloaded", "") == "overloaded"
    assert R.classify(None, None, "timeout") == "transient"
    assert R.classify(400, "invalid", "") == "final"

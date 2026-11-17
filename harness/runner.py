"""The one path to the API.

Every model call goes through `Runner.call`, which gives:
- a response cache keyed by model, API, full request body and repeat index (reruns cost nothing),
- per-model adaptive concurrency (start at the configured cap, halve on `slow_down`),
- retries with exponential backoff and jitter, honouring `Retry-After`,
- branching on `error.code`: billing errors stop the phase, 400-class errors are final,
- cost from token usage and the price table (cached, cache-write and reasoning tokens counted),
- a budget guard that refuses to start work whose estimate would exceed the phase cap,
- raw-first storage: the raw response is written to the cache before anything parses it.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from . import config

ASSUMED_TOKENS_IN = 1500
ASSUMED_TOKENS_OUT = 300
MAX_ATTEMPTS = 8
BILLING_CODES = {"insufficient_quota", "billing_hard_limit_reached", "billing_not_active",
                 "account_deactivated", "quota_exceeded"}


class BudgetExceeded(RuntimeError):
    pass


class BillingError(RuntimeError):
    pass


class AuthError(RuntimeError):
    pass


# --------------------------------------------------------------------------- state

def connect_state(path=None) -> sqlite3.Connection:
    path = path or config.STATE_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=60, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=60000")
    con.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, created REAL)")
    con.execute("""CREATE TABLE IF NOT EXISTS ledger (ts REAL, phase TEXT, model TEXT, purpose TEXT,
                   cost REAL, tokens_in INTEGER, tokens_out INTEGER, pid INTEGER)""")
    return con


def cache_key(model_id: str, api: str, body: dict, repeat: int = 0) -> str:
    blob = json.dumps({"m": model_id, "api": api, "body": body, "r": repeat}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- pricing

def usage_tokens(api: str, raw: dict | None) -> dict:
    u = (raw or {}).get("usage") or {}
    if api == "chat":
        tin = u.get("prompt_tokens") or 0
        d = u.get("prompt_tokens_details") or {}
        tout = u.get("completion_tokens") or 0
        r = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    else:
        tin = u.get("input_tokens") or 0
        d = u.get("input_tokens_details") or {}
        tout = u.get("output_tokens") or 0
        r = (u.get("output_tokens_details") or {}).get("reasoning_tokens") or 0
    return {"tokens_in": int(tin), "tokens_cached": int(d.get("cached_tokens") or 0),
            "tokens_cache_write": int(d.get("cache_write_tokens") or 0),
            "tokens_out": int(tout), "tokens_reasoning": int(r)}


def cost_usd(model: str, tok: dict) -> float:
    m = config.model_cfg(model)
    p = config.models()["pricing"]
    pin, pout = m["price_in"] / 1e6, m["price_out"] / 1e6
    uncached = max(0, tok["tokens_in"] - tok["tokens_cached"] - tok["tokens_cache_write"])
    return (uncached * pin + tok["tokens_cached"] * pin * p["cached_input_multiplier"]
            + tok["tokens_cache_write"] * pin * p["cache_write_multiplier"]
            + tok["tokens_out"] * pout)  # output tokens include reasoning tokens


# --------------------------------------------------------------------------- concurrency

class AdaptiveLimiter:
    def __init__(self, limit: int):
        self.limit = max(1, int(limit))
        self.max_limit = self.limit
        self.active = 0
        self.cond = asyncio.Condition()
        self.successes = 0

    async def acquire(self):
        async with self.cond:
            while self.active >= self.limit:
                await self.cond.wait()
            self.active += 1

    async def release(self, ok: bool = True):
        async with self.cond:
            self.active -= 1
            if ok:
                self.successes += 1
                if self.successes % 50 == 0 and self.limit < self.max_limit:
                    self.limit += 1
            self.cond.notify_all()

    def slow_down(self):
        self.limit = max(2, self.limit // 2)
        self.successes = 0


# --------------------------------------------------------------------------- errors

def _error_info(exc: Exception) -> tuple[int | None, str | None, str, float | None]:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    code = None
    msg = str(exc)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            code = err.get("code") or err.get("type")
            msg = err.get("message") or msg
    retry_after = None
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            ra = resp.headers.get("retry-after")
            if ra:
                retry_after = float(ra)
        except Exception:
            retry_after = None
    return status, (str(code) if code is not None else None), msg[:500], retry_after


def classify(status: int | None, code: str | None, msg: str) -> str:
    """Return one of: billing, auth, rate_limit, overloaded, transient, final."""
    low = (msg or "").lower()
    if status == 429:
        if code in BILLING_CODES or "billing" in low or "exceeded your current quota" in low:
            return "billing"
        return "rate_limit"
    if status in (401, 403):
        return "auth"
    if status in (500, 502, 503, 504, 529) or code == "server_is_overloaded":
        return "overloaded"
    if status is None:
        return "transient"  # timeouts, connection errors
    if status == 408 or status == 409:
        return "transient"
    return "final"


# --------------------------------------------------------------------------- runner

Transport = Callable[[str, str, str, dict], Awaitable[dict]]


@dataclass
class Runner:
    phase: str
    purpose: str = ""
    transport: Transport | None = None  # tests inject a fake transport
    state_path: Any = None
    _con: sqlite3.Connection | None = field(default=None, init=False, repr=False)
    _limiters: dict = field(default_factory=dict, init=False, repr=False)
    _clients: dict = field(default_factory=dict, init=False, repr=False)
    _spent_phase: float = field(default=0.0, init=False)
    _spent_total: float = field(default=0.0, init=False)
    _calls_since_refresh: int = field(default=0, init=False)
    calls_made: int = field(default=0, init=False)
    calls_cached: int = field(default=0, init=False)

    def __post_init__(self):
        config.load_dotenv()
        self._con = connect_state(self.state_path)
        self.refresh_spend()

    # ---- budget
    def refresh_spend(self):
        cur = self._con.execute("SELECT COALESCE(SUM(cost),0) FROM ledger WHERE phase=?", (self.phase,))
        self._spent_phase = cur.fetchone()[0]
        self._spent_total = self._con.execute("SELECT COALESCE(SUM(cost),0) FROM ledger").fetchone()[0]
        self._calls_since_refresh = 0

    @property
    def cap(self) -> float:
        return float(config.budget()["phases"][self.phase])

    @property
    def spent(self) -> float:
        return self._spent_phase

    def mean_cost(self, model: str) -> float:
        row = self._con.execute(
            "SELECT AVG(cost), COUNT(*) FROM (SELECT cost FROM ledger WHERE model=? ORDER BY ts DESC LIMIT 2000)",
            (model,)).fetchone()
        if row and row[1] and row[1] >= 20:
            return float(row[0])
        return cost_usd(model, {"tokens_in": ASSUMED_TOKENS_IN, "tokens_cached": 0, "tokens_cache_write": 0,
                                "tokens_out": ASSUMED_TOKENS_OUT, "tokens_reasoning": 0})

    def is_cached(self, model: str, api: str, body: dict, repeat: int = 0) -> bool:
        key = cache_key(config.model_cfg(model)["model_id"], api, body, repeat)
        return self._con.execute("SELECT 1 FROM cache WHERE key=?", (key,)).fetchone() is not None

    def estimate(self, jobs: list[tuple[str, str, dict, int]]) -> float:
        total = 0.0
        means: dict[str, float] = {}
        for model, api, body, repeat in jobs:
            if self.is_cached(model, api, body, repeat):
                continue
            if model not in means:
                means[model] = self.mean_cost(model)
            total += means[model]
        return total

    def guard(self, jobs, label: str = "") -> float:
        """Refuse to start if the estimate would exceed the phase cap or the total limit."""
        self.refresh_spend()
        est = self.estimate(jobs)
        b = config.budget()
        if self._spent_phase + est > self.cap:
            raise BudgetExceeded(f"{label}: estimate ${est:.2f} + spent ${self._spent_phase:.2f} "
                                 f"exceeds {self.phase} cap ${self.cap:.2f}")
        if self._spent_total + est > float(b["total_limit"]):
            raise BudgetExceeded(f"{label}: estimate ${est:.2f} would exceed the total limit")
        return est

    # ---- clients
    def _client(self, provider: str):
        if provider in self._clients:
            return self._clients[provider]
        from openai import AsyncOpenAI
        p = config.models()["providers"][provider]
        key = os.environ.get(p["key_env"])
        if not key:
            raise AuthError(f"environment variable {p['key_env']} is not set")
        if p["auth"] == "api-key":
            c = AsyncOpenAI(base_url=p["base_url"], api_key="unused", default_headers={"api-key": key},
                            max_retries=0, timeout=600)
        else:
            c = AsyncOpenAI(base_url=p["base_url"], api_key=key, max_retries=0, timeout=600)
        self._clients[provider] = c
        return c

    async def _send(self, provider: str, model_id: str, api: str, body: dict) -> dict:
        if self.transport is not None:
            return await self.transport(provider, model_id, api, body)
        client = self._client(provider)
        path = "/chat/completions" if api == "chat" else "/responses"
        import httpx2
        resp = await client.post(path, body={**body, "model": model_id}, cast_to=httpx2.Response)
        return resp.json()

    def _limiter(self, model: str) -> AdaptiveLimiter:
        if model not in self._limiters:
            self._limiters[model] = AdaptiveLimiter(config.model_cfg(model).get("concurrency", 20))
        return self._limiters[model]

    # ---- the call
    async def call(self, model: str, api: str, body: dict, repeat: int = 0, purpose: str | None = None) -> dict:
        m = config.model_cfg(model)
        model_id = m["model_id"]
        key = cache_key(model_id, api, body, repeat)
        row = self._con.execute("SELECT value FROM cache WHERE key=?", (key,)).fetchone()
        if row:
            self.calls_cached += 1
            out = json.loads(row[0])
            out["from_cache"] = True
            return out

        stop_time_check()
        if self._spent_phase >= self.cap:
            raise BudgetExceeded(f"{self.phase} cap ${self.cap:.2f} reached (spent ${self._spent_phase:.2f})")

        lim = self._limiter(model)
        attempt = 0
        last = {"status": None, "code": None, "msg": ""}
        while attempt < MAX_ATTEMPTS:
            attempt += 1
            await lim.acquire()
            t0 = time.perf_counter()
            exc: Exception | None = None
            raw = None
            try:
                raw = await self._send(m["provider"], model_id, api, body)
            except Exception as e:  # noqa: BLE001 - we branch on the error code below
                exc = e
            finally:
                await lim.release(ok=exc is None)
            latency = (time.perf_counter() - t0) * 1000
            if exc is not None:
                status, code, msg, retry_after = _error_info(exc)
                kind = classify(status, code, msg)
                last = {"status": status, "code": code or type(exc).__name__, "msg": msg}
                if kind == "billing":
                    raise BillingError(f"{model}: {code} {msg}")
                if kind == "auth":
                    raise AuthError(f"{model}: {status} {code} {msg}")
                if kind == "final":
                    out = self._result(model, model_id, api, None, latency, status, code or "bad_request", msg)
                    self._store(key, out)  # deterministic rejections are cached
                    return out
                if kind == "rate_limit":
                    lim.slow_down()
                delay = retry_after if retry_after else min(60.0, 2.0 * (2 ** (attempt - 1)))
                await asyncio.sleep(delay * (0.75 + 0.5 * random.random()))
                continue
            err = raw.get("error") if isinstance(raw, dict) else None
            code = (err or {}).get("code") if isinstance(err, dict) else None
            out = self._result(model, model_id, api, raw, latency, None, code, (err or {}).get("message") if isinstance(err, dict) else None)
            self._store(key, out)
            self._charge(model, out, purpose)
            return out
        return self._result(model, model_id, api, None, 0.0, last["status"], "retries_exhausted:" + str(last["code"]), last["msg"])

    def _result(self, model, model_id, api, raw, latency, status, code, msg) -> dict:
        tok = usage_tokens(api, raw)
        return {"model": model, "model_id": model_id, "api": api, "raw": raw, "latency_ms": round(latency, 1),
                "http_status": status, "error_code": code, "error_message": msg, **tok,
                "cost_usd": cost_usd(model, tok) if raw else 0.0, "from_cache": False,
                "called_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    def _store(self, key: str, out: dict):
        self._con.execute("INSERT OR REPLACE INTO cache (key, value, created) VALUES (?,?,?)",
                          (key, json.dumps(out, ensure_ascii=False), time.time()))

    def _charge(self, model: str, out: dict, purpose: str | None):
        self.calls_made += 1
        c = out["cost_usd"]
        self._con.execute("INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?)",
                          (time.time(), self.phase, model, purpose or self.purpose, c, out["tokens_in"],
                           out["tokens_out"], os.getpid()))
        self._spent_phase += c
        self._spent_total += c
        self._calls_since_refresh += 1
        if self._calls_since_refresh >= 100:
            self.refresh_spend()


def stop_time_check():
    st = config.budget().get("stop_time")
    if not st:
        return
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Europe/Stockholm"))
    hh, mm = map(int, st.split(":"))
    stop = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now >= stop and (now - stop).total_seconds() < 6 * 3600:
        raise BudgetExceeded(f"stop time {st} reached")


# --------------------------------------------------------------------------- normalised output

def normalise(api: str, raw: dict | None) -> dict:
    """Turn a raw Chat Completions or Responses payload into one shape the cases parse."""
    out = {"text": "", "tool_calls": [], "logprobs": None, "status": None, "refusal": None}
    if not raw:
        out["status"] = "error"
        return out
    if api == "chat":
        ch = (raw.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        out["text"] = msg.get("content") or ""
        out["refusal"] = msg.get("refusal")
        out["status"] = ch.get("finish_reason")
        for tc in msg.get("tool_calls") or []:
            f = tc.get("function") or {}
            out["tool_calls"].append({"name": f.get("name"), "arguments": f.get("arguments") or "{}"})
        lp = (ch.get("logprobs") or {}).get("content") if ch.get("logprobs") else None
        if lp:
            out["logprobs"] = [{"token": t.get("token"), "logprob": t.get("logprob")} for t in lp]
    else:
        texts, lps = [], []
        for item in raw.get("output") or []:
            t = item.get("type")
            if t == "message":
                for part in item.get("content") or []:
                    if part.get("type") == "output_text":
                        texts.append(part.get("text") or "")
                        for l in part.get("logprobs") or []:
                            lps.append({"token": l.get("token"), "logprob": l.get("logprob")})
                    elif part.get("type") == "refusal":
                        out["refusal"] = part.get("refusal")
            elif t == "function_call":
                out["tool_calls"].append({"name": item.get("name"), "arguments": item.get("arguments") or "{}"})
        out["text"] = "".join(texts)
        out["logprobs"] = lps or None
        out["status"] = raw.get("status")
        if raw.get("incomplete_details"):
            out["status"] = "incomplete:" + str((raw.get("incomplete_details") or {}).get("reason"))
    return out

"""Turn (case, setup, item) into a Chat Completions or Responses request body.

A *setup* is everything that defines how a prompt is run:
    {"model": "gpt-6-luna", "api": "responses", "effort": "low", "prompt": "...", "settings": {...}}
Settings keys understood here: temperature, logprobs, top_logprobs, max_output_tokens,
structured_outputs, verbosity, samples. Cases may add their own keys (they are ignored here).
The stable prompt always goes first so provider-side prompt caching can apply.
"""
from __future__ import annotations

import copy

from . import config


def build(case, setup: dict, item: dict) -> tuple[str, str, dict]:
    s = setup.get("settings") or {}
    api = setup["api"]
    effort = setup.get("effort")
    user = case.user_message(item, s)
    tools = case.tools(item, s)
    schema = case.schema(s) if s.get("structured_outputs") else None
    if api == "chat":
        body: dict = {"messages": [{"role": "system", "content": setup["prompt"]},
                                   {"role": "user", "content": user}]}
        if effort:
            body["reasoning_effort"] = effort
        if s.get("temperature") is not None:
            body["temperature"] = s["temperature"]
        if s.get("logprobs"):
            body["logprobs"] = True
            if s.get("top_logprobs"):
                body["top_logprobs"] = s["top_logprobs"]
        if s.get("max_output_tokens"):
            body["max_completion_tokens"] = s["max_output_tokens"]
        if schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": case.schema_name(), "strict": True, "schema": schema}}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
            body["tool_choice"] = "auto"
    elif api == "responses":
        body = {"input": [{"role": "developer", "content": setup["prompt"]},
                          {"role": "user", "content": user}]}
        if effort:
            body["reasoning"] = {"effort": effort}
        text: dict = {}
        if schema:
            text["format"] = {"type": "json_schema", "name": case.schema_name(), "schema": schema, "strict": True}
        if s.get("verbosity"):
            text["verbosity"] = s["verbosity"]
        if text:
            body["text"] = text
        if s.get("temperature") is not None:
            body["temperature"] = s["temperature"]
        if s.get("max_output_tokens"):
            body["max_output_tokens"] = s["max_output_tokens"]
        if s.get("logprobs"):
            body["include"] = ["message.output_text.logprobs"]
            body["top_logprobs"] = s.get("top_logprobs") or 1
        if tools:
            body["tools"] = [{"type": "function", **t, "strict": False} for t in tools]
            body["tool_choice"] = "auto"
        m = config.model_cfg(setup["model"])
        if (m.get("probed") or {}).get("prompt_cache_options"):
            body["prompt_cache_options"] = {"ttl": "30m"}
        if m.get("tier") == "flex" and (m.get("probed") or {}).get("service_tier_flex"):
            body["service_tier"] = "flex"
    else:
        raise ValueError(f"unknown api {api}")
    return setup["model"], api, body


def mechanical_port(case, legacy: dict, target: str, effort: str) -> dict:
    """Only the changes the API forces: Responses API, no temperature or logprobs, schema to text.format.

    A tight output-token cap is kept only at effort `none`; with reasoning on, reasoning tokens count
    against `max_output_tokens`, so a legacy 5-token cap would guarantee empty output (Decision D7).
    """
    s = copy.deepcopy(legacy.get("settings") or {})
    s["temperature"] = None
    s["logprobs"] = False
    s.pop("top_logprobs", None)
    if effort != "none":
        s["max_output_tokens"] = None
    s = case.port_settings(s)
    return {"model": target, "api": "responses", "effort": effort, "prompt": legacy["prompt"], "settings": s}


def literal_swap(legacy: dict, target: str, effort: str) -> dict:
    """The legacy request with only the model string (and, for GPT-6, the endpoint shape) swapped.

    Used once per sweep setting to record which legacy parameters the target rejects.
    """
    return {"model": target, "api": "responses", "effort": effort, "prompt": legacy["prompt"],
            "settings": copy.deepcopy(legacy.get("settings") or {})}

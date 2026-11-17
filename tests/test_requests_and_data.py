from harness import generate as G
from harness import requests as Q


def test_chat_and_responses_bodies(stub_case):
    legacy = stub_case.legacy_setup()
    item = {"id": "x", "input": "A blue kite.", "expected": "blue", "slice": "plain", "split": "dev"}
    m, api, body = Q.build(stub_case, legacy, item)
    assert api == "chat" and body["temperature"] == 0 and body["max_completion_tokens"] == 5
    assert body["messages"][0]["role"] == "system" and body["reasoning_effort"] == "none"
    port = Q.mechanical_port(stub_case, legacy, "gpt-6-luna", "low")
    m, api, body = Q.build(stub_case, port, item)
    assert api == "responses" and "temperature" not in body and "max_output_tokens" not in body
    assert body["input"][0]["role"] == "developer" and body["reasoning"] == {"effort": "low"}
    port_none = Q.mechanical_port(stub_case, legacy, "gpt-6-luna", "none")
    assert Q.build(stub_case, port_none, item)[2]["max_output_tokens"] == 5


def test_dedupe_and_split():
    items = [{"input": f"sentence number {i} about a thing", "slice": "ab"[i % 2]} for i in range(100)]
    items.append({"input": items[0]["input"], "slice": "a"})
    items.append({"input": items[1]["input"] + "!", "slice": "b"})
    kept, ex, near = G.dedupe(items, 0.8)
    assert ex == 1 and near >= 1
    parts = G.stratified_split(kept, {"test": 30, "dev": 20, "train": 10}, seed=1)
    assert [len(parts[s]) for s in ("test", "dev", "train")] == [30, 20, 10]
    ids = [id(x) for p in parts.values() for x in p]
    assert len(ids) == len(set(ids))
    assert abs(sum(x["slice"] == "a" for x in parts["test"]) - 15) <= 2


def test_leak_hashes():
    assert len(G.ngram_hashes("one two three four five six seven")) == 2
    assert G.phrase_hash("Velmora AB") in G.all_phrase_hashes("the firm velmora ab said")

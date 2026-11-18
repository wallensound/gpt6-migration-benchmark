import json, sys
s = json.load(open(f"runs/P4/{sys.argv[1]}-sweep/sweep.json"))
for r in s["rows"]:
    print(f"{r['setting']:40s} {r['primary']:.3f} val {r['validity']:.2f} na {r['nonanswer_rate']:.2f} err {r['error_rate']:.2f} $/item {r['cost_per_item']:.6f} p50 {r['latency_p50_s']:.1f}s out {r['tokens_out_mean']:.0f} reas {r['tokens_reasoning_mean']:.0f} {dict(list(r['failure_categories'].items())[:3])}")
print(json.dumps({k: v["effort"] for k, v in s["effort_choice"].items()}))
print(sorted({v["error"][:70] for v in s["literal_swap"].values() if not v["accepted"]}))

"""`make status`: spend so far per phase, phases done, runs in progress."""
from __future__ import annotations

import json

from . import config
from .runner import connect_state


def status() -> str:
    con = connect_state()
    caps = config.budget()["phases"]
    lines = ["Spend by phase (computed from the price table):"]
    rows = dict(con.execute("SELECT phase, SUM(cost) FROM ledger GROUP BY phase").fetchall())
    calls = dict(con.execute("SELECT phase, COUNT(*) FROM ledger GROUP BY phase").fetchall())
    total = 0.0
    for ph, cap in caps.items():
        s = rows.get(ph, 0.0) or 0.0
        total += s
        lines.append(f"  {ph}: ${s:8.2f} of ${cap:>4}  ({calls.get(ph, 0)} calls)")
    lines.append(f"  total: ${total:.2f} of ${config.budget()['total_limit']}")
    by_model = con.execute("SELECT model, COUNT(*), SUM(cost), AVG(tokens_in), AVG(tokens_out) FROM ledger GROUP BY model").fetchall()
    lines.append("By model: " + "; ".join(f"{m} {n} calls ${c:.2f} (avg in {i:.0f}/out {o:.0f})" for m, n, c, i, o in by_model))
    lines.append("Phase artefacts:")
    for ph in ("P2", "P3", "P4", "P5", "P6", "P7"):
        d = config.RUNS / ph
        if d.exists():
            runs = [p for p in d.iterdir() if (p / "manifest.json").exists()]
            unfinished = [p.name for p in runs if not json.loads((p / "manifest.json").read_text(encoding="utf-8")).get("finished")]
            lines.append(f"  {ph}: {len(runs)} runs, {len(unfinished)} unfinished {unfinished[:6]}")
    sealed = (config.DATA / "manifests")
    if sealed.exists():
        lines.append("Sealed datasets: " + ", ".join(sorted(p.stem for p in sealed.glob("*.json"))))
    return "\n".join(lines)

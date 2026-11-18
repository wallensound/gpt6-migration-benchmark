"""`make report`: rebuild runs/bench.duckdb, REPORT.md and the four charts from runs/ (works at any stage)."""
from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

from . import config
from .cases import Case, all_case_ids
from .phases import frozen_info

FIG = config.ROOT / "report"
# reference palette (dataviz skill), light mode
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
DIV_NEG, DIV_MID, DIV_POS = "#e34948", "#f0efec", "#2a78d6"
TARGET_ORDER = ["gpt-6.2-astra", "gpt-6.2-sol", "gpt-6.1-terra", "gpt-6-luna"]
LOOP_TARGETS = ["gpt-6-luna", "gpt-6.1-terra", "gpt-6.2-sol"]


def pct(x, d=1):
    return "–" if x is None else f"{100 * x:.{d}f}%"


def pts(x, d=1):
    return "–" if x is None else f"{100 * x:+.{d}f}"


def money(x, d=4):
    return "–" if x is None else f"${x:.{d}f}"


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# --------------------------------------------------------------------------- duckdb

def build_duckdb() -> dict:
    import duckdb
    import pandas as pd
    db = config.RUNS / "bench.duckdb"
    if db.exists():
        db.unlink()
    runs, results = [], []
    for man in sorted(config.RUNS.glob("P*/*/manifest.json")):
        m = json.loads(man.read_text(encoding="utf-8"))
        for e in m.get("evals", []):
            s = e.get("summary", {})
            runs.append({"run_id": m["run_id"], "phase": m["phase"], "case": m.get("case"), "kind": m.get("kind"),
                         "eval_id": e["eval_id"], "model": e["model"], "model_id": e["model_id"], "api": e["api"],
                         "effort": e.get("effort"), "settings": json.dumps(e.get("settings")), "prompt_hash": e["prompt_hash"],
                         "seed": m.get("seed"), "repeat": e.get("repeat"), "git_commit": m.get("git_commit"),
                         "sdk_version": m.get("sdk_version"), "started_at": m.get("started_at"),
                         "dataset_version": m.get("dataset_version"), "n": s.get("n"), "primary": s.get("primary"),
                         "validity": s.get("validity"), "cost_usd": s.get("cost_usd")})
        rp = man.parent / "results.jsonl.gz"
        if rp.exists():
            with gzip.open(rp, "rt", encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    results.append({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                                    for k, v in r.items()})
    con = duckdb.connect(str(db))
    if runs:
        con.register("r", pd.DataFrame(runs))
        con.execute("CREATE TABLE run AS SELECT * FROM r")
    if results:
        df = pd.DataFrame(results)
        con.register("x", df)
        con.execute("""CREATE TABLE result AS SELECT run_id, eval_id, item_id, split, slice, raw_output, parsed, valid,
                       tokens_in, tokens_cached, tokens_cache_write, tokens_out, tokens_reasoning, latency_ms, cost_usd,
                       error_code, from_cache FROM x""")
        con.execute("""CREATE TABLE score AS SELECT run_id, eval_id, item_id, passed, nonanswer, secondary, categories, diff
                       FROM x""")
    con.close()
    return {"runs": len(runs), "results": len(results)}


# --------------------------------------------------------------------------- charts

def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
                         "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                         "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
                         "axes.spines.right": False, "font.size": 9, "axes.titlesize": 10, "legend.frameon": False})
    return plt


def chart_zero_shot(final: dict) -> str | None:
    cases = [k for k, c in final["cases"].items() if c.get("status") == "evaluated"]
    if not cases:
        return None
    plt = _plt()
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
    import numpy as np
    M = np.full((len(cases), len(TARGET_ORDER)), np.nan)
    for i, cf in enumerate(cases):
        for j, t in enumerate(TARGET_ORDER):
            p = final["cases"][cf]["ports"].get(t)
            if p:
                M[i, j] = 100 * p["zero_shot_drop"]
    lim = max(5.0, float(np.nanmax(np.abs(M))) if np.isfinite(M).any() else 5.0)
    cmap = LinearSegmentedColormap.from_list("div", [DIV_NEG, DIV_MID, DIV_POS])
    fig, ax = plt.subplots(figsize=(6.4, 0.45 * len(cases) + 1.6))
    im = ax.imshow(M, cmap=cmap, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
    ax.grid(False)
    ax.set_xticks(range(len(TARGET_ORDER)), TARGET_ORDER)
    ax.set_yticks(range(len(cases)), cases)
    for i in range(len(cases)):
        for j in range(len(TARGET_ORDER)):
            if np.isfinite(M[i, j]):
                ax.text(j, i, f"{M[i, j]:+.1f}", ha="center", va="center", color=INK, fontsize=8)
    ax.set_title("Zero-shot drop on test (points)\nmechanical port minus legacy setup on gpt-5.6-sol", loc="left")
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.outline.set_visible(False)
    fig.tight_layout()
    p = FIG / "zero_shot_drop.png"
    fig.savefig(p, dpi=160)
    plt.close(fig)
    return p.name


def chart_recovery(final: dict) -> str | None:
    cases = [k for k, c in final["cases"].items() if c.get("targets")]
    if not cases:
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    off = {t: (i - 1) * 0.22 for i, t in enumerate(LOOP_TARGETS)}
    for k, t in enumerate(LOOP_TARGETS):
        xs, ys, lo, hi = [], [], [], []
        for i, cf in enumerate(cases):
            r = final["cases"][cf]["targets"].get(t)
            if r:
                xs.append(i + off[t]); ys.append(100 * r["mean_recovery"])
                lo.append(100 * r["recovery_range"][0]); hi.append(100 * r["recovery_range"][1])
        if xs:
            ax.vlines(xs, lo, hi, color=SERIES[k], linewidth=2)
            ax.plot(xs, ys, "o", color=SERIES[k], markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5, label=t)
    ax.axhline(0, color=INK2, linewidth=1)
    ax.axhline(-3, color=INK2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(len(cases) - 0.5, -3, "non-inferiority margin (−3)", ha="right", va="bottom", color=INK2, fontsize=8)
    ax.set_xticks(range(len(cases)), [c[:2] + " " + c[3:].split("-")[0] for c in cases])
    ax.set_ylabel("Recovery vs legacy (points)")
    ax.set_title("Recovery after the loop: mean of three seeds, line = seed range", loc="left")
    lo_all = min([l for t in LOOP_TARGETS for cf in cases for l in [100 * final["cases"][cf]["targets"].get(t, {}).get("recovery_range", [0])[0]]] + [-3.5])
    ax.set_ylim(lo_all - 1, max(3.5, ax.get_ylim()[1]))
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.08), ncols=3)
    fig.tight_layout()
    p = FIG / "recovery.png"
    fig.savefig(p, dpi=160)
    plt.close(fig)
    return p.name


def chart_cost(final: dict) -> str | None:
    pts_ = []
    for cf, c in final["cases"].items():
        if c.get("status") != "evaluated":
            continue
        if c["source"].get("cost_per_correct"):
            pts_.append(("legacy (gpt-5.6-sol)", c["source"]["cost_per_correct"], c["source"]["test"]))
        for t, p in c["ports"].items():
            if p.get("cost_per_correct"):
                pts_.append(("mechanical port", p["cost_per_correct"], p["test"]))
        for n, o in c["opt"].items():
            if o.get("cost_per_correct"):
                pts_.append(("optimised", o["cost_per_correct"], o["test"]))
    if not pts_:
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.4, 4))
    kinds = ["legacy (gpt-5.6-sol)", "mechanical port", "optimised"]
    for k, kind in enumerate(kinds):
        xs = [x for kk, x, y in pts_ if kk == kind]
        ys = [100 * y for kk, x, y in pts_ if kk == kind]
        ax.scatter(xs, ys, s=28, color=SERIES[k], edgecolor=SURFACE, linewidth=1, label=kind, zorder=3)
    srt = sorted(pts_, key=lambda r: r[1])
    fx, fy, best = [], [], -1
    for _, x, y in srt:
        if y > best:
            best = y; fx.append(x); fy.append(100 * y)
    ax.step(fx, fy, where="post", color=INK2, linewidth=1, linestyle=(0, (3, 3)), label="frontier", zorder=2)
    ax.set_xscale("log")
    ax.set_xlabel("Cost per correct answer (USD, log scale)")
    ax.set_ylabel("Primary score on test (%)")
    ax.set_title("Cost against score, every final configuration", loc="left")
    ax.legend(loc="lower right")
    fig.tight_layout()
    p = FIG / "cost_vs_score.png"
    fig.savefig(p, dpi=160)
    plt.close(fig)
    return p.name


def chart_loop_progress(loops: list[dict], target: str) -> str | None:
    by_case: dict[str, list] = {}
    for l in loops:
        if l["target"] == target and l["version"] == 1:
            by_case.setdefault(l["case"], []).append(l)
    if not by_case:
        return None
    plt = _plt()
    cases = sorted(by_case)
    ncol = 4
    nrow = (len(cases) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(10, 2.3 * nrow), sharey=False, squeeze=False)
    seeds = [11, 22, 33]
    for ax, cf in zip(axes.flat, cases):
        for l in sorted(by_case[cf], key=lambda r: r["seed"]):
            k = seeds.index(l["seed"]) if l["seed"] in seeds else 0
            xs = [e["round"] for e in l["round_log"]]
            ys = [100 * (e.get("dev_primary_after", e.get("dev_primary")) or 0) for e in l["round_log"]]
            ax.plot(xs, ys, color=SERIES[k], linewidth=2, label=f"seed {l['seed']}")
            for e in l["round_log"][1:]:
                d = e.get("decision") or {}
                if "dev_primary" in d:
                    ax.plot(e["round"], 100 * d["dev_primary"], "o" if e.get("accepted") else "x",
                            color=SERIES[k], markersize=6 if e.get("accepted") else 5,
                            markeredgecolor=SURFACE if e.get("accepted") else SERIES[k])
        ax.set_title(cf, loc="left", fontsize=9)
        ax.set_xticks(range(0, 6))
        ys_all = [y for ln in ax.get_lines() for y in ln.get_ydata()]
        ax.set_ylim(max(0, min(ys_all + [90]) - 3), 101)
    for ax in list(axes.flat)[len(cases):]:
        ax.axis("off")
    h, lab = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper right", ncols=3)
    fig.suptitle(f"Loop progress on {target}: dev score by round (o accepted candidate, x rejected)", x=0.01, ha="left", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    p = FIG / f"loop_progress_{target}.png"
    fig.savefig(p, dpi=160)
    plt.close(fig)
    return p.name


# --------------------------------------------------------------------------- collect

def collect_loops() -> list[dict]:
    out = []
    for man in sorted((config.RUNS / "P5").glob("*/manifest.json")) if (config.RUNS / "P5").exists() else []:
        m = json.loads(man.read_text(encoding="utf-8"))
        rl = _json(man.parent / "round_log.json") or []
        rej = _json(man.parent / "rejection_log.json") or []
        out.append({"run_id": m["run_id"], "case": m["case"], "target": m["target"], "seed": m["seed"],
                    "version": m.get("dataset_version", 1), "effort": m.get("effort"), "finished": m.get("finished"),
                    "stop_reason": m.get("stop_reason"), "port_dev": m.get("port_dev_primary"),
                    "final_dev": m.get("final_dev_primary"), "accepted_rounds": m.get("accepted_rounds", []),
                    "round_log": rl, "rejections": rej, "final_leak_check": m.get("final_leak_check")})
    return out


def build_report() -> str:
    FIG.mkdir(parents=True, exist_ok=True)
    db = build_duckdb()
    final = _json(config.RUNS / "P6" / "final.json")
    loops = collect_loops()
    L = []
    summ = config.ROOT / "REPORT_SUMMARY.md"
    L.append("# REPORT: Is prompt migration to GPT-6 reproducible?\n")
    L.append(f"_Regenerated by `make report` on {time.strftime('%Y-%m-%d %H:%M')} from `runs/` "
             f"({db['runs']} evaluations, {db['results']} scored responses in `runs/bench.duckdb`)._\n")
    if summ.exists():
        L.append(summ.read_text(encoding="utf-8").strip() + "\n")
    # ---- setup
    L.append("## Setup\n")
    mcfg = config.models()["models"]
    L.append("| Model | Role | Provider / model ID | Resolved model | Efforts used | Price in/out per 1M |\n|---|---|---|---|---|---|")
    for n, m in mcfg.items():
        L.append(f"| {n} | {m['role']} | {m['provider']} `{m['model_id']}` | {(m.get('probed') or {}).get('resolved_model', '')} | "
                 f"{', '.join(m['efforts'])} | ${m['price_in']} / ${m['price_out']} ({m['tier']}) |")
    L.append(f"\nSDK `openai=={config.sdk_version()}`; reference date {config.REFERENCE_DATE}; models checked "
             f"{(mcfg['gpt-6-luna'].get('probed') or {}).get('checked_at', '?')}. Costs use the price table above "
             "(see PROGRESS.md decisions D1, D2, D9).\n")
    # ---- cases
    L.append("## Cases and data\n")
    L.append("| Case | Legacy dev score (floor) | Drop rate | Train / dev / test / shift | Frozen prompt hash |\n|---|---|---|---|---|")
    for cid in all_case_ids():
        c = Case(cid)
        fz = frozen_info(c)
        st = _json(config.DATA / "stats" / f"{c.folder}.json") or {}
        sz = st.get("items_per_split", {})
        L.append(f"| {c.folder} | {pct(fz['dev_primary']) if fz else 'not frozen'} ({pct(fz['floor'], 0) if fz else '–'}) | "
                 f"{pct(st.get('drop_rate'))} | {sz.get('train', '–')} / {sz.get('dev', '–')} / {sz.get('test', '–')} / {sz.get('shift', '–')} | "
                 f"`{fz['prompt_hash'] if fz else '–'}` |")
    L.append("")
    # ---- sweep
    sweeps = {p.parent.name.replace("-sweep", ""): _json(p) for p in sorted((config.RUNS / "P4").glob("*-sweep/sweep.json"))} \
        if (config.RUNS / "P4").exists() else {}
    if sweeps:
        L.append("## Q1. How much breaks? Sweep on dev (legacy prompt, mechanical port)\n")
        cols = ["source"] + [f"{t}/{e}" for t in TARGET_ORDER for e in config.model_cfg(t)["efforts"]]
        L.append("| Case | " + " | ".join(cols) + " |\n|" + "---|" * (len(cols) + 1))
        for cf, s in sweeps.items():
            d = {f"{r['model']}/{r['effort']}": r for r in s["rows"][1:]}
            cells = [pct(s["source"]["primary"])] + [pct(d[c]["primary"]) if c in d else "–" for c in cols[1:]]
            L.append(f"| {cf} | " + " | ".join(cells) + " |")
        L.append("\nChosen effort per target (best primary score per dollar on dev; ties to the lower effort):\n")
        L.append("| Case | " + " | ".join(TARGET_ORDER) + " |\n|" + "---|" * (len(TARGET_ORDER) + 1))
        for cf, s in sweeps.items():
            L.append(f"| {cf} | " + " | ".join(s["effort_choice"].get(t, {}).get("effort", "–") for t in TARGET_ORDER) + " |")
        L.append("\nLiteral model-string swap (legacy request unchanged, Responses shape): which settings were rejected\n")
        for cf, s in sweeps.items():
            rej = sorted({k for k, v in s["literal_swap"].items() if not v["accepted"]})
            msgs = sorted({v["error"][:90] for v in s["literal_swap"].values() if not v["accepted"]})
            L.append(f"- **{cf}**: rejected at {', '.join(rej) or 'none'}" + (f" — {'; '.join(msgs)}" if msgs else ""))
        L.append("")
    # ---- final
    if final:
        z = chart_zero_shot(final)
        L.append("## Q1 (test). Zero-shot drop per case and target\n")
        if z:
            L.append(f"![Zero-shot drop](report/{z})\n")
        L.append("| Case | Legacy (source) | " + " | ".join(TARGET_ORDER) + " |\n|" + "---|" * (len(TARGET_ORDER) + 2))
        for cf, c in final["cases"].items():
            if c.get("status") != "evaluated":
                L.append(f"| {cf} | {c.get('status')} |" + " |" * len(TARGET_ORDER))
                continue
            cells = []
            for t in TARGET_ORDER:
                p = c["ports"].get(t)
                cells.append(f"{pct(p['test'])} ({pts(p['zero_shot_drop'])}, {p['effort']})" if p else "–")
            L.append(f"| {cf} | {pct(c['source']['test'])} | " + " | ".join(cells) + " |")
        L.append("\nCells: test score of the mechanical port (zero-shot drop in points, chosen effort).\n")
        r = chart_recovery(final)
        L.append("## Q2. Does the loop fix it? Recovery and migrated verdicts\n")
        if r:
            L.append(f"![Recovery](report/{r})\n")
        L.append("| Case | Target | Seed | Test | Recovery | NI lower bound | Holm p | Migrated | Shift | Shift gap |\n|---|---|---|---|---|---|---|---|---|---|")
        for cf, c in final["cases"].items():
            for n, o in sorted((c.get("opt") or {}).items()):
                L.append(f"| {cf} | {o['target']} | {o['seed']} | {pct(o['test'])} | {pts(o['recovery'])} | "
                         f"{pts(o['ni_lower_bound'])} | {o['ni_p_holm']:.3f} | {'yes' if o['migrated'] else 'no'} | "
                         f"{pct(o['shift'])} | {pts(o['shift_gap'])}{' ⚑' if o.get('overfit_flag') else ''} |")
        L.append("")
        L.append("## Q3. Is the fix reproducible?\n")
        L.append("| Case | Target | Mean test | Seed spread | Verdict agreement | Migrated seeds | Seed-repeat check |\n|---|---|---|---|---|---|---|")
        for cf, c in final["cases"].items():
            for t, g in (c.get("targets") or {}).items():
                L.append(f"| {cf} | {t} | {pct(g['mean_test'])} | {100 * g['seed_spread']:.1f} pts | "
                         f"{'yes' if g['verdict_agreement'] else 'no'} | {g['migrated_seeds']}/3 | {'pass' if g['seed_repeat_pass'] else 'fail'} |")
        o = final["overall"]
        L.append("\n| Check | Result | Passes |\n|---|---|---|")
        L.append(f"| Seed repeats (Luna / Terra) | {o['seed_repeat_pass_gpt-6-luna']} / {o['seed_repeat_pass_gpt-6.1-terra']} of {o['n_cases']} cases | "
                 f"{'yes' if o['seed_repeat_pass_min'] >= 6 else 'no'} |")
        L.append(f"| Across cases (migrated, Luna / Terra) | {o['migrated_cases_gpt-6-luna']} / {o['migrated_cases_gpt-6.1-terra']} of {o['n_cases']} | {'yes' if o['across_cases_pass'] else 'no'} |")
        L.append(f"| Main tier (Sol vs Terra on 01, 03, 07) | " + "; ".join(
            f"{k}: Sol {'migrated' if v['sol_case_migrated'] else 'not'} / Terra {'migrated' if v['terra_case_migrated'] else 'not'}, spread {100 * v['sol_seed_spread']:.1f}"
            for k, v in o["main_tier"].items()) + f" | {'yes' if o['main_tier_pass'] else 'no'} |")
        L.append(f"| Data version (v2 vs v1 Luna mean) | " + "; ".join(f"{k}: {pct(v['v2_test'])} vs {pct(v['v1_seed_mean'])} ({pts(v['diff'])})" for k, v in o["data_version"].items())
                 + f" | {'yes' if o['data_version_pass'] else 'no'} |")
        L.append(f"| Shift (gap <= 5 points) | {len(o['shift_flags'])} flagged | {'yes' if o['shift_pass'] else 'no'} |")
        cr = o.get("clean_rerun") or {}
        L.append(f"| Clean rerun (case 03, Luna, seed 11) | rerun {pct(cr.get('rerun_test'))} vs reported {pct(cr.get('reported_test'))} | "
                 f"{'yes' if o.get('clean_rerun_pass') else ('not run' if o.get('clean_rerun_pass') is None else 'no')} |")
        L.append(f"\n**Overall verdict: {o['verdict']}.**\n")
        stab = [(cf, k, v) for cf, c in final["cases"].items() for k, v in (c.get("stability_flip_rate") or {}).items()]
        if stab:
            L.append("Stability (share of test items whose pass/fail flips across three repeated runs):\n")
            L.append("| Case | Configuration | Flip rate |\n|---|---|---|")
            for cf, k, v in stab:
                L.append(f"| {cf} | {k} | {pct(v)} |")
            L.append("")
        cimg = chart_cost(final)
        L.append("## Q4. What does it cost? Cost per correct answer on test\n")
        if cimg:
            L.append(f"![Cost against score](report/{cimg})\n")
        L.append("| Case | Legacy | " + " | ".join(f"{t} port" for t in TARGET_ORDER) + " | " +
                 " | ".join(f"{t} optimised (mean)" for t in LOOP_TARGETS) + " |\n|" + "---|" * (2 + len(TARGET_ORDER) + len(LOOP_TARGETS)))
        for cf, c in final["cases"].items():
            if c.get("status") != "evaluated":
                continue
            row = [money(c["source"]["cost_per_correct"])]
            row += [money((c["ports"].get(t) or {}).get("cost_per_correct")) for t in TARGET_ORDER]
            for t in LOOP_TARGETS:
                v = [o["cost_per_correct"] for o in c["opt"].values() if o["target"] == t and o["cost_per_correct"]]
                row.append(money(sum(v) / len(v)) if v else "–")
            L.append(f"| {cf} | " + " | ".join(row) + " |")
        L.append("")
    # ---- loops
    if loops:
        L.append("## Loop runs\n")
        for t in LOOP_TARGETS:
            img = chart_loop_progress(loops, t)
            if img:
                L.append(f"![Loop progress {t}](report/{img})\n")
        L.append("| Run | Effort | Port dev | Final dev | Accepted rounds | Stop reason | Leak check |\n|---|---|---|---|---|---|---|")
        for l in loops:
            L.append(f"| {l['run_id']} | {l['effort']} | {pct(l['port_dev'])} | {pct(l['final_dev'])} | "
                     f"{', '.join(map(str, l['accepted_rounds'])) or 'none'} | {l['stop_reason'] or ('running' if not l['finished'] else '')} | "
                     f"{'ok' if (l['final_leak_check'] or {}).get('ok') else ('–' if not l['final_leak_check'] else 'FAIL')} |")
        L.append("\nAccepted candidates and their rationales (the optimiser's one-line reasons):\n")
        for l in loops:
            for e in l["round_log"][1:]:
                if e.get("accepted"):
                    d = e["decision"]
                    rat = next((c["rationale"] for c in e["candidates"] if c.get("status") == "accepted"), "")
                    L.append(f"- `{l['run_id']}` round {e['round']} ({d['edit_kind']}, dev {pct(d['dev_primary_current'])} -> {pct(d['dev_primary'])}): {rat}")
        L.append("")
    # ---- protocol verbatim
    L.append("## Pre-registered protocol (verbatim from PROTOCOL.md)\n")
    proto = (config.ROOT / "PROTOCOL.md").read_text(encoding="utf-8")
    L.append("\n".join("> " + line for line in proto.splitlines()))
    L.append("")
    obs = config.ROOT / "report" / "observations.md"
    if obs.exists():
        L.append(obs.read_text(encoding="utf-8"))
    out = "\n".join(L) + "\n"
    (config.ROOT / "REPORT.md").write_text(out, encoding="utf-8")
    return f"REPORT.md written ({len(out)} chars); duckdb: {db}"
